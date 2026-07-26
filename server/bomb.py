
"""Bomb: edge flags, module instances, timer, strikes, role-filtered snapshots."""
import dataclasses
import random
import string

from .modules.base import Result
from .modules.m01_braid_hue import BraidHue

CASINGS = ["rough", "smooth", "greasy"]
BADGES = ["red", "blue", "green", "yellow"]
STICKERS = ["ACME", "KOWALSKI", "VOSS"]


class Bomb:
    def __init__(self, seed: int, module_count: int = 2, seconds: float = 300.0):
        self.seed = seed
        rng = random.Random(seed)

        self.flags_hands = {
            "casing": rng.choice(CASINGS),
            "corner_screw": rng.choice(["present", "missing"]),
            "temperature": rng.choice(["cool", "warm"]),
        }
        self.flags_eyes = {
            "serial": "".join(rng.choice(string.ascii_uppercase + string.digits)
                              for _ in range(6)),
            "badge": rng.choice(BADGES),
            "leds": rng.randint(0, 3),
            "sticker": rng.choice(STICKERS),
        }
        self.flags_scope = {
            "board_rev": rng.randint(1, 9),
            "jumpers": rng.randint(0, 4),
            "capacitor": rng.choice(["ok", "bulging"]),
        }
        all_flags = {**self.flags_hands, **self.flags_eyes, **self.flags_scope}

        self.modules = []
        for _ in range(module_count):
            m = BraidHue()
            m.generate(rng, all_flags)
            self.modules.append(m)

        self.time_left = seconds
        self.strikes = 0
        self.max_strikes = 3
        self.phase = "running"

    def _settle(self, result: Result) -> None:
        if result is Result.STRIKE:
            self.strikes += 1
            if self.strikes >= self.max_strikes:
                self.phase = "lost"
        if all(m.solved for m in self.modules):
            self.phase = "won"

    def act(self, role: str, index: int, action: dict) -> Result:
        if self.phase != "running" or not (0 <= index < len(self.modules)):
            return Result.NOTHING
        r = self.modules[index].act(role, action)
        self._settle(r)
        return r

    def inspect(self, role: str, index: int, query: dict) -> dict:
        if not (0 <= index < len(self.modules)):
            return {}
        return self.modules[index].inspect(role, query)

    def tick(self, dt: float) -> None:
        if self.phase != "running":
            return
        self.time_left -= dt
        if self.time_left <= 0:
            self.time_left = 0.0
            self.phase = "lost"
            return
        for m in self.modules:
            self._settle(m.tick(dt))

    def snapshot(self, role: str) -> dict:
        flags = {"hands": self.flags_hands, "eyes": self.flags_eyes,
                 "scope": self.flags_scope, "book": {}}.get(role, {})
        return {
            "phase": self.phase,
            "time_left": round(self.time_left, 1),
            "strikes": self.strikes,
            "max_strikes": self.max_strikes,
            "flags": flags,
            "modules": [m.views().for_role(role) for m in self.modules],
            # WORLD: one shared geometry per module, identical for every role.
            # Kept as its own top-level key (not merged into "modules") so the
            # role-filtered PERCEPTION view above is untouched by this addition.
            "layouts": [dataclasses.asdict(m.layout()) for m in self.modules],
        }

    def manual_html(self) -> str:
        return "".join(m.manual_page() for m in self.modules)
