
"""Room-level tests for T2 (REARM) and T13 (lobby roster, ready flag, and
pausing the timer while a required role is disconnected).

T2: REARM must build a genuinely new Bomb (never mutate the ended one), must
reseed widely enough that two rounds don't share a rule table, and must never
clobber a bomb that is still running.

T13: roster() is metadata only (connected/ready/required per role, identical
for every viewer - never gated by self.bomb); is_paused() is always
recomputed from self.sockets rather than tracked separately, so it can never
desync from what's actually connected.
"""
import asyncio
import json

from server.room import Room


class _RecordingSocket:
    """Like test_presence.py's _DummySocket, but keeps every message sent to
    it so a test can assert on the actual wire shape, not just on Room's
    internal state."""
    def __init__(self):
        self.sent = []

    async def send_json(self, msg):
        self.sent.append(msg)


def test_rearm_replaces_the_bomb_object_not_just_its_state():
    room = Room("AAAA")
    asyncio.run(room.start(modules=1))
    first = room.bomb
    first.phase = "won"  # end the round without waiting on the real tick loop

    asyncio.run(room.start(modules=1))
    second = room.bomb

    assert second is not first, "REARM must build a new Bomb, not reset the old one"


def test_rearm_reseeds_widely_and_changes_the_rule_table():
    # Room.start() has no pool passthrough (only Bomb() does directly, and
    # this test is specifically about Room's own REARM behaviour, not about
    # forcing module selection) - now that the registry holds M1/M2/M3, a
    # given round may draw any of them, so this only compares BraidHue's
    # .table across whichever rounds happen to draw m01, skipping the rest.
    # 50 iterations across 3 registered module ids still yields plenty of
    # m01 samples to compare.
    room = Room("BBBB")
    seeds, tables = set(), set()
    for _ in range(50):
        asyncio.run(room.start(modules=1))
        seeds.add(room.bomb.seed)
        m = room.bomb.modules[0]
        if m.id == "m01":
            tables.add(json.dumps(m.table, sort_keys=True))
        room.bomb.phase = "won"

    assert len(seeds) > 45, "seed range looks too small - collisions too frequent"
    assert len(tables) > 1, "consecutive m01 rounds produced the same rule table"


def test_start_is_a_no_op_while_a_round_is_running():
    room = Room("CCCC")
    asyncio.run(room.start(modules=1))
    running = room.bomb

    asyncio.run(room.start(modules=1))  # bomb is still "running" - must be ignored

    assert room.bomb is running


def test_roster_reports_connected_ready_and_required():
    room = Room("OOOO")
    room.attach("hands", _RecordingSocket())
    room.attach("scope", _RecordingSocket())
    asyncio.run(room.handle("scope", room.sockets["scope"], {"type": "ready"}))

    by_role = {r["role"]: r for r in room.roster()}
    assert by_role["hands"] == {"role": "hands", "connected": True, "ready": False, "required": True}
    assert by_role["scope"] == {"role": "scope", "connected": True, "ready": True, "required": False}
    assert by_role["eyes"] == {"role": "eyes", "connected": False, "ready": False, "required": True}
    assert by_role["book"]["required"] is True
    assert by_role["dispatch"]["required"] is False


def test_ready_defaults_to_false_and_can_be_toggled_off_again():
    room = Room("PPPP")
    sock = _RecordingSocket()
    room.attach("book", sock)

    assert next(r for r in room.roster() if r["role"] == "book")["ready"] is False

    asyncio.run(room.handle("book", sock, {"type": "ready", "value": True}))
    assert next(r for r in room.roster() if r["role"] == "book")["ready"] is True

    asyncio.run(room.handle("book", sock, {"type": "ready", "value": False}))
    assert next(r for r in room.roster() if r["role"] == "book")["ready"] is False


def test_ready_clears_on_detach_so_a_reconnect_starts_unready():
    room = Room("QQQQ")
    sock = _RecordingSocket()
    room.attach("eyes", sock)
    asyncio.run(room.handle("eyes", sock, {"type": "ready"}))
    assert next(r for r in room.roster() if r["role"] == "eyes")["ready"] is True

    room.detach("eyes", sock)

    new_sock = _RecordingSocket()
    room.attach("eyes", new_sock)
    assert next(r for r in room.roster() if r["role"] == "eyes")["ready"] is False, \
        "a stale ready flag from before a disconnect must not survive a reconnect"


