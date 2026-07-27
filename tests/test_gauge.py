
"""Testbench for M3 - Gauge & Detents. Mirrors test_ledger.py/test_vent.py's
schema-based leak-check style, plus dedicated wrap-around and degenerate-round
guard tests specific to this module's continuous-position mechanic.
"""
import json
import random

from server.bomb import Bomb
from server.modules.base import Result
from server.modules.m03_gauge import N_POSITIONS, Gauge

POOL = ["m03"]


def test_blind_view_never_carries_position_or_zone_data():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        hv = m.views().blind
        assert set(hv.keys()) == {"kind", "solved"}, \
            "seed %d: blind view has an unexpected key %r" % (seed, hv.keys())


def test_deaf_view_has_position_but_never_the_zone():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        ev = m.views().deaf
        assert set(ev.keys()) == {"kind", "position", "count", "solved"}
        assert 0 <= ev["position"] < N_POSITIONS


def test_mute_gets_no_position_data():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=POOL).modules[0]
        bv = m.views().mute
        assert set(bv.keys()) <= {"kind", "module", "solved"}


def test_only_blind_can_probe_gauge():
    bomb = Bomb(1, module_count=1, pool=POOL)
    assert bomb.inspect("deaf", 0, {"cell": 0}) == {}
    assert bomb.inspect("mute", 0, {"cell": 0}) == {}


def test_only_blind_may_act():
    m = Bomb(3, module_count=1, pool=POOL).modules[0]
    for role in ("deaf", "mute", "scope", "dispatch"):
        assert m.act(role, {"turn": "cw"}) is Result.NOTHING
        assert m.act(role, {"lock": 0}) is Result.NOTHING


def test_turning_cw_wraps_from_the_top_to_zero():
    m = Gauge()
    m.generate(random.Random(1), {})
    m.position = N_POSITIONS - 1
    m.act("blind", {"turn": "cw"})
    assert m.position == 0


def test_turning_ccw_wraps_from_zero_to_the_top():
    m = Gauge()
    m.generate(random.Random(2), {})
    m.position = 0
    m.act("blind", {"turn": "ccw"})
    assert m.position == N_POSITIONS - 1


def test_turning_never_strikes_regardless_of_position():
    m = Gauge()
    m.generate(random.Random(3), {})
    for _ in range(N_POSITIONS * 3):
        assert m.act("blind", {"turn": "cw"}) is Result.NOTHING


def test_full_lap_returns_to_the_start():
    m = Gauge()
    m.generate(random.Random(4), {})
    start = m.position
    for _ in range(N_POSITIONS):
        m.act("blind", {"turn": "cw"})
    assert m.position == start


def test_lock_inside_zone_solves():
    for seed in range(200):
        m = Gauge()
        m.generate(random.Random(seed), {})
        m.position = m.zone[0]
        assert m.act("blind", {"lock": 0}) is Result.SOLVED, "seed %d" % seed
        assert m.solved


def test_lock_outside_zone_strikes_but_stays_open():
    for seed in range(200):
        m = Gauge()
        m.generate(random.Random(seed), {})
        outside = next(p for p in range(N_POSITIONS) if p not in m.zone)
        m.position = outside
        assert m.act("blind", {"lock": 0}) is Result.STRIKE, "seed %d" % seed
        assert not m.solved
        assert m.position == outside, "a wrong lock must not move the needle"
        # Retrying correctly afterwards must still work.
        m.position = m.zone[0]
        assert m.act("blind", {"lock": 0}) is Result.SOLVED


def test_lock_value_of_zero_is_not_treated_as_falsy():
    # Regression guard: the real client always sends {"lock": <cell>} where
    # cell is 0 (the gauge's only slot) - act() must check "lock" in action,
    # not action.get("lock") truthiness, or every lock attempt would be
    # silently swallowed as a no-op.
    m = Gauge()
    m.generate(random.Random(5), {})
    m.position = m.zone[0]
    assert m.act("blind", {"lock": 0}) is Result.SOLVED


def test_acting_after_solved_is_a_no_op():
    m = Gauge()
    m.generate(random.Random(6), {})
    m.position = m.zone[0]
    m.act("blind", {"lock": 0})
    assert m.solved
    assert m.act("blind", {"turn": "cw"}) is Result.NOTHING
    assert m.act("blind", {"lock": 0}) is Result.NOTHING


def test_starting_position_is_never_already_inside_the_zone():
    # The degenerate-round guard: without it, some seeds would let a
    # zero-turn lock-in solve the module instantly.
    for seed in range(500):
        m = Gauge()
        m.generate(random.Random(seed), {})
        assert m.position not in m.zone, "seed %d: started already inside the target zone" % seed


def test_deep_notch_feels_different_only_at_its_own_position():
    for seed in range(100):
        m = Gauge()
        m.generate(random.Random(seed), {})
        for p in range(N_POSITIONS):
            m.position = p
            data = m.inspect("blind", {"cell": 0})
            expected = "deep click" if p == m.deep_notch else "click"
            assert data["text"] == expected, "seed %d position %d" % (seed, p)


def test_corner_screw_missing_widens_the_zone_to_three():
    m1 = Gauge()
    m1.generate(random.Random(10), {"corner_screw": "present"})
    m2 = Gauge()
    m2.generate(random.Random(10), {"corner_screw": "missing"})
    assert len(m1.zone) == 2
    assert len(m2.zone) == 3


def test_zone_is_contiguous_and_wraps_correctly():
    for seed in range(200):
        m = Gauge()
        m.generate(random.Random(seed), {"corner_screw": "missing"})
        # A 3-wide contiguous run starting at zone[0], mod N_POSITIONS.
        expected = [(m.zone[0] + i) % N_POSITIONS for i in range(3)]
        assert m.zone == expected, "seed %d: zone is not a contiguous wrap-around run" % seed


def test_layout_is_one_dial_slot_with_no_position_or_zone_data():
    bomb = Bomb(7, module_count=1, pool=POOL)
    layout = bomb.snapshot("blind")["layouts"][0]
    assert layout["w"] == 1 and layout["h"] == 1
    assert len(layout["slots"]) == 1
    assert layout["slots"][0]["kind"] == "dial"
    blob = json.dumps(layout)
    for banned in ("zone", "notch", "position"):
        assert banned not in blob


def test_manual_lists_the_target_zone_as_one_indexed_numbers():
    m = Gauge()
    m.generate(random.Random(11), {})
    page = m.manual_page()
    for p in m.zone:
        assert str(p + 1) in page
