
"""Testbench for M1: golden sequence plus random illegal stimulus.

Every Bomb() here pins pool=["m01"] explicitly - now that M2 exists too,
module_count=1 would otherwise randomly hand this test a Ledger instance
instead of a BraidHue one, and these tests are specifically about M1's own
wires/warm/LEAVE mechanics.
"""
import random

from server.bomb import Bomb
from server.modules.base import Result


def test_golden_path_solves_every_seed():
    for seed in range(400):
        m = Bomb(seed, module_count=1, pool=["m01"]).modules[0]
        for i in m.solution():
            if m.wires[i]["warm"]:
                m.act("blind", {"discharge": i})
            assert m.act("blind", {"cut": i}) is not Result.STRIKE, \
                "seed %d: legal cut struck" % seed
        assert m.solved, "seed %d: golden path did not solve" % seed


def test_warm_wire_undischarged_strikes():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=["m01"]).modules[0]
        warm = next(i for i, w in enumerate(m.wires) if w["warm"])
        if warm in m.solution():
            assert m.act("blind", {"cut": warm}) is Result.STRIKE


def test_leave_wire_always_strikes():
    for seed in range(200):
        m = Bomb(seed, module_count=1, pool=["m01"]).modules[0]
        for i in [j for j in range(len(m.wires)) if m._verdict(j) == "LEAVE"]:
            m.wires[i]["discharged"] = True
            assert m.act("blind", {"cut": i}) is Result.STRIKE


def test_fuzz_never_crashes():
    rng = random.Random(0)
    for seed in range(200):
        bomb = Bomb(seed, module_count=2, pool=["m01"])
        for _ in range(60):
            bomb.act("blind", rng.randrange(2),
                     {rng.choice(["cut", "discharge"]): rng.randrange(6)})
        assert bomb.phase in ("running", "won", "lost")


def test_only_blind_may_act():
    m = Bomb(3, module_count=1, pool=["m01"]).modules[0]
    for role in ("deaf", "mute", "scope", "dispatch"):
        assert m.act(role, {"cut": 0}) is Result.NOTHING
