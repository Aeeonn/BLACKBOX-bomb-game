
"""T6/T9/T10: the presence leak test. As important as test_invariants.py -
see AGENTS.md's presence filter matrix. HANDS must never receive yaw, pitch,
gaze, gesture or pointer keys for OTHER players; every role (HANDS included)
still gets connected/moving for everyone, and full detail for themselves.

T9 adds HANDS' probe echo (module+cell indices only, gated by probe_echo) -
the one presence field visible to every role including HANDS' own entry.

T10 adds the commit-charge ring: visible to every role unconditionally (no
flag - hard rule 12 says it must never be local-only), with progress computed
live from the server's own clock.
"""
import asyncio

from server.room import Room
from server.stage import GESTURE_TTL, HOLD_DURATIONS_S, Stage


class _DummySocket:
    async def send_json(self, msg):
        pass


def test_hands_presence_has_no_detail_keys_for_other_players():
    stage = Stage()
    for role in ("hands", "eyes", "book", "scope", "dispatch"):
        stage.attach(role)
    stage.apply_pose("eyes", yaw=0.4, pitch=-0.2, gaze="bomb")
    stage.apply_gesture("book", "shake")
    stage.apply_point("scope", {"module": 1})

    payload = stage.presence("hands")
    for entry in payload["players"]:
        if entry["role"] == "hands":
            continue  # own data - always full detail, not a leak
        forbidden = {"yaw", "pitch", "gaze", "gesture", "pointer"} & entry.keys()
        assert not forbidden, "hands saw %r for role %r" % (forbidden, entry["role"])
        assert entry.keys() == {"role", "connected", "moving"}


def test_hands_still_gets_connected_and_moving_for_everyone():
    stage = Stage()
    for role in ("hands", "eyes", "book"):
        stage.attach(role)
    stage.apply_pose("eyes", yaw=0.1, pitch=0.0, gaze=None)

    payload = stage.presence("hands")
    by_role = {e["role"]: e for e in payload["players"]}
    assert by_role["eyes"]["connected"] is True
    assert by_role["eyes"]["moving"] is True
    assert by_role["scope"]["connected"] is False  # never attached


def test_non_hands_roles_get_full_detail_for_others():
    stage = Stage()
    stage.attach("eyes")
    stage.attach("book")
    stage.apply_pose("book", yaw=0.5, pitch=0.1, gaze="manual")
    stage.apply_gesture("book", "nod")

    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "book")
    assert entry["yaw"] == 0.5
    assert entry["pitch"] == 0.1
    assert entry["gaze"] == "manual"
    assert entry["gesture"] == "nod"


def test_hands_cannot_point():
    stage = Stage()
    stage.attach("hands")
    stage.apply_point("hands", {"module": 0})  # must be a silent no-op

    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "hands")
    assert entry["pointer"] is None


def test_gesture_expires_after_ttl():
    stage = Stage()
    stage.attach("book")
    stage.apply_gesture("book", "shake")
    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "book")
    assert entry["gesture"] == "shake"

    # simulate the TTL elapsing without a real sleep
    stage.avatars["book"].gesture_at -= (GESTURE_TTL + 0.1)
    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "book")
    assert entry["gesture"] is None


def test_disconnected_seat_stays_present_but_greyed():
    stage = Stage()
    stage.attach("scope")
    stage.apply_pose("scope", yaw=1.0, pitch=1.0, gaze="player")
    stage.detach("scope")

    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "scope")
    assert entry["connected"] is False
    assert entry["role"] == "scope"  # seat still enumerated, not removed
    assert entry["yaw"] == 0.0 and entry["gaze"] is None  # cleared on detach


def test_room_dispatches_pose_gesture_point_into_stage():
    room = Room("FFFF")
    hands, eyes = _DummySocket(), _DummySocket()
    room.attach("hands", hands)
    room.attach("eyes", eyes)

    asyncio.run(room.handle("eyes", eyes, {"type": "pose", "yaw": 0.2, "pitch": 0.0, "gaze": "bomb"}))
    asyncio.run(room.handle("eyes", eyes, {"type": "gesture", "kind": "nod"}))
    asyncio.run(room.handle("hands", hands, {"type": "point", "target": {"module": 0}}))

    seen_by_hands = {e["role"]: e for e in room.stage.presence("hands")["players"]}
    assert set(seen_by_hands["eyes"].keys()) == {"role", "connected", "moving"}

    seen_by_book = {e["role"]: e for e in room.stage.presence("book")["players"]}
    assert seen_by_book["eyes"]["gaze"] == "bomb"
    assert seen_by_book["eyes"]["gesture"] == "nod"
    assert seen_by_book["hands"]["pointer"] is None  # hands' point() call was a no-op


