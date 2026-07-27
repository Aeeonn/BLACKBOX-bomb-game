
"""M2 - The Ledger.

HANDS feels each tile and is told a plain number (probe only) - never
shown it directly. EYES sees a different, independently-generated number
printed on each tile. BOOK's manual holds the (hands number, eyes number)
-> PRESS/SKIP lookup table.

Three-key rule: satisfied. HANDS alone knows its own numbers but not the
verdict; EYES alone knows its own numbers but not the verdict; BOOK alone
knows the table but neither set of numbers.

The "braille" flavour is purely decorative dot art drawn client-side from
the tile's own slot index - nothing meaningful is encoded in it, and the
server never sends any dot data at all. See AGENTS.md T14 (updated from the
original "decode the alphabet" idea - a plain revealed number reads aloud
far better than describing raised dots).
"""
import html
import random

from .base import Layout, Module, Result, Slot, Views, register

VALUES = list(range(1, 7))  # 1..6 - same axis scale as M1's 6x6 table
VERDICTS = ["PRESS", "SKIP"]


@register
class Ledger(Module):
    id = "m02"
    name = "The Ledger"

    def generate(self, rng: random.Random, flags: dict) -> None:
        n = 6
        self.tiles = [
            {"hands_value": rng.choice(VALUES), "eyes_value": rng.choice(VALUES),
             "resolved": False}
            for _ in range(n)
        ]
        self.table = {hv: {ev: rng.choice(VERDICTS) for ev in VALUES} for hv in VALUES}

        # Reuses the existing EYES "badge" flag - no new global flag needed.
        # Mirrors M1's greasy-casing swap.
        self.swap = flags.get("badge") == "red"

        # Guard against a degenerate all-one-verdict round, same spirit as
        # M1's "force at least one CUT" fallback - without this a run of bad
        # luck could make every tile the same action, which is technically
        # solvable but a flat, boring round.
        #
        # _verdict() already applies self.swap, but this write goes into the
        # pre-swap self.table - writing the post-swap value straight back
        # would get flipped AGAIN the next time _verdict() reads it whenever
        # self.swap is True, silently failing to break the tie (or in some
        # cases undoing itself). Working out what to store here needs to
        # account for that: if swap is on, store the value that becomes the
        # opposite verdict *after* one flip, which is the same-looking
        # "only" value - see the swap-inversion table in the code review
        # notes for this ticket if this ever needs re-deriving.
        verdicts_in_play = {self._verdict(i) for i in range(n)}
        if len(verdicts_in_play) == 1:
            only = next(iter(verdicts_in_play))
            flipped = "SKIP" if only == "PRESS" else "PRESS"
            raw_value = only if self.swap else flipped
            t = self.tiles[0]
            self.table[t["hands_value"]][t["eyes_value"]] = raw_value

        self.solved = False

    def _verdict(self, i: int) -> str:
        t = self.tiles[i]
        v = self.table[t["hands_value"]][t["eyes_value"]]
        if self.swap:
            v = {"PRESS": "SKIP", "SKIP": "PRESS"}[v]
        return v

    def solution(self) -> dict[int, str]:
        """Correct action per tile. Testbenches only. Never sent to any client."""
        return {i: self._verdict(i) for i in range(len(self.tiles))}

    def act(self, role: str, action: dict) -> Result:
        if role != "hands" or self.solved:
            return Result.NOTHING

        if "press" in action:
            i, guess = int(action["press"]), "PRESS"
        elif "skip" in action:
            i, guess = int(action["skip"]), "SKIP"
        else:
            return Result.NOTHING

        if not (0 <= i < len(self.tiles)) or self.tiles[i]["resolved"]:
            return Result.NOTHING

        if guess != self._verdict(i):
            return Result.STRIKE

        self.tiles[i]["resolved"] = True
        if all(t["resolved"] for t in self.tiles):
            self.solved = True
            return Result.SOLVED
        return Result.NOTHING

    def inspect(self, role: str, query: dict) -> dict:
        if role != "hands" or "cell" not in query:
            return {}
        i = int(query["cell"])
        if not (0 <= i < len(self.tiles)):
            return {}
        t = self.tiles[i]
        bits = ["reads %d" % t["hands_value"]]
        if t["resolved"]:
            bits.append("done")
        return {"cell": i, "text": ", ".join(bits)}

    def views(self) -> Views:
        return Views(
            hands={"kind": "ledger", "count": len(self.tiles),
                   "resolved": [t["resolved"] for t in self.tiles],
                   "solved": self.solved},
            eyes={"kind": "ledger",
                  "tiles": [{"value": t["eyes_value"], "resolved": t["resolved"]} for t in self.tiles],
                  "solved": self.solved},
            book={"kind": "manual", "module": self.name, "solved": self.solved},
            scope={"kind": "netlist", "count": len(self.tiles), "nets": [], "solved": self.solved},
        )

    def layout(self) -> Layout:
        # 3x2 grid of tiles. Position only - no value or verdict, so this is
        # safe to send identically to every role.
        n = len(self.tiles)
        cols = 3
        slots = [Slot(idx=i, kind="tile", x=(i % cols + 0.5) / cols, y=(i // cols + 0.5) / 2)
                 for i in range(n)]
        return Layout(w=cols, h=2, slots=slots)

    def manual_page(self) -> str:
        head = "".join("<th>%d</th>" % ev for ev in VALUES)
        rows = ""
        for hv in VALUES:
            cells = "".join('<td class="v-%s">%s</td>' % (self.table[hv][ev].lower(), self.table[hv][ev])
                            for ev in VALUES)
            rows += "<tr><th>%d</th>%s</tr>" % (hv, cells)
        notes = [
            "HANDS reads the number they feel on a tile aloud; EYES reads the number printed on "
            "that same tile aloud. Cross-reference HANDS' number (rows) against EYES' number "
            "(columns) below.",
            "If the badge is <b>red</b>, swap every PRESS and SKIP entry.",
            "Every tile must be explicitly pressed or skipped - guessing wrong is a strike.",
        ]
        return ('<section class="module"><h2>%s</h2>'
                '<table class="rules"><tr><th>HANDS \\ EYES</th>%s</tr>%s</table>'
                '<ol class="notes">%s</ol></section>'
                % (html.escape(self.name), head, rows,
                   "".join("<li>%s</li>" % note for note in notes)))
