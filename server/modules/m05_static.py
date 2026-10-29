
"""M5 - The Static.

BLIND probes every tile and privately learns whether it BUZZES or stays
QUIET. DEAF sees each tile's colour, from a small palette. The team tallies
how many tiles buzz in total (BLIND's own count, built up one probe at a
time - not a single number handed to them). MUTE's manual holds a plain
comparison rule: if the buzzing count is at least the number of LEDs lit on
DEAF's own display, press every tile of one colour; otherwise press every
tile of the other. Unlike M1/M2/M4, there is no per-tile lookup table at
all - the puzzle is an aggregate count crossed against a threshold, not a
per-slot classification.

Three-key rule: satisfied. BLIND alone knows which tiles buzz but not their
colours, the LED count, or which colour is currently correct; DEAF alone
knows colours and their own LED count but not which tiles buzz; MUTE alone
knows the rule and the two candidate colours but neither the buzz count nor
the LED count nor any tile's actual colour.
"""
import html
import random

from .base import Layout, Module, Result, Slot, Views, register

COLOURS = ["amber", "teal"]


@register
class Static(Module):
    id = "m05"
    name = "The Static"

    def generate(self, rng: random.Random, flags: dict) -> None:
        n = 6
        self.tiles = [
            {"charged": rng.random() < 0.5, "colour": rng.choice(COLOURS), "pressed": False}
            for _ in range(n)
        ]

        # Guard against a degenerate round where every tile shares one
        # colour - "press every X" would collapse into "press everything" or
        # "press nothing", same spirit as M2's all-one-verdict guard.
        if len({t["colour"] for t in self.tiles}) < 2:
            other = COLOURS[1] if self.tiles[0]["colour"] == COLOURS[0] else COLOURS[0]
            self.tiles[0]["colour"] = other

        # Reuses the existing DEAF "leds" flag (unused until now) as the
        # comparison threshold - DEAF already sees their own lit LED count,
        # so the rule is checkable with no new flag or broadcast field.
        # Clamped to [1, n-1] so BOTH branches stay reachable depending on
        # the round's actual buzz count - a threshold of 0 would make the
        # buzzing count irrelevant (count >= 0 is always true), letting
        # DEAF+MUTE solve this without BLIND ever probing a single tile.
        self.threshold = max(1, min(flags.get("leds", 0), n - 1))
        self.reaches_colour, self.otherwise_colour = rng.sample(COLOURS, 2)

        self.solved = False

    def _target_colour(self) -> str:
        buzzing = sum(1 for t in self.tiles if t["charged"])
        return self.reaches_colour if buzzing >= self.threshold else self.otherwise_colour

    def solution(self) -> list[int]:
        """Indices that must be pressed. Testbenches only. Never sent to any client."""
        target = self._target_colour()
        return [i for i, t in enumerate(self.tiles) if t["colour"] == target]

    def act(self, role: str, action: dict) -> Result:
        if role != "blind" or self.solved:
            return Result.NOTHING
        if "press" not in action:
            return Result.NOTHING
        i = int(action["press"])
        if not (0 <= i < len(self.tiles)) or self.tiles[i]["pressed"]:
            return Result.NOTHING

        if self.tiles[i]["colour"] != self._target_colour():
            return Result.STRIKE

        self.tiles[i]["pressed"] = True
        if all(t["pressed"] for t in self.tiles if t["colour"] == self._target_colour()):
            self.solved = True
            return Result.SOLVED
        return Result.NOTHING

    def inspect(self, role: str, query: dict) -> dict:
        if role != "blind" or "cell" not in query:
            return {}
        i = int(query["cell"])
        if not (0 <= i < len(self.tiles)):
            return {}
        t = self.tiles[i]
        bits = ["buzzes" if t["charged"] else "quiet"]
        if t["pressed"]:
            bits.append("pressed")
        return {"cell": i, "text": ", ".join(bits)}

    def views(self) -> Views:
        return Views(
            blind={"kind": "static", "count": len(self.tiles),
                   "pressed": [t["pressed"] for t in self.tiles], "solved": self.solved},
            deaf={"kind": "static",
                  "tiles": [{"colour": t["colour"], "pressed": t["pressed"]} for t in self.tiles],
                  "solved": self.solved},
            mute={"kind": "manual", "module": self.name, "solved": self.solved},
            scope={"kind": "netlist", "count": len(self.tiles), "nets": [], "solved": self.solved},
        )

    def layout(self) -> Layout:
        # Same 3x2 tile grid as the Ledger - position only, no colour or
        # charge data, so this is safe to send identically to every role.
        n = len(self.tiles)
        cols = 3
        slots = [Slot(idx=i, kind="tile", x=(i % cols + 0.5) / cols, y=(i // cols + 0.5) / 2)
                 for i in range(n)]
        return Layout(w=cols, h=2, slots=slots)

    def manual_page(self) -> str:
        notes = [
            "BLIND probes every tile and reports whether it buzzes or stays quiet, one at a "
            "time, then the team tallies how many buzz in total.",
            "DEAF already knows their own lit LED count from their own display.",
            "If the buzzing count is greater than or equal to the LED count, press every "
            "<b>%s</b> tile. Otherwise, press every <b>%s</b> tile. (Count zero lit LEDs as one.)"
            % (self.reaches_colour.upper(), self.otherwise_colour.upper()),
            "Do not press a tile of the other colour - that is a strike.",
        ]
        return ('<section class="module"><h2>%s</h2>'
                '<ol class="notes">%s</ol></section>'
                % (html.escape(self.name), "".join("<li>%s</li>" % n for n in notes)))
