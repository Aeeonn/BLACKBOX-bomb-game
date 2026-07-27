
"""T6/T9/T10/T12: the presence leak test. As important as test_invariants.py
- see AGENTS.md's presence filter matrix. BLIND must never receive yaw,
pitch, gaze, gesture or pointer keys for OTHER players; every role (BLIND
included) still gets connected/moving for everyone, and full detail for
themselves.

T9 adds BLIND's probe echo (module+cell indices only, gated by probe_echo) -
the one presence field visible to every role including BLIND's own entry.

T10 adds the commit-charge ring: visible to every role unconditionally (no
flag - hard rule 12 says it must never be local-only), with progress computed
live from the server's own clock.

T12 adds MUTE's (or anyone but BLIND's) pointer resolution: module-level by
default regardless of what a client sends, cell-level only when the match's
precise_pointing flag is on.
"""
import asyncio

from server.room import Room
from server.stage import GESTURE_TTL, HOLD_DURATIONS_S, Stage


class _DummySocket:
    async def send_json(self, msg):
        pass


def test_blind_presence_has_no_detail_keys_for_other_players():
    stage = Stage()
    for role in ("blind", "deaf", "mute", "scope", "dispatch"):
        stage.attach(role)
    stage.apply_pose("deaf", yaw=0.4, pitch=-0.2, gaze="bomb")
    stage.apply_gesture("mute", "shake")
    stage.apply_point("scope", {"module": 1})

    payload = stage.presence("blind")
    for entry in payload["players"]:
        if entry["role"] == "blind":
            continue  # own data - always full detail, not a leak
        forbidden = {"yaw", "pitch", "gaze", "gesture", "pointer"} & entry.keys()
        assert not forbidden, "blind saw %r for role %r" % (forbidden, entry["role"])
        assert entry.keys() == {"role", "connected", "moving"}


def test_blind_still_gets_connected_and_moving_for_everyone():
    stage = Stage()
    for role in ("blind", "deaf", "mute"):
        stage.attach(role)
    stage.apply_pose("deaf", yaw=0.1, pitch=0.0, gaze=None)

    payload = stage.presence("blind")
    by_role = {e["role"]: e for e in payload["players"]}
    assert by_role["deaf"]["connected"] is True
    assert by_role["deaf"]["moving"] is True
    assert by_role["scope"]["connected"] is False  # never attached


def test_non_blind_roles_get_full_detail_for_others():
    stage = Stage()
    stage.attach("deaf")
    stage.attach("mute")
    stage.apply_pose("mute", yaw=0.5, pitch=0.1, gaze="manual")
    stage.apply_gesture("mute", "nod")

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "mute")
    assert entry["yaw"] == 0.5
    assert entry["pitch"] == 0.1
    assert entry["gaze"] == "manual"
    assert entry["gesture"] == "nod"


def test_blind_cannot_point():
    stage = Stage()
    stage.attach("blind")
    stage.apply_point("blind", {"module": 0})  # must be a silent no-op

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "blind")
    assert entry["pointer"] is None


def test_gesture_expires_after_ttl():
    stage = Stage()
    stage.attach("mute")
    stage.apply_gesture("mute", "shake")
    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "mute")
    assert entry["gesture"] == "shake"

    # simulate the TTL elapsing without a real sleep
    stage.avatars["mute"].gesture_at -= (GESTURE_TTL + 0.1)
    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "mute")
    assert entry["gesture"] is None


def test_disconnected_seat_stays_present_but_greyed():
    stage = Stage()
    stage.attach("scope")
    stage.apply_pose("scope", yaw=1.0, pitch=1.0, gaze="player")
    stage.detach("scope")

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "scope")
    assert entry["connected"] is False
    assert entry["role"] == "scope"  # seat still enumerated, not removed
    assert entry["yaw"] == 0.0 and entry["gaze"] is None  # cleared on detach


