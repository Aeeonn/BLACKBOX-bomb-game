
"""N2 - The Handshake.

The second needy module (see N1's docstring for what "needy" means: it never
"solves," it just has to be tended for the whole round). Vent's rule is
"always act correctly when it goes off." This module's rule is the opposite
kind of hard: most rounds, the correct move is to do NOTHING at all.

A sync port opens a brief window periodically. EYES sees the window live (a
light) and already knows their own sticker brand. HANDS does NOT see the
window in their broadcast view at all - only by actively probing the port
("syncing" vs "idle"), the same redundant-channel discipline N1 uses for its
glowing vent. BOOK's manual holds the rule: if the sticker reads KOWALSKI,
HANDS must confirm every single sync; otherwise HANDS must NOT confirm and
should let it pass on its own.

Three-key rule: satisfied. HANDS alone can feel whether a window is open but
has no idea whether to confirm it; EYES alone sees the window and their own
sticker but cannot act and does not know the rule; BOOK alone knows the rule
but not the sticker value or when any window is open.
"""
import html
import random

from .base import Layout, Module, Result, Slot, Views, register

WINDOW_S = 8.0
COOLDOWN_RANGE_S = (30.0, 50.0)  # averages ~40s, similar cadence to N1's Vent


@register
class Handshake(Module):
    id = "n02"
    name = "The Handshake"
    needy = True

    def generate(self, rng: random.Random, flags: dict) -> None:
        # Own private seed-derived Random, same reason as N1's: this module
        # keeps drawing cooldowns for the rest of the round, long after
        # generate()'s one shared-rng call is spent elsewhere.
        self._rng = random.Random(rng.randrange(2 ** 31))

        # Reuses the existing EYES "sticker" flag (unused until now) - EYES
        # already sees their own sticker brand, so the rule is checkable
        # with no new flag or broadcast field.
        self.should_confirm = flags.get("sticker") == "KOWALSKI"

        self.window_open = False
        self.timer = 0.0
        self.confirmed_this_window = False
        self.cooldown = self._rng.uniform(*COOLDOWN_RANGE_S)

        # Needy modules never contribute to the win condition (see
        # server/bomb.py's _settle()) - stays False for the whole round.
        self.solved = False

    def tick(self, dt: float) -> Result:
        if not self.window_open:
            self.cooldown -= dt
            if self.cooldown <= 0:
                self.window_open = True
                self.timer = WINDOW_S
                self.confirmed_this_window = False
            return Result.NOTHING

        self.timer -= dt
        if self.timer <= 0:
            self.window_open = False
            self.cooldown = self._rng.uniform(*COOLDOWN_RANGE_S)
            if self.should_confirm and not self.confirmed_this_window:
                return Result.STRIKE  # a required confirm was missed
            return Result.NOTHING  # correctly let a do-not-confirm window pass
        return Result.NOTHING

    def act(self, role: str, action: dict) -> Result:
        if role != "hands" or "confirm" not in action or not self.window_open:
            return Result.NOTHING
        self.confirmed_this_window = True
        # Closes the window immediately either way - once the call is made,
        # there is nothing left to react to for the rest of this cycle.
        self.window_open = False
        self.cooldown = self._rng.uniform(*COOLDOWN_RANGE_S)
        if self.should_confirm:
            return Result.NOTHING
        return Result.STRIKE  # confirmed on a window that should've been left alone

    def inspect(self, role: str, query: dict) -> dict:
        if role != "hands" or "cell" not in query or int(query["cell"]) != 0:
            return {}
        return {"cell": 0, "text": "syncing" if self.window_open else "idle"}

    def views(self) -> Views:
        return Views(
            hands={"kind": "handshake", "solved": self.solved},
            eyes={"kind": "handshake", "open": self.window_open, "solved": self.solved},
            book={"kind": "manual", "module": self.name, "solved": self.solved},
            scope={"kind": "netlist", "count": 1, "nets": [], "solved": self.solved},
        )

    def layout(self) -> Layout:
        return Layout(w=1, h=1, slots=[Slot(idx=0, kind="button", x=0.5, y=0.5)])

    def manual_page(self) -> str:
        notes = [
            "This module never finishes - it must be tended for the whole round.",
            "HANDS can feel whether the sync port is currently syncing by probing it, at any time.",
            "EYES calls out the sticker brand shown on their own display.",
            "If the sticker reads <b>KOWALSKI</b>, HANDS must confirm every single time the "
            "port syncs. If it reads anything else, HANDS must NOT confirm - let every sync "
            "pass on its own instead.",
            "Confirming when you shouldn't, or missing a required confirm before a sync ends, "
            "is a strike.",
        ]
        return ('<section class="module"><h2>%s</h2>'
                '<ol class="notes">%s</ol></section>'
                % (html.escape(self.name), "".join("<li>%s</li>" % n for n in notes)))
