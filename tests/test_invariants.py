
"""THE LEAK TEST. Run after every change. If this fails, the game is broken.

Design Law 3: the BLIND client never RECEIVES colours; the DEAF client never
RECEIVES textures. Not hidden in CSS - not present in the payload.
"""
import json
import re

from server.bomb import Bomb
from server.modules.m01_braid_hue import COLOURS, TEXTURES

FORBIDDEN = {
    "blind": COLOURS,
    "deaf": TEXTURES,
    "scope": COLOURS + TEXTURES,
}


def words(blob: str):
    return set(re.findall(r"[a-z]+", blob.lower()))


def test_no_cross_role_leak():
    for seed in range(300):
        bomb = Bomb(seed, module_count=3)
        for role, banned in FORBIDDEN.items():
            found = words(json.dumps(bomb.snapshot(role)))
            for w in banned:
                assert w not in found, "seed %d: role %r leaked %r" % (seed, role, w)


def test_probe_is_the_only_texture_source():
    bomb = Bomb(1)
    assert "texture" not in json.dumps(bomb.snapshot("blind"))
    assert bomb.inspect("blind", 0, {"cell": 0})["text"]


def test_deaf_cannot_probe():
    assert Bomb(1).inspect("deaf", 0, {"cell": 0}) == {}


def test_mute_gets_no_bomb_state():
    snap = Bomb(2).snapshot("mute")
    assert snap["flags"] == {}
    for m in snap["modules"]:
        assert set(m.keys()) <= {"kind", "module", "solved"}