def test_room_dispatches_pose_gesture_point_into_stage():
    room = Room("FFFF")
    blind, deaf = _DummySocket(), _DummySocket()
    room.attach("blind", blind)
    room.attach("deaf", deaf)

    asyncio.run(room.handle("deaf", deaf, {"type": "pose", "yaw": 0.2, "pitch": 0.0, "gaze": "bomb"}))
    asyncio.run(room.handle("deaf", deaf, {"type": "gesture", "kind": "nod"}))
    asyncio.run(room.handle("blind", blind, {"type": "point", "target": {"module": 0}}))

    seen_by_blind = {e["role"]: e for e in room.stage.presence("blind")["players"]}
    assert set(seen_by_blind["deaf"].keys()) == {"role", "connected", "moving"}

    seen_by_mute = {e["role"]: e for e in room.stage.presence("mute")["players"]}
    assert seen_by_mute["deaf"]["gaze"] == "bomb"
    assert seen_by_mute["deaf"]["gesture"] == "nod"
    assert seen_by_mute["blind"]["pointer"] is None  # blind's point() call was a no-op


def test_probe_echo_visible_to_every_role_including_blind_own():
    stage = Stage()
    for role in ("blind", "deaf", "mute", "scope", "dispatch"):
        stage.attach(role)
    stage.apply_probe("blind", module=1, cell=3)

    for viewer in ("blind", "deaf", "mute", "scope", "dispatch"):
        entry = next(e for e in stage.presence(viewer)["players"] if e["role"] == "blind")
        assert entry["probe"] == {"module": 1, "cell": 3}, \
            "viewer %r did not see the probe echo" % viewer


def test_probe_only_tracks_the_blind_role():
    stage = Stage()
    stage.attach("blind")
    stage.attach("deaf")
    stage.apply_probe("deaf", module=0, cell=0)  # must be a silent no-op

    entry = next(e for e in stage.presence("mute")["players"] if e["role"] == "deaf")
    assert "probe" not in entry  # only the blind row ever carries this key


def test_probe_echo_shape_never_contains_descriptor_text():
    stage = Stage()
    stage.attach("blind")
    stage.apply_probe("blind", module=0, cell=2)

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "blind")
    assert set(entry["probe"].keys()) == {"module", "cell"}
    assert "text" not in entry["probe"]


def test_probe_echo_flag_hides_the_field_for_everyone_when_off():
    stage = Stage()
    stage.attach("blind")
    stage.probe_echo = False
    stage.apply_probe("blind", module=0, cell=2)

    for viewer in ("blind", "deaf", "mute", "scope", "dispatch"):
        entry = next(e for e in stage.presence(viewer)["players"] if e["role"] == "blind")
        assert "probe" not in entry, "viewer %r saw the probe echo while probe_echo=False" % viewer


def test_probe_clears_on_blind_disconnect():
    stage = Stage()
    stage.attach("blind")
    stage.apply_probe("blind", module=0, cell=1)
    stage.detach("blind")

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "blind")
    assert entry["probe"] is None


def test_room_dispatches_probe_into_stage_and_it_echoes_to_other_roles():
    room = Room("GGGG")
    blind, deaf, mute = _DummySocket(), _DummySocket(), _DummySocket()
    room.attach("blind", blind)
    room.attach("deaf", deaf)
    room.attach("mute", mute)
    asyncio.run(room.start(modules=1, seed=1))

    asyncio.run(room.handle("blind", blind, {"type": "probe", "module": 0, "cell": 1}))

    seen_by_deaf = {e["role"]: e for e in room.stage.presence("deaf")["players"]}
    assert seen_by_deaf["blind"]["probe"] == {"module": 0, "cell": 1}


def test_room_start_can_disable_probe_echo():
    room = Room("HHHH")
    blind, deaf = _DummySocket(), _DummySocket()
    room.attach("blind", blind)
    room.attach("deaf", deaf)
    asyncio.run(room.start(modules=1, seed=1, probe_echo=False))

    asyncio.run(room.handle("blind", blind, {"type": "probe", "module": 0, "cell": 0}))

    seen_by_deaf = {e["role"]: e for e in room.stage.presence("deaf")["players"]}
    assert "probe" not in seen_by_deaf["blind"]


