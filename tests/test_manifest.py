
"""Testbench for M4 - The Manifest. Mirrors test_ledger.py/test_gauge.py's
schema-based leak-check style, plus dedicated tests for the ordering
mechanic (distinct from M2's independent per-tile verdicts) and the
step-collision guard that keeps the round's press order unambiguous.
"""
import json
import random

from server.bomb import Bomb
from server.modules.base import Result
from server.modules.m04_manifest import LETTERS, SYMBOLS, Manifest

POOL = ["m04"]


def test_blind_view_never_carries_a_letter_or_step():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        hv = m.views().blind
        assert set(hv.keys()) == {"kind", "count", "pressed", "solved"}, \
            "seed %d: blind view has an unexpected key %r" % (seed, hv.keys())


def test_deaf_view_never_carries_a_symbol_or_step():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        ev = m.views().deaf
        assert set(ev.keys()) == {"kind", "stamps", "solved"}
        for stamp in ev["stamps"]:
            assert set(stamp.keys()) == {"letter", "pressed"}, \
                "seed %d: deaf stamp has an unexpected key %r" % (seed, stamp.keys())
            assert stamp["letter"] in LETTERS


def test_mute_gets_no_stamp_data():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        bv = m.views().mute
        assert set(bv.keys()) <= {"kind", "module", "solved"}


def test_only_blind_can_probe_manifest():
    bomb = Bomb(1, module_count=1, pool=POOL)
    assert bomb.inspect("deaf", 0, {"cell": 0}) == {}
    assert bomb.inspect("mute", 0, {"cell": 0}) == {}


def test_probe_reveals_symbol_as_text():
    bomb = Bomb(1, module_count=1, pool=POOL)
    m = bomb.modules[0]
    data = bomb.inspect("blind", 0, {"cell": 0})
    assert data["text"] == "feels like " + m.stamps[0]["symbol"]


def test_golden_path_solves_every_seed():
    for seed in range(300):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        for i in m.solution():
            assert m.act("blind", {"press": i}) is not Result.STRIKE, \
                "seed %d: pressing in the table's own correct order struck" % seed
        assert m.solved, "seed %d: golden path did not solve" % seed


def test_pressing_out_of_order_strikes():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        order = m.solution()
        if len(order) < 2:
            continue
        assert m.act("blind", {"press": order[1]}) is Result.STRIKE, \
            "seed %d: pressing the second-in-order stamp first did not strike" % seed
        assert not m.stamps[order[1]]["pressed"], "a struck press must not mark the stamp pressed"
        # Recovering with the correct next press must still work afterwards.
        assert m.act("blind", {"press": order[0]}) is not Result.STRIKE


def test_pressing_an_already_pressed_stamp_is_a_no_op():
    m = Bomb(1, module_count=1, pool=POOL).modules[0]
    first = m.solution()[0]
    m.act("blind", {"press": first})
    assert m.act("blind", {"press": first}) is Result.NOTHING, \
        "acting on an already-pressed stamp again must be a no-op, not a second strike"


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


def test_temperature_warm_reverses_the_order():
    # Same seed, only the "temperature" flag differs - mirrors test_ledger.py's
    # badge-swap test. Raw stamps/table must not depend on temperature at all;
    # only the derived press order should reverse.
    for seed in range(300):
        m1 = Manifest()
        m1.generate(random.Random(seed), {"temperature": "cool"})
        m2 = Manifest()
        m2.generate(random.Random(seed), {"temperature": "warm"})

        assert m1.stamps == m2.stamps, "seed %d: stamps must not depend on temperature" % seed
        assert m1.table == m2.table, "seed %d: raw table must not depend on temperature" % seed
        assert m1.reverse is False and m2.reverse is True
        assert m1.solution() == list(reversed(m2.solution())), \
            "seed %d: warm must reverse the press order relative to cool" % seed


def test_steps_are_always_distinct_within_a_round():
    # The collision-avoidance guard: table[][] is filled independently at
    # random per cell, so two stamps could coincidentally land on the same
    # step unless the generator re-rolls one of them.
    for seed in range(500):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        steps = [s["step"] for s in m.stamps]
        assert len(set(steps)) == len(steps), \
            "seed %d: two stamps shared a step, making the press order ambiguous" % seed
        assert sorted(steps) == list(range(1, len(steps) + 1)), \
            "seed %d: steps are not a clean 1..n run" % seed


def test_letters_are_always_distinct_within_a_round():
    for seed in range(300):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        letters = [s["letter"] for s in m.stamps]
        assert len(set(letters)) == len(letters), \
            "seed %d: two stamps shared a letter, making them indistinguishable to DEAF" % seed


def test_stamp_count_is_between_four_and_six():
    for seed in range(300):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        assert 4 <= len(m.stamps) <= 6, "seed %d: unexpected stamp count %d" % (seed, len(m.stamps))


def test_layout_is_a_tile_row_with_no_symbol_letter_or_step_data():
    bomb = Bomb(9, module_count=1, pool=POOL)
    layout = bomb.snapshot("blind")["layouts"][0]
    m = bomb.modules[0]
    assert layout["h"] == 1 and layout["w"] == len(m.stamps)
    assert [s["idx"] for s in layout["slots"]] == list(range(len(m.stamps)))
    assert all(s["kind"] == "tile" for s in layout["slots"])
    assert all(0.0 <= s["x"] <= 1.0 and 0.0 <= s["y"] <= 1.0 for s in layout["slots"])
    blob = json.dumps(layout)
    for banned in SYMBOLS + list(LETTERS) + ["step"]:
        assert banned not in blob


def test_manual_lists_the_full_symbol_by_letter_grid():
    m = Manifest()
    m.generate(random.Random(12), {"temperature": "cool"})
    page = m.manual_page()
    for s in SYMBOLS:
        assert s in page
    for l in LETTERS:
        assert ("<th>%s</th>" % l) in page
    assert "descending" not in page.lower()


def test_manual_notes_the_reversal_only_when_warm():
    m = Manifest()
    m.generate(random.Random(13), {"temperature": "warm"})
    assert "descending" in m.manual_page().lower()
