
"""M4 - The Manifest.

HANDS feels each stamp and is told a private SYMBOL (probe only). EYES sees a
public LETTER printed on that same stamp. BOOK's manual holds the full
symbol x letter -> step-number grid. The whole set of stamps must be pressed
in ascending step order (lowest first) - unlike M2's independent per-tile
PRESS/SKIP, this is a full ordering across every stamp in play, closer in
spirit to M1's CUT-before-LAST rule but generalised to the entire set rather
than just a "last" subset.

Three-key rule: satisfied. HANDS alone knows symbols but not letters or the
table; EYES alone knows letters but not symbols or the table; BOOK alone
knows the table but neither the symbols nor letters actually in play this
round.
"""
import html
import random

from .base import Layout, Module, Result, Slot, Views, register

SYMBOLS = ["anchor", "clover", "spade", "diamond", "star", "crescent"]
LETTERS = "ABCDEF"


@register
class Manifest(Module):
    id = "m04"
    name = "The Manifest"

    def generate(self, rng: random.Random, flags: dict) -> None:
        n = rng.randint(4, 6)
        letters = rng.sample(LETTERS, n)
        self.table = {s: {l: rng.randint(1, n) for l in LETTERS} for s in SYMBOLS}

        # Reuses the existing HANDS "temperature" flag rather than inventing
        # a new one - mirrors M1's casing-swap / M2's badge-swap / M3's
        # corner-screw-width twists.
        self.reverse = flags.get("temperature") == "warm"

        # Every stamp needs a DISTINCT step 1..n so the press order is a
        # total, unambiguous ordering. table[][] is filled independently at
        # random per cell, so two stamps could collide on the same step by
        # chance - reroll just the SYMBOL half of the offending stamp (the
        # letter is already fixed and unique per stamp) until its step is
        # free. Bounded retry, same spirit as M2's degenerate-round guard;
        # the rare exhaustion fallback force-writes the table cell so the
        # printed manual always stays self-consistent with what was assigned.
        self.stamps = []
        used_steps: set[int] = set()
        for i in range(n):
            symbol, step = None, None
            for _ in range(200):
                symbol = rng.choice(SYMBOLS)
                step = self.table[symbol][letters[i]]
                if step not in used_steps:
                    break
            else:
                step = next(s for s in range(1, n + 1) if s not in used_steps)
                self.table[symbol][letters[i]] = step
            used_steps.add(step)
            self.stamps.append({"symbol": symbol, "letter": letters[i],
                                 "step": step, "pressed": False})

        self.solved = False

    def _order(self) -> list[int]:
        idx = sorted(range(len(self.stamps)), key=lambda i: self.stamps[i]["step"])
        return list(reversed(idx)) if self.reverse else idx

    def solution(self) -> list[int]:
        """Correct press order. Testbenches only. Never sent to any client."""
        return self._order()

    def act(self, role: str, action: dict) -> Result:
        if role != "hands" or self.solved:
            return Result.NOTHING
        if "press" not in action:
            return Result.NOTHING
        i = int(action["press"])
        if not (0 <= i < len(self.stamps)) or self.stamps[i]["pressed"]:
            return Result.NOTHING

        pending = [j for j in self._order() if not self.stamps[j]["pressed"]]
        if not pending or pending[0] != i:
            return Result.STRIKE

        self.stamps[i]["pressed"] = True
        if all(s["pressed"] for s in self.stamps):
            self.solved = True
            return Result.SOLVED
        return Result.NOTHING

    def inspect(self, role: str, query: dict) -> dict:
        if role != "hands" or "cell" not in query:
            return {}
        i = int(query["cell"])
        if not (0 <= i < len(self.stamps)):
            return {}
        s = self.stamps[i]
        bits = ["feels like " + s["symbol"]]
        if s["pressed"]:
            bits.append("stamped")
        return {"cell": i, "text": ", ".join(bits)}

    def views(self) -> Views:
        return Views(
            hands={"kind": "manifest", "count": len(self.stamps),
                   "pressed": [s["pressed"] for s in self.stamps], "solved": self.solved},
            eyes={"kind": "manifest",
                  "stamps": [{"letter": s["letter"], "pressed": s["pressed"]} for s in self.stamps],
                  "solved": self.solved},
            book={"kind": "manual", "module": self.name, "solved": self.solved},
            scope={"kind": "netlist", "count": len(self.stamps), "nets": [], "solved": self.solved},
        )

    def layout(self) -> Layout:
        # One row of evenly spaced stamp slots. Position only - no symbol,
        # letter or step, so this is safe to send identically to every role.
        n = len(self.stamps)
        slots = [Slot(idx=i, kind="tile", x=(i + 0.5) / n, y=0.5) for i in range(n)]
        return Layout(w=n, h=1, slots=slots)

    def manual_page(self) -> str:
        head = "".join("<th>%s</th>" % l for l in LETTERS)
        rows = ""
        for s in SYMBOLS:
            cells = "".join("<td>%d</td>" % self.table[s][l] for l in LETTERS)
            rows += "<tr><th>%s</th>%s</tr>" % (s, cells)
        notes = [
            "HANDS describes the symbol felt on each stamp out loud (e.g. \"this one feels like "
            "an anchor\"). EYES reads off the printed letter on that same stamp.",
            "Cross-reference HANDS' symbol (rows) against EYES' letter (columns) below to get "
            "that stamp's step number.",
            "Press every stamp in ascending step order, lowest number first. Pressing out of "
            "order is a strike and does not un-press anything already correctly stamped.",
        ]
        if self.reverse:
            notes.append("If it feels <b>warm</b> to the touch, press in descending step order "
                          "instead - highest number first.")
        return ('<section class="module"><h2>%s</h2>'
                '<table class="rules"><tr><th>Symbol \\ Letter</th>%s</tr>%s</table>'
                '<ol class="notes">%s</ol></section>'
                % (html.escape(self.name), head, rows,
                   "".join("<li>%s</li>" % n for n in notes)))
