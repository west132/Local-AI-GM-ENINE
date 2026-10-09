import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from localgm import flow, mechanics as M
from localgm.state import World, background_tree, WriteRefused
import pytest

BG = pathlib.Path("/home/user/Claude-Engine-V5/examples/harbour_guesthouse/background.md")


class Scripted:
    """Stand-in for the model: returns canned replies per step, in the order asked."""
    def __init__(self, replies): self.replies, self.seen = list(replies), []
    def ask(self, system, user, schema):
        self.seen.append((system, user)); return self.replies.pop(0)


def world():
    return World(background_tree(BG.read_text()))


def test_ai_cannot_write_owned_paths():
    w = world()
    for p in ("player.money", "player.condition.hp", "world_state.time.clock_minutes", "round"):
        with pytest.raises(WriteRefused):
            w.apply({"op": "set", "path": p, "value": 999})


def test_plan_gets_absolute_due_and_fires_in_order():
    w = world()
    w.apply({"op": "plan", "path": "npcs.hobb_marren", "value": "opens the shutters", "due_in_minutes": 90})
    w.apply({"op": "plan", "path": "npcs.tobias_wren", "value": "leaves", "due_in_minutes": 30})
    assert w.due() == []
    w.advance(100)
    assert [p for p, _ in w.due()] == ["npcs.tobias_wren", "npcs.hobb_marren"]


def test_fast_turn_is_sort_tell_audit_only():
    w = world()
    llm = Scripted([{"kind": "fast", "steps": [], "note": "You pick up the broom."}, "You pick up the broom.", {"ok": True}])
    t = flow.run_turn(w, llm, "I pick up the broom")
    assert t.ran == ["sort"] and len(llm.seen) == 3 and w.round == 1


def test_loop_turn_rolls_in_code_and_moves_time():
    w = world()
    before = w.time["clock_minutes"]
    llm = Scripted([
        {"kind": "loop", "steps": ["judge", "react"]},
        {"verdict": "roll", "roll": {"capability": 0, "base": 10, "stakes": {"success": "Hobb lets you in", "failure": "Hobb refuses"}}},
        {"minutes": 20, "ops": [{"op": "set", "path": "npcs.hobb_marren.state.mood", "value": "wary"},
                                {"op": "set", "path": "player.money", "value": 1000}]},
        {"minutes": 20, "ops": [{"op": "set", "path": "npcs.hobb_marren.state.mood", "value": "wary"}]},
        "He eyes you.", {"ok": True}])
    t = flow.run_turn(w, llm, "I ask Hobb for a room")
    assert any("2d10" in l for l in t.lines)
    assert w.get("npcs.hobb_marren.state.mood") == "wary"
    assert w.player["money"] != 1000
    assert w.time["clock_minutes"] == (before + 20) % 1440 or w.time["day_index"] > 0


def test_each_step_loads_only_its_rules():
    w = world()
    llm = Scripted([{"kind": "fast", "steps": []}, "x", {"ok": True}])
    flow.run_turn(w, llm, "I wait")
    sys_sort, sys_tell = llm.seen[0][0], llm.seen[1][0]
    assert "DECISION GATE" in sys_sort and "DECISION GATE" not in sys_tell
    assert len(sys_sort) < 9000
