
"""Testbench for T18 - the Mirror modifier.

Mirror is implemented ENTIRELY in Bomb (server/bomb.py) - zero changes to
any module file. Bomb flips HANDS' in-range integer action/query values
using each module's own layout() slot count, and reverses HANDS' own
per-cell view arrays so HANDS' own screen stays self-consistent (whatever
HANDS just acted on shows up at the SAME index HANDS used). EYES/BOOK/SCOPE
always see the module's true, unflipped numbering - only HANDS' own
perspective is shifted. See AGENTS.md T18 for the design rationale.
"""
import asyncio

from server.bomb import Bomb
from server.modules.base import Result
from server.room import Room


class _DummySocket:
    async def send_json(self, msg):
        pass


def test_mirror_defaults_to_off_and_changes_nothing():
    bomb = Bomb(1, module_count=2, pool=["m01"])
    assert bomb.mirror is False


def test_act_flips_hands_index_before_reaching_the_module():
    bomb = Bomb(1, module_count=1, pool=["m01"], mirror=True)
    m = bomb.modules[0]
    count = len(m.layout().slots)
    # solution()[0] is guaranteed immediately legal to cut (the module's own
    # CUT-then-LAST ordering rules mean an arbitrary cell, e.g. the true
    # last cell, may require other cells cut first - using a hardcoded index
    # here would risk a legitimate STRIKE unrelated to mirroring at all).
    true_target = m.solution()[0]
    hands_target = count - 1 - true_target
    if m.wires[true_target]["warm"]:
        bomb.act("hands", 0, {"discharge": hands_target})
    bomb.act("hands", 0, {"cut": hands_target})
    assert m.wires[true_target]["cut"] is True
    untouched = [i for i in range(count) if i != true_target]
    assert all(not m.wires[i]["cut"] for i in untouched), "only the true target cell should be cut"


def test_inspect_flips_query_in_and_cell_field_back_out():
    bomb = Bomb(1, module_count=1, pool=["m01"], mirror=True)
    m = bomb.modules[0]
    count = len(m.layout().slots)
    true_last = m.wires[count - 1]

    result = bomb.inspect("hands", 0, {"cell": 0})
    # HANDS asked about "cell 0" and must be told "cell 0" back, even though
    # the module was actually queried about its true last cell.
    assert result["cell"] == 0
    assert true_last["texture"] in result["text"]


def test_hands_view_is_self_consistent_after_mirrored_action():
    # The crux of the whole feature: HANDS clicks a cell, and afterward
    # HANDS' OWN view must show THAT SAME cell (not some other index) as
    # cut - otherwise the flip would look like a visible client bug to
    # HANDS rather than an invisible-to-HANDS twist.
    bomb = Bomb(1, module_count=1, pool=["m01"], mirror=True)
    m = bomb.modules[0]
    count = len(m.layout().slots)
    true_target = m.solution()[0]
    hands_target = count - 1 - true_target
    if m.wires[true_target]["warm"]:
        bomb.act("hands", 0, {"discharge": hands_target})
    bomb.act("hands", 0, {"cut": hands_target})

    hv = bomb.snapshot("hands")["modules"][0]
    assert hv["cut"][hands_target] is True, \
        "HANDS' own cell %d must show as cut after HANDS cut cell %d" % (hands_target, hands_target)
    others = [i for i in range(count) if i != hands_target]
    assert all(not hv["cut"][i] for i in others), "no other HANDS-perspective cell should show as cut"


def test_eyes_view_is_never_affected_by_mirror():
    bomb = Bomb(1, module_count=1, pool=["m01"], mirror=True)
    m = bomb.modules[0]
    count = len(m.layout().slots)
    true_target = m.solution()[0]
    hands_target = count - 1 - true_target
    if m.wires[true_target]["warm"]:
        bomb.act("hands", 0, {"discharge": hands_target})
    bomb.act("hands", 0, {"cut": hands_target})

    ev = bomb.snapshot("eyes")["modules"][0]
    assert ev["wires"][true_target]["cut"] is True, "EYES must see the TRUE cell that was actually cut"
    others = [i for i in range(count) if i != true_target]
    assert all(not ev["wires"][i]["cut"] for i in others)


def test_book_and_scope_views_are_never_affected_by_mirror():
    bomb_mirror = Bomb(7, module_count=2, pool=["m01"], mirror=True)
    bomb_plain = Bomb(7, module_count=2, pool=["m01"], mirror=False)
    assert bomb_mirror.snapshot("book") == bomb_plain.snapshot("book")
    assert bomb_mirror.snapshot("scope") == bomb_plain.snapshot("scope")
    assert bomb_mirror.snapshot("dispatch") == bomb_plain.snapshot("dispatch")


