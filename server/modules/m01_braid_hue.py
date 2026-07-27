
"""M1 - Braid & Hue.

BLIND feels texture + warmth (probe only).
DEAF sees colour + which wire feeds the LED.
MUTE holds the texture x colour rule table and the generated footnotes.
Three-key rule: satisfied. No two roles can solve this without the third.
"""
import html
import random

from .base import Layout, Module, Result, Slot, Views, register

TEXTURES = ["braided", "ribbed", "smooth", "frayed", "sticky", "glassy"]
COLOURS = ["red", "blue", "yellow", "white", "black", "green"]
VERDICTS = ["CUT", "LEAVE", "LAST"]


@register
class BraidHue(Module):
    id = "m01"
    name = "Braid & Hue"

    def generate(self, rng: random.Random, flags: dict) -> None:
        n = rng.randint(3, 6)
        self.wires = [
            {"texture": rng.choice(TEXTURES), "colour": rng.choice(COLOURS),
             "warm": False, "cut": False, "discharged": False}
            for _ in range(n)
        ]
        rng.choice(self.wires)["warm"] = True
        self.table = {t: {c: rng.choice(VERDICTS) for c in COLOURS} for t in TEXTURES}
        self.led_wire = rng.randrange(n)

        self.swap = flags.get("casing") == "greasy"
        self.reverse_last = any(ch in "AEIOU" for ch in flags.get("serial", ""))

        self.nets = []
        if n >= 4:
            a, b = rng.sample(range(n), 2)
            self.nets.append([a, b])

        if not any(self._verdict(i) in ("CUT", "LAST") for i in range(n)):
            w = self.wires[0]
            self.table[w["texture"]][w["colour"]] = "LEAVE" if self.swap else "CUT"

        self.solved = False

    def _verdict(self, i: int) -> str:
        w = self.wires[i]
        v = self.table[w["texture"]][w["colour"]]
        if self.swap:
            v = {"CUT": "LEAVE", "LEAVE": "CUT"}.get(v, v)
        return v

    def _last_order(self) -> list[int]:
        order = [i for i in range(len(self.wires)) if self._verdict(i) == "LAST"]
        return list(reversed(order)) if self.reverse_last else order

    def solution(self) -> list[int]:
        """Full legal cut sequence. Testbenches only. Never sent to any client."""
        plain = [i for i in range(len(self.wires)) if self._verdict(i) == "CUT"]
        return plain + self._last_order()

    def act(self, role: str, action: dict) -> Result:
        if role != "blind" or self.solved:
            return Result.NOTHING

        if "discharge" in action:
            i = int(action["discharge"])
            if 0 <= i < len(self.wires):
                self.wires[i]["discharged"] = True
            return Result.NOTHING

        if "cut" not in action:
            return Result.NOTHING
        i = int(action["cut"])
        if not (0 <= i < len(self.wires)) or self.wires[i]["cut"]:
            return Result.NOTHING

        w, v = self.wires[i], self._verdict(i)
        if w["warm"] and not w["discharged"]:
            return Result.STRIKE
        if v == "LEAVE":
            return Result.STRIKE

        pending_plain = [j for j in range(len(self.wires))
                         if self._verdict(j) == "CUT" and not self.wires[j]["cut"]]
        if v == "CUT" and any(self.wires[j]["cut"] for j in self._last_order()):
            return Result.STRIKE
        if v == "LAST":
            if pending_plain:
                return Result.STRIKE
            pending_last = [j for j in self._last_order() if not self.wires[j]["cut"]]
            if pending_last and pending_last[0] != i:
                return Result.STRIKE

        w["cut"] = True
        if all(self.wires[j]["cut"] for j in self.solution()):
            self.solved = True
            return Result.SOLVED
        return Result.NOTHING

    def inspect(self, role: str, query: dict) -> dict:
        if role != "blind" or "cell" not in query:
            return {}
        i = int(query["cell"])
        if not (0 <= i < len(self.wires)):
            return {}
        w = self.wires[i]
        bits = [w["texture"]]
        if w["warm"]:
            bits.append("warm")
        if w["discharged"]:
            bits.append("discharged")
        if w["cut"]:
            bits.append("severed")
        return {"cell": i, "text": ", ".join(bits)}

    def views(self) -> Views:
        return Views(
            blind={"kind": "wires", "count": len(self.wires),
                   "cut": [w["cut"] for w in self.wires],
                   "discharged": [w["discharged"] for w in self.wires],
                   "solved": self.solved},
            deaf={"kind": "wires",
                  "wires": [{"colour": w["colour"], "cut": w["cut"]} for w in self.wires],
                  "led_wire": self.led_wire, "solved": self.solved},
            mute={"kind": "manual", "module": self.name, "solved": self.solved},
            scope={"kind": "netlist", "count": len(self.wires),
                   "nets": self.nets, "solved": self.solved},
        )

    def layout(self) -> Layout:
        # One row of evenly spaced wire slots. Position only - no colour,
        # texture or verdict, so this is safe to send identically to every role.
        n = len(self.wires)
        slots = [Slot(idx=i, kind="wire", x=(i + 0.5) / n, y=0.5) for i in range(n)]
        return Layout(w=n, h=1, slots=slots)

    def manual_page(self) -> str:
        head = "".join("<th>%s</th>" % c for c in COLOURS)
        rows = ""
        for t in TEXTURES:
            cells = "".join('<td class="v-%s">%s</td>'
                            % (self.table[t][c].lower(), self.table[t][c]) for c in COLOURS)
            rows += "<tr><th>%s</th>%s</tr>" % (t, cells)
        notes = [
            "The <b>warm</b> wire must be discharged (hold D for 2s) before cutting, "
            "whatever the table says.",
            "If the casing is <b>greasy</b>, swap every CUT and LEAVE entry.",
            "If the serial code contains a <b>vowel</b>, resolve LAST entries in reverse order.",
            "Every CUT wire is cut before any LAST wire. Out of order is a strike.",
        ]
        return ('<section class="module"><h2>%s</h2>'
                '<table class="rules"><tr><th></th>%s</tr>%s</table>'
                '<ol class="notes">%s</ol></section>'
                % (html.escape(self.name), head, rows,
                   "".join("<li>%s</li>" % n for n in notes)))