def test_rearm_clears_a_stale_probe_position():
    room = Room("IIII")
    blind, deaf = _DummySocket(), _DummySocket()
    room.attach("blind", blind)
    room.attach("deaf", deaf)
    asyncio.run(room.start(modules=1, seed=1))
    asyncio.run(room.handle("blind", blind, {"type": "probe", "module": 0, "cell": 2}))
    room.bomb.phase = "won"

    asyncio.run(room.start(modules=1, seed=2))  # REARM

    seen_by_deaf = {e["role"]: e for e in room.stage.presence("deaf")["players"]}
    assert seen_by_deaf["blind"]["probe"] is None


def test_charge_progress_visible_to_every_role_including_blind_own():
    stage = Stage()
    for role in ("blind", "deaf", "mute", "scope", "dispatch"):
        stage.attach(role)
    stage.start_charge("blind", "cut", module=0, cell=1)

    for viewer in ("blind", "deaf", "mute", "scope", "dispatch"):
        entry = next(e for e in stage.presence(viewer)["players"] if e["role"] == "blind")
        assert entry["charge"] is not None, "viewer %r did not see the charge ring" % viewer
        assert entry["charge"]["module"] == 0
        assert entry["charge"]["cell"] == 1
        assert entry["charge"]["kind"] == "cut"
        assert 0.0 <= entry["charge"]["progress"] <= 1.0


def test_charge_only_tracks_the_blind_role():
    stage = Stage()
    stage.attach("blind")
    stage.attach("deaf")
    stage.start_charge("deaf", "cut", module=0, cell=0)  # must be a silent no-op

    entry = next(e for e in stage.presence("mute")["players"] if e["role"] == "deaf")
    assert "charge" not in entry  # only the blind row ever carries this key


def test_charge_ignores_unknown_kind():
    stage = Stage()
    stage.attach("blind")
    stage.start_charge("blind", "not_a_real_kind", module=0, cell=0)

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "blind")
    assert entry["charge"] is None


def test_charge_progress_increases_with_elapsed_time():
    stage = Stage()
    stage.attach("blind")
    stage.start_charge("blind", "cut", module=0, cell=0)

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "blind")
    early_progress = entry["charge"]["progress"]

    # simulate half the 1s cut duration elapsing without a real sleep
    stage.avatars["blind"].charge["started_at"] -= HOLD_DURATIONS_S["cut"] * 0.5
    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "blind")
    assert entry["charge"]["progress"] > early_progress


def test_charge_progress_clamps_at_one_past_the_hold_duration():
    stage = Stage()
    stage.attach("blind")
    stage.start_charge("blind", "discharge", module=0, cell=0)

    # simulate well past the 2s discharge duration
    stage.avatars["blind"].charge["started_at"] -= HOLD_DURATIONS_S["discharge"] * 5

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "blind")
    assert entry["charge"]["progress"] == 1.0


def test_charge_clears_on_stop():
    stage = Stage()
    stage.attach("blind")
    stage.start_charge("blind", "cut", module=0, cell=0)
    stage.stop_charge("blind")

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "blind")
    assert entry["charge"] is None


def test_charge_clears_on_disconnect():
    stage = Stage()
    stage.attach("blind")
    stage.start_charge("blind", "cut", module=0, cell=0)
    stage.detach("blind")

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "blind")
    assert entry["charge"] is None


def test_room_dispatches_charge_start_and_stop_into_stage():
    room = Room("JJJJ")
    blind, deaf = _DummySocket(), _DummySocket()
    room.attach("blind", blind)
    room.attach("deaf", deaf)

    asyncio.run(room.handle("blind", blind,
        {"type": "charge", "action": "start", "kind": "cut", "module": 0, "cell": 3}))
    seen = {e["role"]: e for e in room.stage.presence("deaf")["players"]}
    assert seen["blind"]["charge"]["module"] == 0
    assert seen["blind"]["charge"]["cell"] == 3

    asyncio.run(room.handle("blind", blind, {"type": "charge", "action": "stop"}))
    seen = {e["role"]: e for e in room.stage.presence("deaf")["players"]}
    assert seen["blind"]["charge"] is None


