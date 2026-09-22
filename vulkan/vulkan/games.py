"""
games.py — minigame framework.

A game is a small class with start()/stop()/handle(). The registry at the
bottom is the only thing the UI reads, so adding a new game later means
writing one class and adding one line — no UI or server changes.
"""

import asyncio
import logging
import random

log = logging.getLogger("vulkan.games")


class BaseGame:
    id = "base"
    name = "Base game"
    description = ""

    def __init__(self, robot, broadcast):
        self.robot = robot
        self.broadcast = broadcast
        self.running = False
        self._task = None

    def say_ui(self, text, **extra):
        """Push a line of game narration to every connected UI."""
        self.broadcast("game", {"game": self.id, "text": text, **extra})

    async def start(self):
        self.running = True
        self._task = asyncio.create_task(self._run())

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

    async def _run(self):
        raise NotImplementedError

    async def handle(self, action, payload):
        """Optional: respond to a button press from the UI."""
        return {"ok": True}


class RedLightGreenLight(BaseGame):
    """Robot drives while 'green', must be stopped by the player on 'red'."""

    id = "red_light"
    name = "Red Light, Green Light"
    description = "Vulkan drives on green. Hit STOP before red or it loses a point."

    def __init__(self, robot, broadcast):
        super().__init__(robot, broadcast)
        self.state = "red"
        self.score = 0
        self.misses = 0

    async def _run(self):
        try:
            self.say_ui("Get ready…", score=self.score)
            await asyncio.sleep(2)
            while self.running:
                self.state = "green"
                await self.robot.set_lights("green")
                self.say_ui("GREEN — go!", state="green", score=self.score)
                await self.robot.move("forward", duration=random.uniform(1.0, 2.5))
                await asyncio.sleep(random.uniform(1.5, 3.5))

                if not self.running:
                    break

                self.state = "red"
                await self.robot.set_lights("red")
                await self.robot.stop()
                self.say_ui("RED — stop!", state="red", score=self.score)
                await asyncio.sleep(1.5)
        except asyncio.CancelledError:
            raise

    async def handle(self, action, payload):
        if action == "stop_press":
            if self.state == "green":
                self.score += 1
                await self.robot.stop()
                self.say_ui(f"Nice — stopped in time! Score {self.score}", score=self.score)
            else:
                self.misses += 1
                self.say_ui(f"Too early! Misses {self.misses}", score=self.score)
        return {"ok": True, "score": self.score}


class FollowTheLeader(BaseGame):
    """Robot performs a move; player repeats it back with the controls."""

    id = "follow"
    name = "Follow the Leader"
    description = "Vulkan performs a move — copy it using the controls before time runs out."

    MOVES = ["forward", "backward", "left", "right"]

    def __init__(self, robot, broadcast):
        super().__init__(robot, broadcast)
        self.expected = None
        self.score = 0

    async def _run(self):
        try:
            while self.running:
                self.expected = random.choice(self.MOVES)
                self.say_ui(f"Copy this: {self.expected.upper()}", expected=self.expected, score=self.score)
                await self.robot.move(self.expected, duration=0.5)
                await asyncio.sleep(5)
                if self.expected is not None and self.running:
                    self.say_ui(f"Time's up — it was {self.expected.upper()}", score=self.score)
        except asyncio.CancelledError:
            raise

    async def handle(self, action, payload):
        if action == "answer":
            guess = (payload or {}).get("move")
            if guess == self.expected:
                self.score += 1
                self.expected = None
                self.say_ui(f"Correct! Score {self.score}", score=self.score)
                await self.robot.say("Correct!")
            else:
                self.say_ui("Not quite.", score=self.score)
        return {"ok": True, "score": self.score}


GAMES = {g.id: g for g in (RedLightGreenLight, FollowTheLeader)}


def list_games():
    return [
        {"id": g.id, "name": g.name, "description": g.description}
        for g in GAMES.values()
    ]


class GameManager:
    """Only one game runs at a time — it owns the robot while active."""

    def __init__(self, robot, broadcast):
        self.robot = robot
        self.broadcast = broadcast
        self.current = None

    async def start(self, game_id):
        await self.stop()
        cls = GAMES.get(game_id)
        if not cls:
            return {"ok": False, "error": f"unknown game {game_id}"}
        self.current = cls(self.robot, self.broadcast)
        await self.current.start()
        return {"ok": True, "game": game_id}

    async def stop(self):
        if self.current:
            await self.current.stop()
            self.current = None
        return {"ok": True}

    async def handle(self, action, payload):
        if not self.current:
            return {"ok": False, "error": "no game running"}
        return await self.current.handle(action, payload)
