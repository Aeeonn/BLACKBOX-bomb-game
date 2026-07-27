
"""T5: Bomb selects modules from REGISTRY by id instead of hardcoding one,
and excludes any module whose requires_roles isn't satisfied by who is
connected. A blind/deaf/mute room must never generate a SCOPE-dependent
module.
"""
import asyncio

import pytest

from server.bomb import Bomb
from server.modules.base import REGISTRY, Layout, Module, Result, Views, register
from server.room import Room


class _FakeScopeOnly(Module):
    """Throwaway module requiring SCOPE. Registered/unregistered around every
    test in this file only, so it can never leak into any other test file's
    view of REGISTRY.
    """
    id = "test_scope_only"
    name = "Fake Scope-Only"
    requires_roles = {"scope"}

    def generate(self, rng, flags):
        self.solved = False

    def views(self):
        return Views(blind={}, deaf={}, mute={}, scope={"kind": "fake"})

    def layout(self):
        return Layout(w=1, h=1, slots=[])

    def act(self, role, action):
        return Result.NOTHING

    def manual_page(self):
        return "<section></section>"


class _DummySocket:
    async def send_json(self, msg):
        pass


@pytest.fixture(autouse=True)
def _register_fake_module():
    register(_FakeScopeOnly)
    try:
        yield
    finally:
        REGISTRY.pop(_FakeScopeOnly.id, None)


def test_pool_selects_by_id_not_a_hardcoded_class():
    bomb = Bomb(1, module_count=3, pool=["test_scope_only"], roles={"scope"})
    assert all(m.id == "test_scope_only" for m in bomb.modules)


def test_blind_deaf_mute_room_never_gets_the_scope_only_module():
    roles = {"blind", "deaf", "mute"}
    pool = ["m01", "test_scope_only"]
    for seed in range(200):
        bomb = Bomb(seed, module_count=4, pool=pool, roles=roles)
        assert all(m.id != "test_scope_only" for m in bomb.modules), \
            "seed %d: SCOPE-dependent module generated without SCOPE connected" % seed


def test_scope_room_can_get_the_scope_only_module():
    roles = {"blind", "deaf", "mute", "scope"}
    pool = ["m01", "test_scope_only"]
    seen = set()
    for seed in range(200):
        bomb = Bomb(seed, module_count=4, pool=pool, roles=roles)
        seen.update(m.id for m in bomb.modules)
    assert "test_scope_only" in seen, "scope-only module never appeared even with SCOPE connected"


def test_no_eligible_module_raises_instead_of_crashing_obscurely():
    with pytest.raises(ValueError):
        Bomb(1, module_count=1, pool=["test_scope_only"], roles={"blind", "deaf", "mute"})


def test_room_excludes_scope_only_module_when_scope_is_not_connected():
    room = Room("EEEE")
    for role in ("blind", "deaf", "mute"):
        room.attach(role, _DummySocket())
    asyncio.run(room.start(modules=4, seed=1))
    assert all(m.id != "test_scope_only" for m in room.bomb.modules)
