
"""Testbench for N2 - The Handshake, the second needy module. Mirrors
test_vent.py's needy-module conventions, but this module's twist is the
opposite of Vent's: most rounds, the correct action is to do nothing at all,
so a large share of these tests are about confirming restraint is rewarded
just as much as a correct confirm.
"""
import json
import random

from server.bomb import Bomb
from server.modules.base import Result
from server.modules.n02_handshake import WINDOW_S, Handshake

POOL = ["n02"]


def test_hands_view_never_carries_window_or_rule_data():
    for seed in range(100):
        m = Handshake()
        m.generate(random.Random(seed), {})
        hv = m.views().hands
        assert set(hv.keys()) == {"kind", "solved"}, \
            "seed %d: hands view has an unexpected key %r" % (seed, hv.keys())


def test_eyes_view_has_the_window_but_never_the_rule():
    for seed in range(100):
        m = Handshake()
        m.generate(random.Random(seed), {})
        ev = m.views().eyes
        assert set(ev.keys()) == {"kind", "open", "solved"}


def test_book_gets_no_window_or_sticker_state():
    for seed in range(100):
        m = Handshake()
        m.generate(random.Random(seed), {})
        bv = m.views().book
        assert set(bv.keys()) <= {"kind", "module", "solved"}


def test_only_hands_can_probe_handshake():
    bomb = Bomb(1, module_count=1, pool=POOL)
    assert bomb.inspect("eyes", 0, {"cell": 0}) == {}
    assert bomb.inspect("book", 0, {"cell": 0}) == {}


def test_probe_reports_idle_then_syncing_once_the_window_opens():
    m = Handshake()
    m.generate(random.Random(1), {})
    m.cooldown = 0.5
    assert m.inspect("hands", {"cell": 0})["text"] == "idle"
    m.tick(0.4)
    assert m.inspect("hands", {"cell": 0})["text"] == "idle", "must not open before its own cooldown elapses"
    m.tick(0.2)
    assert m.inspect("hands", {"cell": 0})["text"] == "syncing", "must open once cooldown reaches zero"


def test_window_opens_after_cooldown_and_lasts_window_s():
    m = Handshake()
    m.generate(random.Random(2), {})
    m.cooldown = 0
    m.tick(0.01)
    assert m.window_open
    assert m.timer == WINDOW_S


def test_correct_confirm_does_not_strike_and_closes_the_window():
    m = Handshake()
    m.generate(random.Random(3), {"sticker": "KOWALSKI"})
    assert m.should_confirm
    m.cooldown = 0
    m.tick(0.01)
    assert m.act("hands", {"confirm": True}) is not Result.STRIKE
    assert not m.window_open, "a confirm must close the window immediately"


def test_wrong_confirm_strikes_and_still_closes_the_window():
    m = Handshake()
    m.generate(random.Random(4), {"sticker": "ACME"})
    assert not m.should_confirm
    m.cooldown = 0
    m.tick(0.01)
    assert m.act("hands", {"confirm": True}) is Result.STRIKE
    assert not m.window_open


def test_missing_a_required_confirm_strikes_via_tick_timeout():
    m = Handshake()
    m.generate(random.Random(5), {"sticker": "KOWALSKI"})
    m.cooldown = 0
    m.tick(0.01)  # opens
    assert m.tick(WINDOW_S + 1) is Result.STRIKE, "letting a required window expire unconfirmed must strike"
    assert not m.window_open


def test_correctly_restraining_does_not_strike_on_timeout():
    m = Handshake()
    m.generate(random.Random(6), {"sticker": "VOSS"})
    assert not m.should_confirm
    m.cooldown = 0
    m.tick(0.01)  # opens
    assert m.tick(WINDOW_S + 1) is not Result.STRIKE, "letting a do-not-confirm window expire must not strike"
    assert not m.window_open


def test_confirming_outside_a_window_is_a_no_op():
    m = Handshake()
    m.generate(random.Random(7), {"sticker": "KOWALSKI"})
    assert not m.window_open
    assert m.act("hands", {"confirm": True}) is Result.NOTHING