def test_flip_is_involutive_round_trip_matches_seed_for_seed():
    # Same seed => same wires/table regardless of mirror (mirror only
    # affects how indices are TRANSLATED, never module generation itself).
    bomb_mirror = Bomb(9, module_count=1, pool=["m01"], mirror=True)
    bomb_plain = Bomb(9, module_count=1, pool=["m01"], mirror=False)
    assert bomb_mirror.modules[0].wires == bomb_plain.modules[0].wires
    assert bomb_mirror.modules[0].table == bomb_plain.modules[0].table


def test_golden_path_solves_with_mirrored_indices_translated_by_a_real_player():
    # Simulates what an informed crew would actually do: take the module's
    # TRUE solution() order (which is what BOOK's manual rules resolve to),
    # translate each true index to "HANDS' own number" (the inverse flip),
    # and send THAT to bomb.act() - proving the whole pipeline is consistent
    # end-to-end, not just for a single cut.
    for seed in range(100):
        bomb = Bomb(seed, module_count=1, pool=["m01"], mirror=True)
        m = bomb.modules[0]
        count = len(m.layout().slots)
        for true_i in m.solution():
            hands_i = count - 1 - true_i
            if m.wires[true_i]["warm"]:
                bomb.act("hands", 0, {"discharge": hands_i})
            assert bomb.act("hands", 0, {"cut": hands_i}) is not Result.STRIKE, \
                "seed %d: correctly-translated cut struck" % seed
        assert m.solved, "seed %d: golden path did not solve under mirror" % seed


def test_ledger_press_skip_also_flip_correctly():
    bomb = Bomb(1, module_count=1, pool=["m02"], mirror=True)
    m = bomb.modules[0]
    count = len(m.layout().slots)
    verdict = m.solution()[count - 1]  # true last tile's correct verdict
    action = {"press": 0} if verdict == "PRESS" else {"skip": 0}
    assert bomb.act("hands", 0, action) is not Result.STRIKE
    assert m.tiles[count - 1]["resolved"] is True


def test_vent_purge_also_flips_correctly():
    bomb = Bomb(1, module_count=1, pool=["n01"], mirror=True)
    m = bomb.modules[0]
    count = len(m.layout().slots)
    m.cooldown = 0
    m.tick(0.01)  # activates
    true_target = m.table[m.active]
    hands_i = count - 1 - true_target
    assert bomb.act("hands", 0, {"purge": hands_i}) is not Result.STRIKE
    assert m.active is None, "purging the correctly-translated vent must clear it"


def test_gauge_lock_is_a_no_op_flip_since_it_only_has_one_slot():
    # Gauge has exactly one "dial" slot (count=1), so count-1-0 == 0 always -
    # mirror must be a harmless no-op for it, not a crash or a mismatch.
    bomb = Bomb(1, module_count=1, pool=["m03"], mirror=True)
    m = bomb.modules[0]
    m.position = m.zone[0]
    assert bomb.act("hands", 0, {"lock": 0}) is Result.SOLVED


def test_gauge_turn_action_is_unaffected_since_its_value_is_a_string():
    bomb = Bomb(1, module_count=1, pool=["m03"], mirror=True)
    m = bomb.modules[0]
    start = m.position
    bomb.act("hands", 0, {"turn": "cw"})
    assert m.position == (start + 1) % 12, "turn direction must never be touched by the int-flip heuristic"


def test_manual_includes_mirror_footnote_only_when_active():
    bomb_on = Bomb(1, module_count=1, pool=["m01"], mirror=True)
    bomb_off = Bomb(1, module_count=1, pool=["m01"], mirror=False)
    assert "MIRRORED" in bomb_on.manual_html()
    assert "MIRRORED" not in bomb_off.manual_html()


def test_room_start_forces_probe_echo_off_when_mirror_is_requested():
    room = Room("MIRR")
    room.attach("hands", _DummySocket())
    room.attach("eyes", _DummySocket())
    room.attach("book", _DummySocket())
    # Explicitly requests probe_echo=True AND mirror=True - mirror must win.
    asyncio.run(room.start(modules=1, mirror=True, probe_echo=True))
    assert room.stage.probe_echo is False
    assert room.bomb.mirror is True


def test_room_start_leaves_probe_echo_alone_when_mirror_is_off():
    room = Room("PLAN")
    room.attach("hands", _DummySocket())
    asyncio.run(room.start(modules=1, mirror=False, probe_echo=True))
    assert room.stage.probe_echo is True


def test_room_handle_start_message_threads_mirror_through():
    room = Room("WIRE")
    hands = _DummySocket()
    room.attach("hands", hands)
    room.attach("eyes", _DummySocket())
    room.attach("book", _DummySocket())
    asyncio.run(room.handle("book", hands, {"type": "start", "modules": 1, "mirror": True}))
    assert room.bomb.mirror is True
    assert room.stage.probe_echo is False
