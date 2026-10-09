"""Faults found in the Ashfall R1-R10 run (docs/runs/ashfall_r10_claude), each with the test that keeps it fixed."""
import pathlib, random, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from localgm import combat, flow, mechanics as M, rules
from test_flow import Scripted, world, OK, LOOP_REACT, FAST
from test_rules import react, ByKind
from test_authority import ASK, MOOD, force_ask


def ash():
    return world("ashfall_hunter")


def test_a_person_whose_position_is_free_text_is_present_where_that_text_says():
    w = ash()
    w.tree["world_state"]["location"] = "canal_embankment"
    assert "eli_voss" in w.actors_here()                # "hiding in relay hut 3 on the disused Canal Street embankment..."
    w.tree["world_state"]["location"] = "hale_workshop"
    assert "eli_voss" not in w.actors_here() and "nadia_voss" in w.actors_here()


def test_the_scene_is_in_the_prompt_once_and_a_new_foe_is_in_it():
    w = ash()
    s = {x["id"]: x for x in flow.load_steps()}
    t = flow.Turn(w, "x")
    for sid in ("wonder", "react", "fight"):
        assert flow.inputs(s[sid], t).count("PERSON nadia_voss") == 1, sid
    combat.add_foes(w, [{"id": "imp", "name": "Imp", "v": 2, "size": "small"}])
    assert "imp" in w.actors_here() and "fighting the player" in flow.scene(w, True)
    assert "()" not in flow.scene(world(), True)


def test_the_narrator_is_told_what_the_player_learned_and_what_happens_in_the_room_but_not_offscreen_lives():
    w = ash()
    ops = [{"op": "set", "path": "locked_case_truths.red_line_case.discovered_information.sign", "value": "scorch marks on hut 3", "channel": "Rin saw them"},
           {"op": "set", "path": "npcs.nadia_voss.state.status", "value": "pays Rin"},
           {"op": "set", "path": "npcs.jonas_rusk.state.status", "value": "ran the window"},
           {"op": "set", "path": "factions.ash_choir.state", "value": {"x": 1}},
           {"op": "set", "path": "npcs.nadia_voss.knowledge.facts.secret", "value": "x", "channel": "told"}]
    t = flow.Turn(w, "x")
    flow._record_lines(t, ops)
    told = "\n".join(t.facts)
    assert "scorch marks on hut 3" in told and "pays Rin" in told
    assert "ran the window" not in told and "factions.ash_choir" not in told and "knowledge.facts.secret" not in told


def test_kill_order_finishes_a_downed_foe_without_a_roll_and_pays_xp_once():
    w = ash()
    out = {"foes": [{"id": "imp", "name": "Imp", "v": 2, "size": "small"}], "kill": True,
           "exchanges": [{"foe": "imp", "roll": {"capability": 4, "base": 1}, "on_success": "full", "my_source": "two-handed",
                          "on_failure": "setback", "attackers": [{"who": "Imp", "source": "small"}]}] * 6}
    lines, facts, owed = combat.run(w, out, random.Random(1))
    assert w.state_of("imp") == "dead" and any("no roll" in l for l in lines)
    assert sum("XP" in f for f in facts) == 1


def test_a_plan_is_not_refused_for_touching_the_actors_other_decided_paths_and_counts_from_the_end_of_the_action(monkeypatch):
    force_ask(monkeypatch, "NO, BUT")
    w = world()
    ask = ASK("Does Hobb sell a room?", governs=["npcs.hobb_marren.state.mood"])
    plan = {"op": "plan", "path": "npcs.hobb_marren", "value": "closes the desk", "due_in_minutes": 30}
    llm = Scripted([LOOP_REACT, ask, react(minutes=60, ops=[MOOD("cool", requires={"on": "Does Hobb sell a room?", "answer": "NO", "band": "BUT"}), plan]),
                    react(), "ok", OK])                                      # a second pass: other dues fell during the hour
    flow.run_turn(w, llm, "x")
    due = w.get("npcs.hobb_marren.plan.dues")[0]
    assert due["day"] * 1440 + due["clock"] == 0 * 1440 + 975 + 60 + 30        # 30 minutes after the action ended, not before


def test_a_band_that_does_not_match_is_refused(monkeypatch):
    force_ask(monkeypatch, "NO, BUT")
    w = world()
    ask = ASK("Does Hobb sell a room?", governs=["npcs.hobb_marren.state.mood"])
    bad = react(ops=[MOOD("cool", requires={"on": "Does Hobb sell a room?", "answer": "NO", "band": "AND"})])
    good = react(ops=[MOOD("cool", requires={"on": "Does Hobb sell a room?", "answer": "NO", "band": "BUT"})])
    llm = Scripted([LOOP_REACT, ask, bad, good, "ok", OK])
    flow.run_turn(w, llm, "x")
    assert "depends on a AND result" in llm.seen[3][1] and w.get("npcs.hobb_marren.state.mood") == "cool"


def test_an_npc_recovers_by_the_night_and_the_hour():
    w = ash()
    w.tree["npcs"]["eli_voss"]["state"]["hp"] = 3
    rules.heal_target(w, "eli_voss", "hour")
    top = w._vitals("eli_voss")[2]
    assert w.tree["npcs"]["eli_voss"]["state"]["hp"] == 3 + max(1, top // 4)
    rules.heal_target(w, "eli_voss", "night")
    assert w.tree["npcs"]["eli_voss"]["state"]["hp"] == top
