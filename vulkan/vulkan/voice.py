"""
voice.py — speech routing and the chat brain.

Two things live here:

1. Target routing. Every spoken/typed exchange has a TARGET:
     "robot"  -> speech comes out of the robot's speaker; commands drive it
     "pc"     -> speech comes out of the PC speakers; it's a normal chat
   The UI has an explicit toggle for this, and a spoken message can also
   override it by starting with "vulkan," (robot) or "computer," (pc).

2. Command parsing. Movement commands are matched literally rather than
   sent to a model — "go forward" should move the robot instantly and
   work with no model installed. Anything that isn't a command falls
   through to the chat model if one is configured.

STT note: recognition itself runs in the BROWSER (Web Speech API) because
the Pi Zero W has nowhere near the headroom for local speech recognition,
and the PC app is already serving a browser UI. The transcript arrives
here as text. TTS likewise: 'pc' target speaks in the browser,
'robot' target calls robot.say().
"""

import logging
import re

from . import config

log = logging.getLogger("vulkan.voice")

COMMANDS = [
    (r"\b(go |move )?forward\b|\bahead\b", ("move", "forward")),
    (r"\b(go |move )?back(ward)?\b|\breverse\b", ("move", "backward")),
    (r"\b(turn |go )?left\b", ("move", "left")),
    (r"\b(turn |go )?right\b", ("move", "right")),
    (r"\bstop\b|\bhalt\b|\bfreeze\b", ("move", "stop")),
    (r"\b(raise|lift|arms? up)\b", ("lift", 1.0)),
    (r"\b(lower|drop|arms? down)\b", ("lift", 0.0)),
    (r"\blook up\b|\bhead up\b", ("head", 0.9)),
    (r"\blook down\b|\bhead down\b", ("head", 0.1)),
    (r"\bauto( mode)?\b|\bexplore\b|\broam\b", ("mode", "auto")),
    (r"\bmanual( mode)?\b", ("mode", "manual")),
]


def detect_wake_word(text: str) -> bool:
    t = (text or "").lower().strip()
    return any(w in t for w in config.WAKE_WORDS)


def resolve_target(text: str, default_target: str) -> tuple:
    """Returns (target, cleaned_text). An explicit prefix overrides the
    UI toggle for that one message."""
    t = (text or "").strip()
    low = t.lower()
    if low.startswith(("vulkan,", "vulkan ", "hey vulkan")):
        cleaned = re.sub(r"^(hey\s+)?vulkan[,\s]+", "", t, flags=re.I)
        return "robot", cleaned
    if low.startswith(("computer,", "computer ", "pc,")):
        cleaned = re.sub(r"^(computer|pc)[,\s]+", "", t, flags=re.I)
        return "pc", cleaned
    return default_target, t


def parse_command(text: str):
    """Returns (kind, value) or None if this isn't a movement command."""
    low = (text or "").lower()
    for pattern, result in COMMANDS:
        if re.search(pattern, low):
            return result
    return None


class ChatBrain:
    """Optional conversational replies via a local Ollama model.

    Kept optional on purpose: the robot must be fully controllable with
    no model installed. If Ollama isn't reachable, chat degrades to a
    short canned reply and every movement command still works.
    """

    SYSTEM_PROMPT = (
        "You are Vulkan, a small friendly desk robot with treads, two arms and a "
        "camera. You are talking to the person in front of you. Keep replies to "
        "one or two short sentences — you're a little robot, not an essay writer. "
        "Be warm, curious and a bit playful."
    )

    def __init__(self, url="http://127.0.0.1:11434", model="gemma2:2b"):
        self.url = url
        self.model = model
        self.available = None

    async def check(self) -> bool:
        import aiohttp

        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{self.url}/api/tags", timeout=3) as r:
                    self.available = r.status == 200
        except Exception:
            self.available = False
        return self.available

    async def reply(self, text: str) -> str:
        import aiohttp

        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{self.url}/api/generate",
                    json={
                        "model": self.model,
                        "system": self.SYSTEM_PROMPT,
                        "prompt": text,
                        "stream": False,
                        "options": {"temperature": 0.7, "num_predict": 120},
                    },
                    timeout=60,
                ) as r:
                    if r.status != 200:
                        return "My chat brain isn't answering right now."
                    data = await r.json()
                    return (data.get("response") or "").strip() or "…"
        except Exception as e:
            log.debug("Chat failed: %s", e)
            return "I can't reach my chat brain, but I can still take commands."
