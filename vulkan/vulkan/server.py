"""
server.py — the local app server.

One process serves everything:
  GET  /            desktop UI
  GET  /m           mobile UI (joystick)
  WS   /ws          real-time control + telemetry for both

Why a local web server instead of a native GUI toolkit: the phone needs
a UI anyway, and the robot only allows ONE connection to itself. Serving
both UIs from the one process that holds that single robot connection
means desktop and phone can be used at the same time without fighting
over the robot — which a separate native app + separate mobile app
could not do.
"""

import asyncio
import json
import logging
from pathlib import Path

from aiohttp import web, WSMsgType

from . import config
from .robot_link import RobotLink
from .auto_mode import AutoMode
from .games import GameManager, list_games
from .voice import ChatBrain, detect_wake_word, resolve_target, parse_command

log = logging.getLogger("vulkan.server")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class VulkanApp:
    def __init__(self):
        self.robot = RobotLink()
        self.clients = set()
        self.auto = AutoMode(self.robot, self.broadcast)
        self.games = GameManager(self.robot, self.broadcast)
        self.chat = ChatBrain()
        self.mode = "manual"
        self._camera_task = None

    # ---------------- client fan-out ----------------

    def broadcast(self, kind, payload):
        """Fire-and-forget push to every connected UI (desktop + phone)."""
        msg = json.dumps({"type": kind, **payload})
        for ws in list(self.clients):
            try:
                asyncio.create_task(ws.send_str(msg))
            except Exception:
                self.clients.discard(ws)

    def status(self):
        return {
            "type": "status",
            "connected": self.robot.connected,
            "mode": self.mode,
            "info": self.robot.info,
            "auto_running": self.auto.running,
            "game": self.games.current.id if self.games.current else None,
        }

    # ---------------- camera streaming ----------------

    async def _camera_loop(self):
        interval = 1.0 / max(1, config.CAMERA_FPS)
        try:
            while True:
                if self.robot.connected and self.clients:
                    frame = await self.robot.capture_jpeg_b64()
                    if frame:
                        self.broadcast("camera", {"jpeg": frame})
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Camera loop stopped: %s", e)

    def ensure_camera(self):
        if self._camera_task is None or self._camera_task.done():
            self._camera_task = asyncio.create_task(self._camera_loop())

    # ---------------- mode switching ----------------

    async def set_mode(self, mode):
        if mode == self.mode:
            return
        self.mode = mode
        if mode == "auto":
            await self.games.stop()
            await self.auto.start()
        else:
            await self.auto.stop()
        self.broadcast("status", self.status())

    # ---------------- command handling ----------------

    async def handle(self, action, payload):
        p = payload or {}

        if action == "connect":
            result = await self.robot.connect(p.get("serial") or None)
            if result.get("connected"):
                self.ensure_camera()
            self.broadcast("status", self.status())
            return result

        if action == "disconnect":
            await self.auto.stop()
            await self.games.stop()
            await self.robot.disconnect()
            self.mode = "manual"
            self.broadcast("status", self.status())
            return {"ok": True}

        if action == "mode":
            await self.set_mode(p.get("mode", "manual"))
            return {"ok": True, "mode": self.mode}

        # --- manual control ---
        if action == "move":
            if self.mode == "auto":
                return {"ok": False, "error": "switch to Manual to drive"}
            return await self.robot.move(p.get("direction", "stop"))

        if action == "drive":
            # Continuous joystick input: left/right track speeds.
            if self.mode == "auto":
                return {"ok": False, "error": "switch to Manual to drive"}
            return await self.robot.drive(
                float(p.get("left", 0)), float(p.get("right", 0)), p.get("duration")
            )

        if action == "lift":
            return await self.robot.set_lift(float(p.get("height", 0)))

        if action == "head":
            return await self.robot.set_head(float(p.get("angle", 0.5)))

        if action == "lights":
            return await self.robot.set_lights(p.get("color", "blue"))

        if action == "animate":
            return await self.robot.animate(p.get("name", "hello"))

        if action == "say":
            return await self.robot.say(p.get("text", ""))

        # --- games ---
        if action == "game_list":
            return {"ok": True, "games": list_games()}

        if action == "game_start":
            await self.set_mode("manual")
            return await self.games.start(p.get("game"))

        if action == "game_stop":
            return await self.games.stop()

        if action == "game_action":
            return await self.games.handle(p.get("action"), p)

        # --- chat / voice ---
        if action == "chat":
            return await self.handle_chat(p.get("text", ""), p.get("target", "pc"))

        if action == "status":
            return self.status()

        return {"ok": False, "error": f"unknown action {action}"}

    async def handle_chat(self, text, default_target):
        """The one path both typed chat and speech transcripts go through."""
        target, cleaned = resolve_target(text, default_target)

        # Wake word while roaming: greet, then carry on.
        if self.mode == "auto" and detect_wake_word(text):
            greeting = await self.auto.greet(text)
            self.broadcast("chat", {"role": "vulkan", "text": greeting, "target": "robot"})
            return {"ok": True, "reply": greeting, "target": "robot", "spoken_by": "robot"}

        # Movement commands are matched literally so they work with no
        # model installed and respond instantly.
        cmd = parse_command(cleaned)
        if cmd and target == "robot":
            kind, value = cmd
            if kind == "move":
                await self.robot.move(value)
                reply = f"Okay — {value}."
            elif kind == "lift":
                await self.robot.set_lift(value)
                reply = "Arms up." if value else "Arms down."
            elif kind == "head":
                await self.robot.set_head(value)
                reply = "Looking up." if value > 0.5 else "Looking down."
            elif kind == "mode":
                await self.set_mode(value)
                reply = f"{value.capitalize()} mode."
            else:
                reply = "Done."
            self.broadcast("chat", {"role": "vulkan", "text": reply, "target": target})
            return {"ok": True, "reply": reply, "target": target, "spoken_by": target}

        # Otherwise: conversation.
        reply = await self.chat.reply(cleaned)
        if target == "robot":
            await self.robot.say(reply)
        self.broadcast("chat", {"role": "vulkan", "text": reply, "target": target})
        return {"ok": True, "reply": reply, "target": target, "spoken_by": target}


# ---------------- aiohttp wiring ----------------


async def ws_handler(request):
    app: VulkanApp = request.app["vulkan"]
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    app.clients.add(ws)
    await ws.send_str(json.dumps(app.status()))
    log.info("UI connected (%d total)", len(app.clients))

    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            action = data.get("action")
            req_id = data.get("id")
            try:
                result = await app.handle(action, data)
            except Exception as e:
                log.exception("Action %s failed", action)
                result = {"ok": False, "error": str(e)}
            if req_id is not None:
                await ws.send_str(json.dumps({"type": "result", "id": req_id, **(result or {})}))
    finally:
        app.clients.discard(ws)
        log.info("UI disconnected (%d left)", len(app.clients))
    return ws


async def index(request):
    return web.FileResponse(WEB_DIR / "index.html")


async def mobile(request):
    return web.FileResponse(WEB_DIR / "mobile.html")


def build_app():
    vulkan = VulkanApp()
    app = web.Application()
    app["vulkan"] = vulkan
    app.router.add_get("/", index)
    app.router.add_get("/m", mobile)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static", WEB_DIR)
    return app


def run(host=None, port=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    web.run_app(build_app(), host=host or config.HOST, port=port or config.PORT)
