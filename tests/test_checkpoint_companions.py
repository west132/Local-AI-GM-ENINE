import pathlib, random, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from localgm import combat, flow, mechanics as M, rules
from test_flow import Scripted, world, FAST, OK
from test_rules import react, ByKind


def test_the_ten_round_check_runs_only_on_a_tenth_round_and_closes_what_is_settled():
    w = world("ashfall_hunter")
    close = {"ops": [{"op": "set", "path": "quests.find_eli_voss.status", "value": "completed", "because": "Eli is safe at the workshop"}], "notes": ["laundromat still live"]}
    for r in range(9):
        w.round = r
        t = flow.run_turn(w, Scripted([FAST, "x", OK]), "I wait")
        assert "checkpoint" not in t.ran
    w.round = 9
    llm = Scripted([FAST, close, "x", OK])
    t = flow.run_turn(w, llm, "I wait")
    assert "checkpoint" in t.ran and w.get("quests.find_eli_voss.status") == "completed"
    assert any("XP" in f for f in t.facts)                                  # closing it pays its XP once
    assert "OPEN ITEMS" in llm.seen[1][1] and "find_eli_voss" in llm.seen[1][1]


def test_the_check_cannot_reopen_or_invent():
    w = world("ashfall_hunter")
    assert w.commit([{"op": "set", "path": "quests.find_eli_voss.status", "value": "completed"}]) == []
    w.round = 9
    reopen = {"ops": [{"op": "set", "path": "quests.find_eli_voss.status", "value": "active", "because": "x"}], "notes": []}
    t = flow.run_turn(w, Scripted([FAST, reopen, {"ops": [], "notes": []}, "x", OK]), "I wait")
    assert w.get("quests.find_eli_voss.status") == "completed"


def test_tracked_companions_gain_xp_and_levels_alongside_the_player():
    w = world("ashfall_hunter")
    llm = Scripted([{"kind": "loop", "steps": ["react"]}, {"asks": []},
                    react(companion_join=[{"id": "jo_kestrel", "level": 3}]), react(), "Jo joins.", OK])
    flow.run_turn(w, llm, "Jo and I go to the basement together")
    cap = w.get("npcs.jo_kestrel.capability")
    assert cap["tracked"] and cap["overall_level"] == 3
    out = {"foes": [{"id": "imp", "name": "Imp", "v": 3, "size": "small"}],
           "exchanges": [{"foe": "imp", "roll": {"capability": 4, "base": 1}, "on_success": "full", "my_source": "T4", "on_failure": "setback",
                          "attackers": [{"who": "Imp", "source": "small"}]}] * 6}
    xp0 = w.get("npcs.jo_kestrel.capability.xp")
    lines, facts, owed = combat.run(w, out, random.Random(2))
    assert w.get("npcs.jo_kestrel.capability.xp") > xp0 and any("Jo Kestrel earned" in f for f in facts)
    assert w.commit([{"op": "set", "path": "npcs.jo_kestrel.capability.xp", "value": 9999}])      # the AI cannot write it
    flow.run_turn(w, Scripted([{"kind": "loop", "steps": ["react"]}, {"asks": []}, react(companion_leave=["jo_kestrel"]), react(), "ok", OK]), "x")
    assert not w.get("npcs.jo_kestrel.capability.tracked")


def test_a_companions_skills_grow_at_the_boundary():
    w = world("ashfall_hunter")
    w.tree["npcs"]["jo_kestrel"]["capability"] = {"tracked": True, "overall_level": 3, "xp": 0,
                                                  "skills": {"tracking": {"class": "ELITE", "tier": "T1", "growth_evidence": 12, "ceiling_evidence": 0}}}
    msgs = rules.growth_boundary(w, {})
    assert w.get("npcs.jo_kestrel.capability.skills.tracking.tier") == "T2" and any("tracking rose to T2" in m for m in msgs)
