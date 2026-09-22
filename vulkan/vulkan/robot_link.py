"""
robot_link.py — the single place that talks to the robot.

Everything else in Vulkan (web UI, auto mode, games, voice) goes through
RobotLink. The rcute-cozmars SDK is used as-is rather than reimplementing
its msgpack-RPC-over-websocket protocol; the server on the Pi is
unmodified stock rcute-cozmars-server.

Important constraint from the server: it accepts ONE connection at a
time (see the lock in the server's /rpc handler). So Vulkan holds a
single shared connection and multiplexes every client (desktop window,
phone browser) over it — never one connection per UI.
"""

import asyncio
import base64
import logging

from . import config

log = logging.getLogger("vulkan.robot")


class RobotLink:
    def __init__(self):
        self._robot = None
        self._lock = asyncio.Lock()
        self.serial = None
        self.info = {}

    # ---------------- connection ----------------

    @property
    def connected(self) -> bool:
        return self._robot is not None

    async def connect(self, serial_or_ip=None) -> dict:
        """Connect to the robot. Returns a status dict either way — the UI
        shows connection state prominently, so failures must be reportable
        rather than raised into the void."""
        async with self._lock:
            if self._robot is not None:
                return {"connected": True, "info": self.info}

            try:
                from rcute_cozmars import AioRobot
            except ImportError as e:
                return {"connected": False, "error": f"rcute-cozmars not installed: {e}"}

            target = serial_or_ip or config.DEFAULT_ROBOT
            try:
                robot = AioRobot(target) if target else AioRobot()
                await robot.connect()
                self._robot = robot
                self.serial = target
                self.info = {
                    "hostname": getattr(robot, "hostname", None),
                    "ip": getattr(robot, "ip", None),
                    "serial": getattr(robot, "serial", None),
                }
                log.info("Connected to robot %s", self.info)
                return {"connected": True, "info": self.info}
            except Exception as e:
                self._robot = None
                return {"connected": False, "error": str(e)}

    async def disconnect(self):
        async with self._lock:
            if self._robot is None:
                return
            try:
                await self._robot.disconnect()
            except Exception as e:
                log.warning("Disconnect error (ignored): %s", e)
            finally:
                self._robot = None
                self.info = {}

    # ---------------- movement ----------------

    async def drive(self, left: float, right: float, duration=None):
        """Raw differential drive. left/right are -1.0 .. 1.0.

        This is what the WASD keys and the phone joystick both feed into —
        the joystick sends continuous values here for real-time control
        rather than discrete 'go forward' commands."""
        if not self._robot:
            return {"ok": False, "error": "not connected"}
        try:
            await self._robot.motors.set_speed((left, right), duration)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def stop(self):
        if not self._robot:
            return {"ok": False, "error": "not connected"}
        try:
            await self._robot.motors.stop()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def move(self, direction: str, speed=None, duration=None):
        """Named movement used by keyboard control, auto mode and games."""
        s = config.DRIVE_SPEED if speed is None else speed
        t = config.TURN_SPEED if speed is None else speed
        d = config.MOVE_DURATION if duration is None else duration

        table = {
            "forward": (s, s),
            "backward": (-s, -s),
            "left": (-t, t),
            "right": (t, -t),
        }
        if direction == "stop":
            return await self.stop()
        if direction not in table:
            return {"ok": False, "error": f"unknown direction {direction}"}
        left, right = table[direction]
        return await self.drive(left, right, d)

    # ---------------- arms (lift) and head ----------------

    async def set_lift(self, height: float, duration=0.5):
        """Arm position, 0.0 (down) .. 1.0 (up)."""
        if not self._robot:
            return {"ok": False, "error": "not connected"}
        try:
            lo = self._robot.lift.min_height
            hi = self._robot.lift.max_height
            target = lo + (hi - lo) * max(0.0, min(1.0, height))
            await self._robot.lift.set_height(target, duration=duration)
            return {"ok": True, "height": target}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def set_head(self, angle_fraction: float, duration=0.5):
        """Head tilt, 0.0 (lowest) .. 1.0 (highest)."""
        if not self._robot:
            return {"ok": False, "error": "not connected"}
        try:
            lo = self._robot.head.min_angle
            hi = self._robot.head.max_angle
            target = lo + (hi - lo) * max(0.0, min(1.0, angle_fraction))
            await self._robot.head.set_angle(target, duration=duration)
            return {"ok": True, "angle": target}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------- expression ----------------

    async def say(self, text: str):
        """Speak THROUGH the robot's own speaker (as opposed to the PC's —
        see voice.py for how the user chooses the target)."""
        if not self._robot:
            return {"ok": False, "error": "not connected"}
        try:
            await self._robot.say(text)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def animate(self, name: str):
        if not self._robot:
            return {"ok": False, "error": "not connected"}
        try:
            await self._robot.animate(name)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def set_lights(self, color):
        if not self._robot:
            return {"ok": False, "error": "not connected"}
        try:
            self._robot.lights.color = color
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------- sensors ----------------

    async def distance(self):
        """Sonar distance in cm. Auto mode's obstacle avoidance uses this."""
        if not self._robot:
            return None
        try:
            d = await self._robot.sonar.distance()
            return d * 100 if d is not None and d < 10 else d
        except Exception:
            return None

    async def capture_jpeg_b64(self):
        """One camera frame as base64 JPEG, ready to push over the
        websocket to any connected UI."""
        if not self._robot:
            return None
        try:
            import cv2

            frame = await self._robot.camera.capture()
            if frame is None:
                return None
            ok, buf = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), config.CAMERA_JPEG_QUALITY]
            )
            if not ok:
                return None
            return base64.b64encode(buf.tobytes()).decode("ascii")
        except Exception as e:
            log.debug("Camera capture failed: %s", e)
            return None
