
"""Testbench for M5 - The Static. Mirrors test_manifest.py/test_ledger.py's
schema-based leak-check style, plus dedicated tests for the count-vs-threshold
mechanic (an aggregate comparison, unlike every earlier module's per-slot or
per-round table lookup).
"""
import json
import random

from server.bomb import Bomb
from server.modules.base import Result
from server.modules.m05_static import COLOURS, Static

POOL = ["m05"]


def test_blind_view_never_carries_a_colour_or_charge():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        hv = m.views().blind
        assert set(hv.keys()) == {"kind", "count", "pressed", "solved"}, \
            "seed %d: blind view has an unexpected key %r" % (seed, hv.keys())


def test_deaf_view_never_carries_a_charge_or_threshold():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        ev = m.views().deaf
        assert set(ev.keys()) == {"kind", "tiles", "solved"}
        for tile in ev["tiles"]:
            assert set(tile.keys()) == {"colour", "pressed"}, \
                "seed %d: deaf tile has an unexpected key %r" % (seed, tile.keys())
            assert tile["colour"] in COLOURS


def test_mute_gets_no_tile_or_threshold_data():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        bv = m.views().mute
        assert set(bv.keys()) <= {"kind", "module", "solved"}


def test_only_blind_can_probe_static():
    bomb = Bomb(1, module_count=1, pool=POOL)
    assert bomb.inspect("deaf", 0, {"cell": 0}) == {}
    assert bomb.inspect("mute", 0, {"cell": 0}) == {}


def test_probe_reveals_charge_as_text():
    bomb = Bomb(1, module_count=1, pool=POOL)
    m = bomb.modules[0]
    data = bomb.inspect("blind", 0, {"cell": 0})
    expected = "buzzes" if m.tiles[0]["charged"] else "quiet"
    assert data["text"] == expected


def test_golden_path_solves_every_seed():
    for seed in range(300):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        for i in m.solution():
            assert m.act("blind", {"press": i}) is not Result.STRIKE, \
                "seed %d: pressing a solution tile struck" % seed
        assert m.solved, "seed %d: golden path did not solve" % seed


def test_pressing_the_wrong_colour_strikes():
    for seed in range(300):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        target = m._target_colour()
        wrong = next(i for i, t in enumerate(m.tiles) if t["colour"] != target)
        assert m.act("blind", {"press": wrong}) is Result.STRIKE, \
            "seed %d: pressing a non-target-colour tile did not strike" % seed
        assert not m.tiles[wrong]["pressed"]
        # Recovering with the actual solution afterwards must still work.
        for i in m.solution():
            m.act("blind", {"press": i})
        assert m.solved


def test_pressing_an_already_pressed_tile_is_a_no_op():
    m = Bomb(1, module_count=1, pool=POOL).modules[0]
    first = m.solution()[0]
    m.act("blind", {"press": first})
    assert m.act("blind", {"press": first}) is Result.NOTHING, \
        "acting on an already-pressed tile again must be a no-op, not a second strike"


def test_only_blind_may_act():
    m = Bomb(3, module_count=1, pool=POOL).modules[0]
    for role in ("deaf", "mute", "scope", "dispatch"):
        assert m.act(role, {"press": 0}) is Result.NOTHING


def test_acting_after_solved_is_a_no_op():
    m = Bomb(2, module_count=1, pool=POOL).modules[0]
    for i in m.solution():
        m.act("blind", {"press": i})
    assert m.solved
    assert m.act("blind", {"press": 0}) is Result.NOTHING


def test_threshold_is_never_zero_or_the_full_tile_count():
    # The degenerate-round guard: threshold=0 would make "count >= threshold"
    # always true (BLIND's probing becomes irrelevant); threshold=n would make
    # it always false (same problem, the other direction).
    for seed in range(500):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        assert 1 <= m.threshold <= len(m.tiles) - 1, \
            "seed %d: threshold %d is degenerate" % (seed, m.threshold)


def test_both_colours_always_present():
    for seed in range(300):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        colours = {t["colour"] for t in m.tiles}
        assert colours == set(COLOURS), \
            "seed %d: round did not have both colours present" % seed


def test_target_colour_matches_the_threshold_comparison():
    for seed in range(300):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        buzzing = sum(1 for t in m.tiles if t["charged"])
        expected = m.reaches_colour if buzzing >= m.threshold else m.otherwise_colour
        assert m._target_colour() == expected, "seed %d" % seed


def test_solution_is_exactly_the_target_colour_tiles():
    for seed in range(300):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        target = m._target_colour()
        expected = [i for i, t in enumerate(m.tiles) if t["colour"] == target]
        assert m.solution() == expected, "seed %d" % seed


def test_layout_is_a_3x2_tile_grid_with_no_colour_or_charge_data():
    bomb = Bomb(9, module_count=1, pool=POOL)
    layout = bomb.snapshot("blind")["layouts"][0]
    assert layout["w"] == 3 and layout["h"] == 2
    assert [s["idx"] for s in layout["slots"]] == list(range(6))
    assert all(s["kind"] == "tile" for s in layout["slots"])
    blob = json.dumps(layout)
    for banned in COLOURS + ["charged", "threshold"]:
        assert banned not in blob


def test_manual_states_both_candidate_colours_and_the_rule():
    m = Static()
    m.generate(random.Random(11), {"leds": 2})
    page = m.manual_page()
    assert m.reaches_colour.upper() in page
    assert m.otherwise_colour.upper() in page
    assert "LED" in page


def test_leds_flag_sets_the_threshold_before_clamping():
    m = Static()
    m.generate(random.Random(12), {"leds": 2})
    assert m.threshold == 2  # within [1, 5], no clamping needed for this value


def test_manual_matches_the_server_when_no_leds_are_lit():
    # The server clamps a zero LED count up to a threshold of one; the manual
    # used to say only "the LED count", so a round with zero LEDs and zero
    # buzzing tiles was solvable on paper (0 >= 0) but struck in play.
    m = Static()
    m.generate(random.Random(4), {"leds": 0})
    for t in m.tiles:
        t["charged"] = False
    assert "zero lit LEDs as one" in m.manual_page()
    assert all(m.tiles[i]["colour"] == m.otherwise_colour for i in m.solution())

    m2 = Static()
    m2.generate(random.Random(12), {"leds": 0})
    assert m2.threshold == 1  # clamped up from the degenerate 0
