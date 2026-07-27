
"""Testbench for N1 - The Vent, and for the needy-module win-check itself
(T15's Bomb._settle() change - see the session's plan notes on why this was
needed: needy modules never "solve," so they must be excluded from the
all-modules-solved win check, guarded against the vacuous-truth all([])==True
case when every module in the bomb happens to be needy).
"""
import json
import random

from server.bomb import Bomb
from server.modules.base import Result
from server.modules.n01_vent import N_VENTS, PURGE_WINDOW_S, Vent

POOL = ["n01"]


def test_needy_only_bomb_can_never_be_won():
    bomb = Bomb(1, module_count=2, pool=POOL)
    # Tend it perfectly for a long simulated stretch - correct purges only,
    # never missing a window.
    for _ in range(30):
        for m in bomb.modules:
            while m.active is None:
                m.tick(1.0)
            m.act("blind", {"purge": m.table[m.active]})
        bomb._settle(Result.NOTHING)
    assert bomb.phase == "running", \
        "an all-needy bomb reached %r - it must never be winnable" % bomb.phase


def test_neglecting_the_vent_strikes_through_the_real_bomb_tick_pipeline():
    # Unlike the other tests here (which call Vent.tick()/.act() directly),
    # this one drives everything through Bomb.tick() - the same path
    # Room._loop() actually calls every 0.1s - to prove the wiring between
    # Bomb.tick -> Module.tick -> Bomb._settle is genuinely connected, not
    # just correct in isolation.
    bomb = Bomb(1, module_count=1, pool=POOL, seconds=999.0)
    vent = bomb.modules[0]
    vent.cooldown = 0.05
    assert bomb.strikes == 0
    bomb.tick(0.1)  # crosses the cooldown, activates the vent
    assert vent.active is not None
    bomb.tick(PURGE_WINDOW_S + 1)  # neglect it past its 15s window
    assert bomb.strikes == 1, "Bomb.tick() must propagate the Vent's timeout into a real strike"
    assert bomb.phase == "running", "one strike alone must not end the round"


def test_needy_module_does_not_block_a_win_once_the_real_objective_is_solved():
    bomb = Bomb(1, module_count=2, pool=["m01", "n01"])
    vent = next(m for m in bomb.modules if m.id == "n01")
    m01 = next(m for m in bomb.modules if m.id == "m01")
    assert vent.needy and not m01.needy

    for i in m01.solution():
        if m01.wires[i]["warm"]:
            bomb.act("blind", bomb.modules.index(m01), {"discharge": i})
        bomb.act("blind", bomb.modules.index(m01), {"cut": i})

    assert bomb.phase == "won", \
        "the round should be won once the only non-needy module solves, regardless of the neglected Vent"


def test_settle_does_not_win_on_an_empty_module_list_edge_case():
    # Regression guard for the all([]) == True Python gotcha the T15 fix
    # specifically had to avoid.
    bomb = Bomb(1, module_count=1, pool=POOL)
    bomb.modules = []
    bomb._settle(Result.NOTHING)
    assert bomb.phase == "running"


def test_vent_starts_dormant_and_activates_after_its_cooldown():
    m = Vent()
    m.generate(random.Random(1), {})
    assert m.active is None
    m.cooldown = 0.5
    assert m.tick(0.4) is Result.NOTHING
    assert m.active is None, "must not activate before its own cooldown elapses"
    m.tick(0.2)
    assert m.active is not None, "must activate once cooldown reaches zero"
    assert m.timer == PURGE_WINDOW_S


def test_unpurged_window_strikes_and_resets():
    m = Vent()
    m.generate(random.Random(2), {})
    m.cooldown = 0
    m.tick(0.01)  # activates
    assert m.active is not None
    assert m.tick(PURGE_WINDOW_S + 1) is Result.STRIKE
    assert m.active is None, "a timeout must cool the vent back down"


def test_correct_purge_resets_without_a_strike():
    m = Vent()
    m.generate(random.Random(3), {})
    m.cooldown = 0
    m.tick(0.01)
    target = m.table[m.active]
    assert m.act("blind", {"purge": target}) is not Result.STRIKE
    assert m.active is None, "a correct purge must cool the vent down"


