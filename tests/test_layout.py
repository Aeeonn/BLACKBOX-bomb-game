
"""T4: layout() is WORLD geometry - one shared spatial layout per module,
identical for every role. See AGENTS.md hard rule 3.
"""
import json

from server.bomb import Bomb

ROLES = ["hands", "eyes", "book", "scope", "dispatch"]


def test_layout_identical_across_all_roles():
    for seed in range(50):
        bomb = Bomb(seed, module_count=3)
        snapshots = {role: bomb.snapshot(role)["layouts"] for role in ROLES}
        first = snapshots["hands"]
        for role, layouts in snapshots.items():
            assert layouts == first, "seed %d: role %r saw a different layout" % (seed, role)


def test_layout_shape_matches_wire_count():
    bomb = Bomb(7, module_count=2)
    layouts = bomb.snapshot("hands")["layouts"]
    for layout, module in zip(layouts, bomb.modules):
        assert layout["w"] == len(module.wires)
        assert layout["h"] == 1
        assert [s["idx"] for s in layout["slots"]] == list(range(len(module.wires)))
        assert all(s["kind"] == "wire" for s in layout["slots"])
        assert all(0.0 <= s["x"] <= 1.0 and 0.0 <= s["y"] <= 1.0 for s in layout["slots"])


def test_layout_carries_no_properties():
    bomb = Bomb(3, module_count=2)
    blob = json.dumps(bomb.snapshot("hands")["layouts"])
    for banned in ("colour", "texture", "braided", "verdict"):
        assert banned not in blob