def test_probe_echo_visible_to_every_role_including_hands_own():
    stage = Stage()
    for role in ("hands", "eyes", "book", "scope", "dispatch"):
        stage.attach(role)
    stage.apply_probe("hands", module=1, cell=3)

    for viewer in ("hands", "eyes", "book", "scope", "dispatch"):
        entry = next(e for e in stage.presence(viewer)["players"] if e["role"] == "hands")
        assert entry["probe"] == {"module": 1, "cell": 3}, \
            "viewer %r did not see the probe echo" % viewer


def test_probe_only_tracks_the_hands_role():
    stage = Stage()
    stage.attach("hands")
    stage.attach("eyes")
    stage.apply_probe("eyes", module=0, cell=0)  # must be a silent no-op

    entry = next(e for e in stage.presence("book")["players"] if e["role"] == "eyes")
    assert "probe" not in entry  # only the hands row ever carries this key


def test_probe_echo_shape_never_contains_descriptor_text():
    stage = Stage()
    stage.attach("hands")
    stage.apply_probe("hands", module=0, cell=2)

    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "hands")
    assert set(entry["probe"].keys()) == {"module", "cell"}
    assert "text" not in entry["probe"]


def test_probe_echo_flag_hides_the_field_for_everyone_when_off():
    stage = Stage()
    stage.attach("hands")
    stage.probe_echo = False
    stage.apply_probe("hands", module=0, cell=2)

    for viewer in ("hands", "eyes", "book", "scope", "dispatch"):
        entry = next(e for e in stage.presence(viewer)["players"] if e["role"] == "hands")
        assert "probe" not in entry, "viewer %r saw the probe echo while probe_echo=False" % viewer


def test_probe_clears_on_hands_disconnect():
    stage = Stage()
    stage.attach("hands")
    stage.apply_probe("hands", module=0, cell=1)
    stage.detach("hands")

    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "hands")
    assert entry["probe"] is None


def test_room_dispatches_probe_into_stage_and_it_echoes_to_other_roles():
    room = Room("GGGG")
    hands, eyes, book = _DummySocket(), _DummySocket(), _DummySocket()
    room.attach("hands", hands)
    room.attach("eyes", eyes)
    room.attach("book", book)
    asyncio.run(room.start(modules=1, seed=1))

    asyncio.run(room.handle("hands", hands, {"type": "probe", "module": 0, "cell": 1}))

    seen_by_eyes = {e["role"]: e for e in room.stage.presence("eyes")["players"]}
    assert seen_by_eyes["hands"]["probe"] == {"module": 0, "cell": 1}


def test_room_start_can_disable_probe_echo():
    room = Room("HHHH")
    hands, eyes = _DummySocket(), _DummySocket()
    room.attach("hands", hands)
    room.attach("eyes", eyes)
    asyncio.run(room.start(modules=1, seed=1, probe_echo=False))

    asyncio.run(room.handle("hands", hands, {"type": "probe", "module": 0, "cell": 0}))

    seen_by_eyes = {e["role"]: e for e in room.stage.presence("eyes")["players"]}
    assert "probe" not in seen_by_eyes["hands"]


def test_rearm_clears_a_stale_probe_position():
    room = Room("IIII")
    hands, eyes = _DummySocket(), _DummySocket()
    room.attach("hands", hands)
    room.attach("eyes", eyes)
    asyncio.run(room.start(modules=1, seed=1))
    asyncio.run(room.handle("hands", hands, {"type": "probe", "module": 0, "cell": 2}))
    room.bomb.phase = "won"

    asyncio.run(room.start(modules=1, seed=2))  # REARM

    seen_by_eyes = {e["role"]: e for e in room.stage.presence("eyes")["players"]}
    assert seen_by_eyes["hands"]["probe"] is None


