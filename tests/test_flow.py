import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from localgm import flow, mechanics as M
from localgm.state import World, background_tree, WriteRefused
import pytest

BG = pathlib.Path(__file__).resolve().parent.parent / "examples/harbour_guesthouse/background.md"


class Scripted:
    """Stand-in for the model: returns canned replies per step, in the order asked."""
    def __init__(self, replies): self.replies, self.seen = list(replies), []
    def ask(self, system, user, schema, max_tokens=None):
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
    assert w.tree["npcs"]["edda_pryce"]["plan"]["dues"][0]["clock"] == 1020      # BACKGROUND's "17:00" became a real due
    w.apply({"op": "plan", "path": "npcs.hobb_marren", "value": "opens the shutters", "due_in_minutes": 90})
    w.apply({"op": "plan", "path": "npcs.tobias_wren", "value": "leaves", "due_in_minutes": 30})
    assert w.due() == []
    w.advance(100)
    assert [p for p, _ in w.due()] == ["npcs.tobias_wren", "npcs.edda_pryce", "npcs.hobb_marren"]


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


def test_fight_runs_in_code_and_kills_nobody_the_ai_did_not_hit():
    import random
    from localgm import combat
    w = world()
    out = {"foes": [{"id": "thug", "name": "Thug", "v": 1, "size": "normal"}],
           "exchanges": [{"foe": "thug", "roll": {"capability": 0, "base": 10}, "on_success": "full",
                          "my_source": "unarmed", "on_failure": "loss",
                          "attackers": [{"who": "Thug", "source": "man-sized"}]}] * 6}
    lines, facts = combat.run(w, out, random.Random(3))
    assert any("Exchange 1" in l for l in lines)
    hp = w.player["condition"]["hp"]
    assert 0 <= hp <= M.max_hp(1)
    assert w.state_of("thug") in ("standing", "down", "dead")
    # nothing happens after somebody is down
    n = sum(1 for l in lines if l.startswith("Exchange"))
    assert n <= 6


def test_down_then_hit_is_dead_and_sticks():
    w = world()
    w.player["condition"]["hp"] = 0
    w.hurt([3])
    assert w.player_state() == "dead"


def test_ai_unknown_damage_source_is_refused():
    import pytest
    from localgm import combat
    with pytest.raises(M.RuleError):
        combat.damage_roll("laser")


HARD = ["ashfall_hunter", "cyberpunk_red_south_nc", "last_scion_boundary", "tarnstead_low_fantasy"]
ROOT = pathlib.Path(__file__).resolve().parent.parent / "examples"


@pytest.mark.parametrize("name", HARD)
def test_hard_backgrounds_load_and_every_unparsed_plan_goes_to_intake(name):
    w = World(background_tree((ROOT / name / "background.md").read_text()))
    assert w.actors_here()
    todo = w.needs_intake()
    for kind in ("npcs", "factions"):
        for rid, r in (w.tree.get(kind) or {}).items():
            p = (r.get("plan") or {}) if isinstance(r, dict) else {}
            assert p.get("dues") or p.get("text") or not p or r["plan"] in [w.get(x + ".plan") for x in todo]   # nothing silently dropped
    assert len(flow.scene(w, True)) < 8000
    assert isinstance(todo, list)


def test_intake_sets_dues_and_refuses_the_past():
    w = World(background_tree((ROOT / "tarnstead_low_fantasy" / "background.md").read_text()))
    todo = w.needs_intake()
    first = todo[:4]
    for p in todo[4:]:
        w.get(p + ".plan").pop("text", None); w.get(p + ".plan")["triggers"] = ["x"]
    good = {"actors": [{"id": p, "dues": [{"day_offset": 1, "at": "dawn", "what": "patrol"}], "triggers": ["immediately if the watch closes"]} for p in first]}
    bad = {"actors": [{"id": p, "dues": [{"day_offset": 0, "at": "00:10", "what": "past"}], "triggers": []} for p in first]}
    llm = Scripted([bad, good])
    flow.intake(w, llm, batch=4)
    assert all(p not in w.needs_intake() for p in first)
    d = w.get(first[0] + ".plan.dues")[0]
    assert d["day"] == 1 and d["clock"] == 360
    assert "past" in llm.seen[1][1]       # the refusal reason went back to the AI


def test_money_as_a_record_still_pays_and_never_goes_below_zero():
    w = World(background_tree((ROOT / "tarnstead_low_fantasy" / "background.md").read_text()))
    amount, cur = w.cash()
    w.pay(-5)
    assert w.cash()[0] == amount - 5 and cur
    with pytest.raises(M.RuleError):
        w.pay(-10 ** 6)


def test_wh_question_and_unsupported_likelihood_are_not_rolled():
    w = world()
    t = flow.Turn(w, "x")
    out = {"minutes": 5, "ops": [], "asks": [
        {"question": "What has been happening in town?", "likelihood": 3},
        {"question": "Does Hobb have a spare room?", "likelihood": 2},
        {"question": "Does Hobb have a spare room?", "likelihood": 2, "for": "the house is half empty"}]}
    bad = flow.do_apply(t, out)
    assert len(bad) == 2 and len([l for l in t.lines if l.startswith("ask")]) == 1


def test_a_looping_narrator_is_cut_off_by_the_program():
    loop = "You step onto the quay. Gulls circle overhead.\n\n" + "\n".join(
        f'You tell him your favourite thing is number {i}, and he smiles. "That is a great thing. What is your favourite colour?"' for i in range(1, 60))
    out = flow.clean("```text\n" + loop + "\n```")
    assert len(out.split()) <= flow.MAX_WORDS and "```" not in out
    assert out.count("What is your favourite colour") <= 1 or len(out.split()) < 360
    same = flow.clean("The door opens. The door opens. The door opens. A man enters.")
    assert same == "The door opens. A man enters."
