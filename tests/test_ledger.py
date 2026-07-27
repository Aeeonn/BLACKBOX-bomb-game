
"""Testbench for M2 - The Ledger. Mirrors test_m01.py's golden-path/strike
style, plus a dedicated schema-based leak check (see test_invariants.py's
docstring on why this matters) - Ledger's secret data is plain integers, and
integers don't have the distinctive-word property that lets test_invariants.py
grep for "colour"/"texture" safely, so a string-containment check would be
unreliable here. Checking the actual dict KEYS on each view is precise
regardless of what the numbers happen to be.
"""
import json
import random

from server.bomb import Bomb
from server.modules.base import Result
from server.modules.m02_ledger import Ledger

POOL = ["m02"]


def test_blind_view_never_carries_a_per_tile_value():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        hv = m.views().blind
        assert set(hv.keys()) == {"kind", "count", "resolved", "solved"}, \
            "seed %d: blind view has an unexpected key %r" % (seed, hv.keys())


def test_deaf_view_never_carries_blind_value():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        ev = m.views().deaf
        assert set(ev.keys()) == {"kind", "tiles", "solved"}
        for tile in ev["tiles"]:
            assert set(tile.keys()) == {"value", "resolved"}, \
                "seed %d: deaf tile has an unexpected key %r" % (seed, tile.keys())


def test_mute_gets_no_tile_values():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        bv = m.views().mute
        assert set(bv.keys()) <= {"kind", "module", "solved"}


def test_only_blind_can_probe_ledger():
    bomb = Bomb(1, module_count=1, pool=POOL)
    assert bomb.inspect("deaf", 0, {"cell": 0}) == {}
    assert bomb.inspect("mute", 0, {"cell": 0}) == {}


def test_probe_reveals_blind_value_as_text():
    bomb = Bomb(1, module_count=1, pool=POOL)
    m = bomb.modules[0]
    data = bomb.inspect("blind", 0, {"cell": 0})
    assert data["text"] == "reads %d" % m.tiles[0]["blind_value"]


def test_golden_path_solves_every_seed():
    for seed in range(300):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        for i, verdict in m.solution().items():
            action = {"press": i} if verdict == "PRESS" else {"skip": i}
            assert m.act("blind", action) is not Result.STRIKE, \
                "seed %d: the table's own correct verdict struck" % seed
        assert m.solved, "seed %d: golden path did not solve" % seed


def test_wrong_guess_strikes():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        verdict = m.solution()[0]
        wrong_action = {"skip": 0} if verdict == "PRESS" else {"press": 0}
        assert m.act("blind", wrong_action) is Result.STRIKE, \
            "seed %d: wrong guess on tile 0 did not strike" % seed


def test_resolving_a_tile_twice_is_a_no_op():
    m = Bomb(1, module_count=1, pool=POOL).modules[0]
    verdict = m.solution()[0]
    action = {"press": 0} if verdict == "PRESS" else {"skip": 0}
    m.act("blind", action)
    assert m.act("blind", action) is Result.NOTHING, \
        "acting on an already-resolved tile again must be a no-op, not a second strike"


def test_only_blind_may_act():
    m = Bomb(3, module_count=1, pool=POOL).modules[0]
    for role in ("deaf", "mute", "scope", "dispatch"):
        assert m.act(role, {"press": 0}) is Result.NOTHING


def test_badge_red_swaps_the_table():
    # Same seed, only the "badge" flag differs - the swap flips every
    # tile's verdict, so the two solutions must be each other's opposite,
    # and the RAW table generation must never depend on the swap flag at
    # all (mirrors M1: self.table is built from rng before self.swap is even
    # read). Looped over many seeds because the degenerate-guard's
    # swap-inversion logic only actually gets exercised on the seeds where
    # it fires - a single seed isn't enough to trust the fix broadly.
    for seed in range(300):
        m1 = Ledger()
        m1.generate(random.Random(seed), {"badge": "blue"})
        m2 = Ledger()
        m2.generate(random.Random(seed), {"badge": "red"})

        assert m1.tiles == m2.tiles, "seed %d: tiles must not depend on badge" % seed
        assert m1.table == m2.table, "seed %d: raw table must not depend on badge" % seed
        assert m1.swap is False and m2.swap is True
        for i in range(6):
            assert m1._verdict(i) != m2._verdict(i), \
                "seed %d tile %d: badge=red must flip the verdict relative to badge=blue" % (seed, i)


def test_layout_is_a_3x2_tile_grid_with_no_verdict_data():
    bomb = Bomb(5, module_count=1, pool=POOL)
    layout = bomb.snapshot("blind")["layouts"][0]
    assert layout["w"] == 3 and layout["h"] == 2
    assert [s["idx"] for s in layout["slots"]] == list(range(6))
    assert all(s["kind"] == "tile" for s in layout["slots"])
    assert all(0.0 <= s["x"] <= 1.0 and 0.0 <= s["y"] <= 1.0 for s in layout["slots"])
    blob = json.dumps(layout)
    for banned in ("press", "skip", "value"):
        assert banned not in blob