def test_charge_progress_visible_to_every_role_including_hands_own():
    stage = Stage()
    for role in ("hands", "eyes", "book", "scope", "dispatch"):
        stage.attach(role)
    stage.start_charge("hands", "cut", module=0, cell=1)

    for viewer in ("hands", "eyes", "book", "scope", "dispatch"):
        entry = next(e for e in stage.presence(viewer)["players"] if e["role"] == "hands")
        assert entry["charge"] is not None, "viewer %r did not see the charge ring" % viewer
        assert entry["charge"]["module"] == 0
        assert entry["charge"]["cell"] == 1
        assert entry["charge"]["kind"] == "cut"
        assert 0.0 <= entry["charge"]["progress"] <= 1.0


def test_charge_only_tracks_the_hands_role():
    stage = Stage()
    stage.attach("hands")
    stage.attach("eyes")
    stage.start_charge("eyes", "cut", module=0, cell=0)  # must be a silent no-op

    entry = next(e for e in stage.presence("book")["players"] if e["role"] == "eyes")
    assert "charge" not in entry  # only the hands row ever carries this key


def test_charge_ignores_unknown_kind():
    stage = Stage()
    stage.attach("hands")
    stage.start_charge("hands", "not_a_real_kind", module=0, cell=0)

    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "hands")
    assert entry["charge"] is None


def test_charge_progress_increases_with_elapsed_time():
    stage = Stage()
    stage.attach("hands")
    stage.start_charge("hands", "cut", module=0, cell=0)

    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "hands")
    early_progress = entry["charge"]["progress"]

    # simulate half the 1s cut duration elapsing without a real sleep
    stage.avatars["hands"].charge["started_at"] -= HOLD_DURATIONS_S["cut"] * 0.5
    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "hands")
    assert entry["charge"]["progress"] > early_progress


def test_charge_progress_clamps_at_one_past_the_hold_duration():
    stage = Stage()
    stage.attach("hands")
    stage.start_charge("hands", "discharge", module=0, cell=0)

    # simulate well past the 2s discharge duration
    stage.avatars["hands"].charge["started_at"] -= HOLD_DURATIONS_S["discharge"] * 5

    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "hands")
    assert entry["charge"]["progress"] == 1.0


def test_charge_clears_on_stop():
    stage = Stage()
    stage.attach("hands")
    stage.start_charge("hands", "cut", module=0, cell=0)
    stage.stop_charge("hands")

    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "hands")
    assert entry["charge"] is None


def test_charge_clears_on_disconnect():
    stage = Stage()
    stage.attach("hands")
    stage.start_charge("hands", "cut", module=0, cell=0)
    stage.detach("hands")

    entry = next(e for e in stage.presence("eyes")["players"] if e["role"] == "hands")
    assert entry["charge"] is None


def test_room_dispatches_charge_start_and_stop_into_stage():
    room = Room("JJJJ")
    hands, eyes = _DummySocket(), _DummySocket()
    room.attach("hands", hands)
    room.attach("eyes", eyes)

    asyncio.run(room.handle("hands", hands,
        {"type": "charge", "action": "start", "kind": "cut", "module": 0, "cell": 3}))
    seen = {e["role"]: e for e in room.stage.presence("eyes")["players"]}
    assert seen["hands"]["charge"]["module"] == 0
    assert seen["hands"]["charge"]["cell"] == 3

    asyncio.run(room.handle("hands", hands, {"type": "charge", "action": "stop"}))
    seen = {e["role"]: e for e in room.stage.presence("eyes")["players"]}
    assert seen["hands"]["charge"] is None


def test_rearm_clears_a_stale_charge():
    room = Room("KKKK")
    hands, eyes = _DummySocket(), _DummySocket()
    room.attach("hands", hands)
    room.attach("eyes", eyes)
    asyncio.run(room.start(modules=1, seed=1))
    asyncio.run(room.handle("hands", hands,
        {"type": "charge", "action": "start", "kind": "cut", "module": 0, "cell": 2}))
    room.bomb.phase = "won"

    asyncio.run(room.start(modules=1, seed=2))  # REARM

    seen_by_eyes = {e["role"]: e for e in room.stage.presence("eyes")["players"]}
    assert seen_by_eyes["hands"]["charge"] is None

