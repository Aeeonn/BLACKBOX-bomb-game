
"""Room-level tests for T2: REARM must build a genuinely new Bomb (never
mutate the ended one), must reseed widely enough that two rounds don't share
a rule table, and must never clobber a bomb that is still running.
"""
import asyncio
import json

from server.room import Room


def test_rearm_replaces_the_bomb_object_not_just_its_state():
    room = Room("AAAA")
    asyncio.run(room.start(modules=1))
    first = room.bomb
    first.phase = "won"  # end the round without waiting on the real tick loop

    asyncio.run(room.start(modules=1))
    second = room.bomb

    assert second is not first, "REARM must build a new Bomb, not reset the old one"


def test_rearm_reseeds_widely_and_changes_the_rule_table():
    room = Room("BBBB")
    seeds, tables = set(), set()
    for _ in range(50):
        asyncio.run(room.start(modules=1))
        seeds.add(room.bomb.seed)
        tables.add(json.dumps(room.bomb.modules[0].table, sort_keys=True))
        room.bomb.phase = "won"

    assert len(seeds) > 45, "seed range looks too small - collisions too frequent"
    assert len(tables) > 1, "consecutive rounds produced the same M1 rule table"


def test_start_is_a_no_op_while_a_round_is_running():
    room = Room("CCCC")
    asyncio.run(room.start(modules=1))
    running = room.bomb

    asyncio.run(room.start(modules=1))  # bomb is still "running" - must be ignored

    assert room.bomb is running