def test_lobby_broadcast_carries_a_roster_not_a_bare_role_list():
    room = Room("RRRR")
    sock = _RecordingSocket()
    room.attach("hands", sock)

    asyncio.run(room.broadcast_state())

    msg = sock.sent[-1]
    assert msg["type"] == "lobby"
    assert msg["roster"] == room.roster()
    assert "roles" not in msg, "T13 replaced the bare role-name list with the richer roster"


def test_is_paused_false_before_any_bomb_exists():
    room = Room("SSSS")
    assert room.is_paused() is False


def test_is_paused_true_once_a_required_role_disconnects_mid_round():
    room = Room("TTTT")
    hands, eyes, book = _RecordingSocket(), _RecordingSocket(), _RecordingSocket()
    room.attach("hands", hands)
    room.attach("eyes", eyes)
    room.attach("book", book)
    asyncio.run(room.start(modules=1))
    assert room.is_paused() is False

    room.detach("book", book)
    assert room.is_paused() is True, "losing a required role mid-round must pause the timer"

    room.attach("book", _RecordingSocket())
    assert room.is_paused() is False, "reconnecting the missing required role must unpause"


def test_is_paused_ignores_optional_roles_disconnecting():
    room = Room("UUUU")
    hands, eyes, book = _RecordingSocket(), _RecordingSocket(), _RecordingSocket()
    room.attach("hands", hands)
    room.attach("eyes", eyes)
    room.attach("book", book)
    room.attach("scope", _RecordingSocket())
    asyncio.run(room.start(modules=1))

    room.detach("scope", room.sockets["scope"])

    assert room.is_paused() is False, "scope/dispatch are optional - their absence must never pause anything"


def test_tick_once_freezes_time_while_paused_and_resumes_without_a_jump():
    room = Room("VVVV")
    hands, eyes, book = _RecordingSocket(), _RecordingSocket(), _RecordingSocket()
    room.attach("hands", hands)
    room.attach("eyes", eyes)
    room.attach("book", book)
    asyncio.run(room.start(modules=1, seconds=100.0))
    start_time = room.bomb.time_left

    room.detach("book", book)
    asyncio.run(room._tick_once(5.0))  # a long fake dt - must be fully ignored while paused
    assert room.bomb.time_left == start_time, "time must not move at all while paused"

    room.attach("book", _RecordingSocket())
    asyncio.run(room._tick_once(2.0))
    assert room.bomb.time_left == start_time - 2.0, \
        "resuming must apply only the new dt, never the dt accumulated while paused"


def test_state_broadcast_includes_a_paused_flag_for_every_role():
    room = Room("WWWW")
    hands, eyes, book = _RecordingSocket(), _RecordingSocket(), _RecordingSocket()
    room.attach("hands", hands)
    room.attach("eyes", eyes)
    room.attach("book", book)
    asyncio.run(room.start(modules=1))

    asyncio.run(room.broadcast_state())
    assert hands.sent[-1]["payload"]["paused"] is False

    room.detach("book", book)
    asyncio.run(room.broadcast_state())
    assert hands.sent[-1]["payload"]["paused"] is True


def test_detaching_mid_round_immediately_rebroadcasts_the_paused_state():
    # Exercises the same finally-block behaviour server/main.py adds for T13,
    # without needing a real websocket - broadcast_state() is called once
    # right after detach(), same as main.py now does.
    room = Room("XXXX")
    hands, eyes, book = _RecordingSocket(), _RecordingSocket(), _RecordingSocket()
    room.attach("hands", hands)
    room.attach("eyes", eyes)
    room.attach("book", book)
    asyncio.run(room.start(modules=1))
    hands.sent.clear()

    room.detach("book", book)
    asyncio.run(room.broadcast_state())

    assert hands.sent[-1]["payload"]["paused"] is True
