
"""M3 - Gauge & Detents.

HANDS turns a knob (free, no strike risk) and can feel one tactile "deep
notch" via probe - this is pure flavour and carries zero gameplay
information; it is deliberately NOT the answer, so HANDS cannot solve this
alone by feel no matter how carefully they turn. EYES sees the needle's
exact position on a 1-12 dial, but does not know the target zone. BOOK's
manual holds the target zone (a short contiguous range of positions), but
never sees the current needle position. Three-key rule: satisfied - solving
requires a continuous relay (EYES calling out the needle's number, BOOK
saying where it needs to land) rather than a single probe-then-act like
M1/M2, which is the "no discrete answer" AGENTS.md T16 calls for.

Locking in while the needle is inside the target zone solves the module.
Locking in outside the zone is a strike, but - like N1's wrong purge - the
knob is left exactly where it was, so a miscommunication can be corrected
with more turning rather than being penalised twice.
"""
import html
import random

from .base import Layout, Module, Result, Slot, Views, register

N_POSITIONS = 12


@register
class Gauge(Module):
    id = "m03"
    name = "Gauge & Detents"

    def generate(self, rng: random.Random, flags: dict) -> None:
        # Reuses the existing HANDS "corner_screw" flag rather than inventing
        # a new one - mirrors M1's casing-swap / M2's badge-swap twists.
        width = 3 if flags.get("corner_screw") == "missing" else 2
        zone_start = rng.randrange(N_POSITIONS)
        self.zone = [(zone_start + i) % N_POSITIONS for i in range(width)]
        self.deep_notch = rng.randrange(N_POSITIONS)

        # Guard against the degenerate case where the starting position is
        # already inside the target zone - that would let a lock-in on turn
        # zero solve the module with no relay at all, same spirit as M1's
        # "force at least one CUT" and M2's "force a non-uniform table"
        # guards against a trivial round.
        self.position = rng.randrange(N_POSITIONS)
        while self.position in self.zone:
            self.position = rng.randrange(N_POSITIONS)

        self.solved = False

    def _in_zone(self) -> bool:
        return self.position in self.zone

    def act(self, role: str, action: dict) -> Result:
        if role != "hands" or self.solved:
            return Result.NOTHING

        if "turn" in action:
            # Turning never strikes - it's free exploration, not a
            # commitment. Any value other than "cw"/"ccw" is ignored.
            if action["turn"] == "cw":
                self.position = (self.position + 1) % N_POSITIONS
            elif action["turn"] == "ccw":
                self.position = (self.position - 1) % N_POSITIONS
            return Result.NOTHING

        # Checked with "in", not truthiness - the client always sends a
        # cell index (0) as this key's value, which would be falsy and
        # silently swallow every lock attempt if this used action.get("lock").
        if "lock" in action:
            if self._in_zone():
                self.solved = True
                return Result.SOLVED
            return Result.STRIKE

        return Result.NOTHING

    def inspect(self, role: str, query: dict) -> dict:
        if role != "hands" or "cell" not in query:
            return {}
        if int(query["cell"]) != 0:
            return {}
        text = "deep click" if self.position == self.deep_notch else "click"
        return {"cell": 0, "text": text}

    def views(self) -> Views:
        return Views(
            hands={"kind": "gauge", "solved": self.solved},
            eyes={"kind": "gauge", "position": self.position, "count": N_POSITIONS, "solved": self.solved},
            book={"kind": "manual", "module": self.name, "solved": self.solved},
            scope={"kind": "netlist", "count": 1, "nets": [], "solved": self.solved},
        )

    def layout(self) -> Layout:
        # A single control point - one "dial" slot, not per-position slots,
        # since HANDS only ever acts on the one knob, never a specific
        # position directly.
        return Layout(w=1, h=1, slots=[Slot(idx=0, kind="dial", x=0.5, y=0.5)])

    def manual_page(self) -> str:
        zone_str = ", ".join(str(p + 1) for p in self.zone)
        notes = [
            "The needle moves around a dial numbered 1 through 12. HANDS turns the knob left or right, one detent at a time.",
            "HANDS may feel one deeper notch somewhere on the dial - it is tactile flavour only and means nothing. "
            "Do not use it to navigate; rely on EYES' calls instead.",
            "EYES should call out the needle's current number after every turn.",
            "Guide HANDS to turn the needle onto any of the target numbers below, in either direction, then have "
            "them lock it in.",
            "Locking in outside the target zone is a strike, but the needle does not move - keep turning and try again.",
        ]
        if len(self.zone) > 2:
            notes.append("(A missing corner screw has widened this round's target zone.)")
        return ('<section class="module"><h2>%s</h2>'
                '<p class="rules">Target zone: <b>%s</b></p>'
                '<ol class="notes">%s</ol></section>'
                % (html.escape(self.name), zone_str, "".join("<li>%s</li>" % n for n in notes)))
