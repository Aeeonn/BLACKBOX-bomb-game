
"""T6: the presence leak test. As important as test_invariants.py - see
AGENTS.md's presence filter matrix. HANDS must never receive yaw, pitch,
gaze, gesture or pointer keys for OTHER players; every role (HANDS included)
still gets connected/moving for everyone, and full detail for themselves.
"""
import asyncio

from server.room import Room
from server.stage import GESTURE_TTL, Stage


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
