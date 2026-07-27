
"""N1 - The Vent.

The first needy module: it never "solves" (Module.needy=True excludes it
from Bomb._settle()'s win check - see T15's session notes) - it just has to
be tended for the whole round, generating a strike if neglected.

Every ~45s one of three vents starts glowing. EYES sees exactly which one,
directly - no probing needed. HANDS feels the SAME vent as "warm" via probe,
which is a deliberately redundant confirmation channel, not the hidden part.
The hidden part is BOOK's manual: a per-round-random table mapping the
glowing vent's number to the vent that must ACTUALLY be purged. Purging the
glowing vent itself is only correct if the table happens to map it to
itself - most rounds it won't. Three-key rule: satisfied. HANDS alone knows
which vent is warm but not which to purge; EYES alone knows which glows but
not the table; BOOK alone knows the table but not which vent is currently
glowing.
"""
import html
import random

from .base import Layout, Module, Result, Slot, Views, register

N_VENTS = 3
PURGE_WINDOW_S = 15.0
COOLDOWN_RANGE_S = (30.0, 60.0)  # averages ~45s, per AGENTS.md T15


@register
class Vent(Module):
    id = "n01"
    name = "The Vent"
    needy = True

    def generate(self, rng: random.Random, flags: dict) -> None:
        # Vent needs its own draws every cycle for the rest of the round,
        # long after generate()'s single rng call is spent elsewhere - a
        # private, seed-derived Random keeps that reproducible relative to
        # dt-application order without holding a reference to the shared rng.
        self._rng = random.Random(rng.randrange(2 ** 31))
        self.table = {glow: self._rng.randrange(N_VENTS) for glow in range(N_VENTS)}
        self.active: int | None = None
        self.timer = 0.0
        self.cooldown = self._rng.uniform(*COOLDOWN_RANGE_S)
        # Needy modules never contribute to the win condition (see
        # server/bomb.py's _settle()) - this stays False for the entire
        # round on purpose, it is not a bug that it's never set True.
        self.solved = False

    def _start_cycle(self) -> None:
        self.active = self._rng.randrange(N_VENTS)
        self.timer = PURGE_WINDOW_S

    def _cool_down(self) -> None:
        self.active = None
        self.cooldown = self._rng.uniform(*COOLDOWN_RANGE_S)

    def tick(self, dt: float) -> Result:
        if self.active is None:
            self.cooldown -= dt
            if self.cooldown <= 0:
                self._start_cycle()
            return Result.NOTHING

        self.timer -= dt
        if self.timer <= 0:
            self._cool_down()
            return Result.STRIKE
        return Result.NOTHING

    def act(self, role: str, action: dict) -> Result:
        if role != "hands" or "purge" not in action or self.active is None:
            return Result.NOTHING
        i = int(action["purge"])
        if not (0 <= i < N_VENTS):
            return Result.NOTHING

        target = self.table[self.active]
        if i != target:
            # Wrong vent: a strike, but the vent stays active so a
            # miscommunication under time pressure can still be corrected
            # within the remaining window, rather than compounding penalties.
            return Result.STRIKE

        self._cool_down()
        return Result.NOTHING

    def inspect(self, role: str, query: dict) -> dict:
        if role != "hands" or "cell" not in query:
            return {}
        i = int(query["cell"])
        if not (0 <= i < N_VENTS):
            return {}
        return {"cell": i, "text": "warm" if i == self.active else "cool"}

    def views(self) -> Views:
        return Views(
            hands={"kind": "vent", "count": N_VENTS, "solved": self.solved},
            eyes={"kind": "vent", "count": N_VENTS, "glowing": self.active, "solved": self.solved},
            book={"kind": "manual", "module": self.name, "solved": self.solved},
            scope={"kind": "netlist", "count": N_VENTS, "nets": [], "solved": self.solved},
        )

    def layout(self) -> Layout:
        slots = [Slot(idx=i, kind="vent", x=(i + 0.5) / N_VENTS, y=0.5) for i in range(N_VENTS)]
        return Layout(w=N_VENTS, h=1, slots=slots)

    def manual_page(self) -> str:
        rows = "".join(
            "<tr><th>%d</th><td>%d</td></tr>" % (glow + 1, target + 1)
            for glow, target in self.table.items()
        )
        notes = [
            "This module never finishes - it must be tended for the whole round.",
            "Roughly every 45 seconds, one of the three vents starts glowing. EYES calls out its number.",
            "Look up the glowing number below to find which vent HANDS must actually purge - "
            "they are often <b>not</b> the same vent.",
            "HANDS has 15 seconds to purge the correct vent once one starts glowing. "
            "Purging the wrong vent, or running out of time, is a strike.",
        ]
        return ('<section class="module"><h2>%s</h2>'
                '<table class="rules"><tr><th>Glowing vent</th><th>Purge vent</th></tr>%s</table>'
                '<ol class="notes">%s</ol></section>'
                % (html.escape(self.name), rows, "".join("<li>%s</li>" % n for n in notes)))
