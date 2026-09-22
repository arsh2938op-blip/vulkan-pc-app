"""
auto_mode.py — Vulkan's autonomous behaviour.

Deliberately not a fixed movement loop. Each tick it reads the sonar,
weighs a few weighted choices, and occasionally does something
expressive (look around, wiggle the arms, blink the lights) so it reads
as a robot with its own agenda rather than a Roomba. Obstacle avoidance
always wins over the random choice.
"""

import asyncio
import logging
import random

from . import config

log = logging.getLogger("vulkan.auto")

# (action, weight) — weights are relative, not percentages.
IDLE_ACTIONS = [
    ("forward", 34),
    ("left", 16),
    ("right", 16),
    ("look_around", 12),
    ("pause", 10),
    ("arms", 6),
    ("lights", 6),
]


class AutoMode:
    def __init__(self, robot, broadcast=None):
        self.robot = robot
        self.broadcast = broadcast or (lambda *_: None)
        self._task = None
        self.running = False
        self.last_action = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        log.info("Auto mode started")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.robot.stop()
        log.info("Auto mode stopped")

    async def greet(self, heard_text=""):
        """Called when the wake word is detected (see voice.py). Auto mode
        pauses whatever it was doing, acknowledges, then carries on."""
        self.last_action = "greet"
        self.broadcast("auto", {"action": "greet", "heard": heard_text})
        await self.robot.stop()
        await self.robot.set_head(0.8, duration=0.3)
        greeting = random.choice(
            ["Hello!", "Hi there!", "Hey — I'm listening.", "Yes? I'm here."]
        )
        await self.robot.say(greeting)
        await self.robot.set_head(0.5, duration=0.3)
        return greeting

    async def _loop(self):
        try:
            while self.running:
                await self._tick()
                await asyncio.sleep(config.AUTO_TICK)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("Auto loop crashed: %s", e)
            self.running = False
            self.broadcast("auto", {"action": "error", "error": str(e)})

    async def _tick(self):
        # Obstacle avoidance always takes priority over the random choice.
        dist = await self.robot.distance()
        if dist is not None and dist < config.AUTO_OBSTACLE_CM:
            self.last_action = "avoid"
            self.broadcast("auto", {"action": "avoid", "distance": dist})
            await self.robot.move("backward", duration=0.5)
            await asyncio.sleep(0.5)
            await self.robot.move(random.choice(["left", "right"]), duration=0.6)
            return

        action = random.choices(
            [a for a, _ in IDLE_ACTIONS], weights=[w for _, w in IDLE_ACTIONS]
        )[0]
        self.last_action = action
        self.broadcast("auto", {"action": action, "distance": dist})

        if action in ("forward", "left", "right"):
            await self.robot.move(action, duration=random.uniform(0.3, 0.9))

        elif action == "look_around":
            await self.robot.set_head(random.uniform(0.2, 0.9), duration=0.4)

        elif action == "arms":
            await self.robot.set_lift(random.choice([0.0, 0.5, 1.0]), duration=0.4)

        elif action == "lights":
            await self.robot.set_lights(
                random.choice(["blue", "cyan", "white", (0, 120, 255)])
            )

        elif action == "pause":
            await self.robot.stop()