def test_confirming_twice_in_the_same_window_only_counts_once():
    m = Handshake()
    m.generate(random.Random(8), {"sticker": "ACME"})
    m.cooldown = 0
    m.tick(0.01)
    first = m.act("hands", {"confirm": True})
    assert first is Result.STRIKE
    # Window is already closed after the first confirm, so a second attempt
    # in the same instant is just a no-op, not a second strike.
    assert m.act("hands", {"confirm": True}) is Result.NOTHING


def test_only_hands_may_confirm():
    m = Handshake()
    m.generate(random.Random(9), {})
    m.cooldown = 0
    m.tick(0.01)
    for role in ("eyes", "book", "scope", "dispatch"):
        assert m.act(role, {"confirm": True}) is Result.NOTHING
    assert m.window_open, "a non-hands act() must not affect the window at all"


def test_sticker_kowalski_requires_confirmation_any_other_sticker_does_not():
    m1 = Handshake()
    m1.generate(random.Random(10), {"sticker": "KOWALSKI"})
    assert m1.should_confirm is True
    for brand in ("ACME", "VOSS"):
        m2 = Handshake()
        m2.generate(random.Random(10), {"sticker": brand})
        assert m2.should_confirm is False


def test_needy_only_bomb_can_never_be_won():
    bomb = Bomb(1, module_count=2, pool=POOL)
    for _ in range(20):
        for m in bomb.modules:
            while not m.window_open:
                m.tick(1.0)
            m.act("hands", {"confirm": True})
        bomb._settle(Result.NOTHING)
    assert bomb.phase == "running", \
        "an all-needy bomb reached %r - it must never be winnable" % bomb.phase


def test_neglecting_a_required_confirm_strikes_through_the_real_bomb_tick_pipeline():
    # Drives everything through Bomb.tick() - the same path Room._loop()
    # actually calls every 0.1s - to prove the wiring is genuinely connected,
    # not just correct in isolation (mirrors test_vent.py's equivalent test).
    bomb = Bomb(1, module_count=1, pool=POOL, seconds=999.0)
    handshake = bomb.modules[0]
    handshake.should_confirm = True
    handshake.cooldown = 0.05
    assert bomb.strikes == 0
    bomb.tick(0.1)  # crosses the cooldown, opens the window
    assert handshake.window_open
    bomb.tick(WINDOW_S + 1)  # neglect the required confirm past its window
    assert bomb.strikes == 1, "Bomb.tick() must propagate the Handshake's timeout into a real strike"
    assert bomb.phase == "running", "one strike alone must not end the round"


def test_golden_path_survives_many_cycles_with_zero_strikes():
    for seed in range(30):
        m = Handshake()
        m.generate(random.Random(seed), {})
        strikes = 0
        for _ in range(20):
            while not m.window_open:
                r = m.tick(1.0)
                if r is Result.STRIKE:
                    strikes += 1
            if m.should_confirm:
                r = m.act("hands", {"confirm": True})
            else:
                r = m.tick(WINDOW_S + 1)  # correctly let it pass
            if r is Result.STRIKE:
                strikes += 1
        assert strikes == 0, "seed %d: tending every cycle correctly still struck" % seed


def test_layout_is_one_button_slot_with_no_window_or_rule_data():
    bomb = Bomb(11, module_count=1, pool=POOL)
    layout = bomb.snapshot("hands")["layouts"][0]
    assert layout["w"] == 1 and layout["h"] == 1
    assert len(layout["slots"]) == 1
    assert layout["slots"][0]["kind"] == "button"
    blob = json.dumps(layout)
    for banned in ("open", "sticker", "confirm", "kowalski"):
        assert banned not in blob.lower()


def test_manual_states_the_generic_conditional_not_the_resolved_answer():
    # The manual must print the SAME if/then rule regardless of this round's
    # actual should_confirm value - resolving it outright would let BOOK
    # solve without ever hearing EYES' sticker report, breaking the
    # three-key rule.
    m1 = Handshake()
    m1.generate(random.Random(12), {"sticker": "KOWALSKI"})
    m2 = Handshake()
    m2.generate(random.Random(12), {"sticker": "ACME"})
    assert m1.manual_page() == m2.manual_page(), \
        "the printed manual must not depend on this round's actual sticker value"
    assert "KOWALSKI" in m1.manual_page()