def test_wrong_purge_strikes_but_stays_active_for_a_retry():
    m = Vent()
    m.generate(random.Random(4), {})
    m.cooldown = 0
    m.tick(0.01)
    target = m.table[m.active]
    wrong = next(i for i in range(N_VENTS) if i != target)
    assert m.act("blind", {"purge": wrong}) is Result.STRIKE
    assert m.active is not None, "a wrong purge must NOT reset - the crew should get to retry within the window"
    # Retrying with the correct vent afterwards must still work.
    assert m.act("blind", {"purge": target}) is not Result.STRIKE
    assert m.active is None


def test_purge_while_dormant_is_a_no_op():
    m = Vent()
    m.generate(random.Random(5), {})
    assert m.active is None
    assert m.act("blind", {"purge": 0}) is Result.NOTHING


def test_only_blind_may_purge():
    m = Vent()
    m.generate(random.Random(6), {})
    m.cooldown = 0
    m.tick(0.01)
    target = m.table[m.active]
    for role in ("deaf", "mute", "scope", "dispatch"):
        assert m.act(role, {"purge": target}) is Result.NOTHING


def test_only_blind_can_probe_vent():
    bomb = Bomb(1, module_count=1, pool=POOL)
    assert bomb.inspect("deaf", 0, {"cell": 0}) == {}
    assert bomb.inspect("mute", 0, {"cell": 0}) == {}


def test_probe_reports_warm_only_for_the_active_vent():
    m = Vent()
    m.generate(random.Random(7), {})
    m.cooldown = 0
    m.tick(0.01)
    for i in range(N_VENTS):
        data = m.inspect("blind", {"cell": i})
        expected = "warm" if i == m.active else "cool"
        assert data["text"] == expected


def test_table_is_not_always_the_identity_mapping_across_many_seeds():
    # Confirms the indirection genuinely exists - if every seed happened to
    # map every glow to itself, MUTE's table would be pointless and the
    # module would collapse to "just purge whichever one glows."
    any_non_identity = False
    for seed in range(50):
        m = Vent()
        m.generate(random.Random(seed), {})
        if any(glow != target for glow, target in m.table.items()):
            any_non_identity = True
            break
    assert any_non_identity, "expected at least one seed with a non-identity glow->purge mapping"


def test_blind_view_never_carries_glow_or_table_data():
    for seed in range(100):
        m = Vent()
        m.generate(random.Random(seed), {})
        hv = m.views().blind
        assert set(hv.keys()) == {"kind", "count", "solved"}


def test_deaf_view_never_carries_the_purge_table():
    for seed in range(100):
        m = Vent()
        m.generate(random.Random(seed), {})
        ev = m.views().deaf
        assert set(ev.keys()) == {"kind", "count", "glowing", "solved"}


def test_mute_gets_no_per_vent_state():
    for seed in range(100):
        m = Vent()
        m.generate(random.Random(seed), {})
        bv = m.views().mute
        assert set(bv.keys()) <= {"kind", "module", "solved"}


def test_layout_is_three_vents_with_no_glow_or_table_data():
    bomb = Bomb(1, module_count=1, pool=POOL)
    layout = bomb.snapshot("blind")["layouts"][0]
    assert layout["w"] == N_VENTS and layout["h"] == 1
    assert [s["idx"] for s in layout["slots"]] == list(range(N_VENTS))
    assert all(s["kind"] == "vent" for s in layout["slots"])
    blob = json.dumps(layout)
    for banned in ("glow", "purge", "table", "warm"):
        assert banned not in blob


def test_golden_path_survives_many_cycles_with_zero_strikes():
    for seed in range(30):
        m = Vent()
        m.generate(random.Random(seed), {})
        strikes = 0
        for _ in range(25):
            while m.active is None:
                r = m.tick(1.0)
                if r is Result.STRIKE:
                    strikes += 1
            r = m.act("blind", {"purge": m.table[m.active]})
            if r is Result.STRIKE:
                strikes += 1
        assert strikes == 0, "seed %d: tending every cycle correctly still struck" % seed


def test_manual_lists_all_three_glow_to_purge_entries():
    m = Vent()
    m.generate(random.Random(9), {})
    page = m.manual_page()
    for glow, target in m.table.items():
        assert ("<th>%d</th><td>%d</td>" % (glow + 1, target + 1)) in page