def test_rearm_clears_a_stale_charge():
    room = Room("KKKK")
    blind, deaf = _DummySocket(), _DummySocket()
    room.attach("blind", blind)
    room.attach("deaf", deaf)
    asyncio.run(room.start(modules=1, seed=1))
    asyncio.run(room.handle("blind", blind,
        {"type": "charge", "action": "start", "kind": "cut", "module": 0, "cell": 2}))
    room.bomb.phase = "won"

    asyncio.run(room.start(modules=1, seed=2))  # REARM

    seen_by_deaf = {e["role"]: e for e in room.stage.presence("deaf")["players"]}
    assert seen_by_deaf["blind"]["charge"] is None


def test_pointer_resolves_to_module_only_by_default():
    stage = Stage()
    stage.attach("mute")
    stage.apply_point("mute", {"module": 2, "cell": 5})  # client sends a cell anyway

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "mute")
    assert entry["pointer"] == {"module": 2}, \
        "a client-supplied cell must be dropped when precise_pointing is off"


def test_pointer_includes_cell_when_precise_pointing_is_on():
    stage = Stage()
    stage.attach("mute")
    stage.precise_pointing = True
    stage.apply_point("mute", {"module": 2, "cell": 5})

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "mute")
    assert entry["pointer"] == {"module": 2, "cell": 5}


def test_pointer_without_a_cell_is_unaffected_by_precise_pointing():
    stage = Stage()
    stage.attach("mute")
    stage.precise_pointing = True
    stage.apply_point("mute", {"module": 3})

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "mute")
    assert entry["pointer"] == {"module": 3}


def test_pointer_with_no_module_clears_to_none():
    stage = Stage()
    stage.attach("mute")
    stage.apply_point("mute", {"module": 1})
    stage.apply_point("mute", {})  # no module key at all - e.g. pointer left the bomb

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "mute")
    assert entry["pointer"] is None


def test_blind_still_cannot_point_even_with_precise_pointing_on():
    stage = Stage()
    stage.attach("blind")
    stage.precise_pointing = True
    stage.apply_point("blind", {"module": 0, "cell": 0})

    entry = next(e for e in stage.presence("deaf")["players"] if e["role"] == "blind")
    assert entry["pointer"] is None


def test_room_dispatches_point_with_module_only_default():
    room = Room("LLLL")
    mute, deaf = _DummySocket(), _DummySocket()
    room.attach("mute", mute)
    room.attach("deaf", deaf)

    asyncio.run(room.handle("mute", mute,
        {"type": "point", "target": {"module": 1, "cell": 4}}))

    seen = {e["role"]: e for e in room.stage.presence("deaf")["players"]}
    assert seen["mute"]["pointer"] == {"module": 1}


def test_room_start_can_enable_precise_pointing():
    room = Room("MMMM")
    mute, deaf = _DummySocket(), _DummySocket()
    room.attach("mute", mute)
    room.attach("deaf", deaf)
    asyncio.run(room.start(modules=1, seed=1, precise_pointing=True))

    asyncio.run(room.handle("mute", mute,
        {"type": "point", "target": {"module": 0, "cell": 2}}))

    seen = {e["role"]: e for e in room.stage.presence("deaf")["players"]}
    assert seen["mute"]["pointer"] == {"module": 0, "cell": 2}


def test_rearm_clears_a_stale_pointer():
    room = Room("NNNN")
    mute, deaf = _DummySocket(), _DummySocket()
    room.attach("mute", mute)
    room.attach("deaf", deaf)
    asyncio.run(room.start(modules=1, seed=1))
    asyncio.run(room.handle("mute", mute, {"type": "point", "target": {"module": 0}}))
    room.bomb.phase = "won"

    asyncio.run(room.start(modules=1, seed=2))  # REARM

    seen_by_deaf = {e["role"]: e for e in room.stage.presence("deaf")["players"]}
    assert seen_by_deaf["mute"]["pointer"] is None

