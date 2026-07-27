
"""Bomb: edge flags, module instances, timer, strikes, role-filtered snapshots."""
import dataclasses
import random
import string

from .modules.base import REGISTRY, Result

CASINGS = ["rough", "smooth", "greasy"]
BADGES = ["red", "blue", "green", "yellow"]
STICKERS = ["ACME", "KOWALSKI", "VOSS"]

# Every role the game currently supports. Defined here (not imported from
# room.py) to avoid a circular import, since Room already imports Bomb.
ALL_ROLES = {"hands", "eyes", "book", "scope", "dispatch"}


class Bomb:
    def __init__(self, seed: int, module_count: int = 2, seconds: float = 300.0,
                 pool: list[str] | None = None, roles: set[str] | None = None,
                 mirror: bool = False):
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

        # Pick modules from the registry rather than hardcoding one. `pool`
        # narrows which ids are in play (defaults to everything registered);
        # `roles` is who's actually connected (defaults to all five) and
        # excludes any module whose requires_roles isn't fully covered - e.g.
        # a hands/eyes/book room must never draw a SCOPE-dependent module.
        roles = ALL_ROLES if roles is None else roles
        candidate_ids = list(REGISTRY.keys()) if pool is None else pool
        eligible = [mid for mid in candidate_ids
                    if REGISTRY[mid].requires_roles <= roles]
        if not eligible:
            raise ValueError(
                "no module in pool %r has its requires_roles satisfied by roles %r"
                % (candidate_ids, sorted(roles)))

        self.modules = []
        for _ in range(module_count):
            cls = REGISTRY[rng.choice(eligible)]
            m = cls()
            m.generate(rng, all_flags)
            self.modules.append(m)

        self.time_left = seconds
        self.strikes = 0
        self.max_strikes = 3
        self.phase = "running"
        # T18: Mirror modifier - see _mirror_index()/_mirror_view() below for
        # the actual transform. Implemented entirely here, not in any module
        # file - every module keeps acting/viewing in its own true, unflipped
        # numbering; Bomb translates HANDS' indices on the way in/out.
        self.mirror = mirror

    def _settle(self, result: Result) -> None:
        if result is Result.STRIKE:
            self.strikes += 1
            if self.strikes >= self.max_strikes:
                self.phase = "lost"
        # T15: needy modules (Module.needy) never "solve" - they just have to
        # be tended for the whole round, so they're excluded from the win
        # check entirely. The `non_needy and` guard matters: all([]) is True
        # in Python, so without it an all-needy round would win on its very
        # first tick.
        non_needy = [m for m in self.modules if not m.needy]
        if non_needy and all(m.solved for m in non_needy):
            self.phase = "won"

    @staticmethod
    def _mirror_index(i: int, count: int) -> int:
        # Involutive: applying this twice with the same count returns the
        # original value, which is what lets inspect() flip a query cell on
        # the way in and flip the very same field back on the way out.
        return count - 1 - i

    def _mirror_action(self, action: dict, count: int) -> dict:
        """T18: flips any in-range integer value in an incoming HANDS action
        dict, using the module's own slot count from layout(). This is
        deliberately generic across every module's differently-named action
        keys (cut/discharge/press/skip/purge/lock) rather than special-casing
        each one, which is what keeps this a Bomb-only change. It relies on
        the convention every current module follows: the only integers a
        HANDS action ever carries are slot indices in range [0, count). A
        future module with some OTHER integer parameter (not a cell index)
        would need this reconsidered - flag it if that ever comes up.
        """
        out = {}
        for k, v in action.items():
            if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < count:
                out[k] = self._mirror_index(v, count)
            else:
                out[k] = v
        return out

    def _mirror_view(self, view: dict, count: int) -> dict:
        """T18: HANDS' own per-cell state arrays (e.g. "cut", "discharged",
        "resolved") are reversed so that whatever HANDS just acted on (using
        their own, already-mirrored index) shows up at the SAME index HANDS
        used - the flip is entirely self-consistent from HANDS' side. Only
        called for the "hands" role's view; EYES/BOOK/SCOPE/DISPATCH never
        pass through here and always see the module's true numbering.
        """
        out = dict(view)
        for k, v in view.items():
            if isinstance(v, list) and len(v) == count:
                out[k] = list(reversed(v))
        return out

    def act(self, role: str, index: int, action: dict) -> Result:
        if self.phase != "running" or not (0 <= index < len(self.modules)):
            return Result.NOTHING
        module = self.modules[index]
        if role == "hands" and self.mirror:
            action = self._mirror_action(action, len(module.layout().slots))
        r = module.act(role, action)
        self._settle(r)
        return r

    def inspect(self, role: str, index: int, query: dict) -> dict:
        if not (0 <= index < len(self.modules)):
            return {}
        module = self.modules[index]
        if role == "hands" and self.mirror and "cell" in query:
            count = len(module.layout().slots)
            true_cell = self._mirror_index(int(query["cell"]), count)
            result = module.inspect(role, {**query, "cell": true_cell})
            if "cell" in result:
                # Flip the true cell back to HANDS' own number, so the probe
                # result HANDS receives still describes "their" cell, not the
                # module's internal one - see _mirror_index()'s involutive note.
                result = {**result, "cell": self._mirror_index(result["cell"], count)}
            return result
        return module.inspect(role, query)

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
        modules_out = []
        for m in self.modules:
            view = m.views().for_role(role)
            if role == "hands" and self.mirror:
                view = self._mirror_view(view, len(m.layout().slots))
            modules_out.append(view)
        return {
            "phase": self.phase,
            "time_left": round(self.time_left, 1),
            "strikes": self.strikes,
            "max_strikes": self.max_strikes,
            "flags": flags,
            "modules": modules_out,
            # WORLD: one shared geometry per module, identical for every role.
            # Kept as its own top-level key (not merged into "modules") so the
            # role-filtered PERCEPTION view above is untouched by this addition.
            # Mirror never touches this - rule 3 says one shared geometry for
            # everyone; only HANDS' own indices into that geometry are flipped.
            "layouts": [dataclasses.asdict(m.layout()) for m in self.modules],
        }

    def manual_html(self) -> str:
        # T17: wraps each module's own manual_page() with a "Module i of N"
        # label and forces a page break before it. This is content-based
        # numbering, not a physical print-page counter - browsers' native
        # print engines don't reliably expose "which physical page am I on"
        # via CSS alone, but "Module 2 of 3" is always correct regardless of
        # how the printer/browser paginates, and satisfies the same need.
        n = len(self.modules)
        pages = []
        for i, m in enumerate(self.modules):
            pages.append(
                '<div class="modpage"><div class="modpage-label">Module %d of %d</div>%s</div>'
                % (i + 1, n, m.manual_page()))
        html = "".join(pages)
        # T18: the ONLY place Mirror is ever disclosed to players - a single
        # match-wide footnote, not per-module text (the modifier applies
        # uniformly to every module's cell numbering, so one note covers all
        # of them). Deliberately vague about exact indices/arithmetic - "count
        # from the other end" is the whole trick, and it's the same trick
        # regardless of how wide any given module happens to be.
        if self.mirror:
            html += ('<p class="mirror-note">&#9888; MIRRORED: every wired, tiled, or vented '
                     "module this round is mirrored for HANDS. Where EYES calls out the Nth "
                     "position counting from their left, HANDS must act on the Nth position "
                     "counting from their own RIGHT instead (and vice versa).</p>")
        return html
