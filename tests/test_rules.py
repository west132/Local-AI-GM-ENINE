"""The V5 rules that need world state: growth, rest, quests, modules, hidden truth, injuries, XP."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from localgm import combat, flow, mechanics as M, rules
from localgm.state import World, background_tree
from test_flow import Scripted, world, FAST, OK, LOOP_REACT, LOOP_JUDGE, roll_form, force_check

QUEST = {"kind": "loop", "steps": ["quest"]}


def react(**kw):
    return {"minutes": 0, "ops": [], **kw}


def skill(w):
    return w.player["skills"]["navigation_and_errands"]


class ByKind:
    """Answers by what the step asks for, so a second pass for dues needs no extra script."""
    def __init__(self, sort, react_first, react_next=None):
        self.sort, self.first, self.next, self.seen = sort, react_first, react_next or react(), []
    def ask(self, system, user, schema=None, max_tokens=None):
        self.seen.append((system, user))
        if "REPLY with one JSON" not in system:
            return "ok"
        form = system.split("REPLY with one JSON")[1]
        if "minutes" in form:
            r, self.first = self.first, self.next
            return r
        return self.sort if "kind" in form else {"asks": []} if "asks" in form else OK


def run_react(w, **kw):
    llm = ByKind(LOOP_REACT, react(**kw))
    return flow.run_turn(w, llm, "x"), llm


# ---------- rest and growth ----------

def test_rest_heals_a_quarter_per_hour_and_sleep_heals_fully():
    w = world()
    top = rules.hp_max(w)
    w.player["condition"]["hp"] = 1
    run_react(w, minutes=120, rest="rest")
    assert w.player["condition"]["hp"] == 1 + 2 * max(1, top // 4)
    run_react(w, minutes=480, rest="sleep")
    assert w.player["condition"]["hp"] == top


def test_sleep_is_a_growth_boundary_tiers_rise_and_the_period_resets():
    w = world()
    skill(w)["growth_evidence"] = 12
    w.player["growth_period"]["credited"] = ["navigation_and_errands"]
    run_react(w, minutes=480, rest="sleep")
    s = skill(w)
    assert s["tier"] == "T2" and s["growth_evidence"] == 0 and s["ceiling_evidence"] == 2     # NORMAL tops out at T2: overflow counts toward class
    assert w.player["growth_period"]["credited"] == [] and w.player["growth_period"]["opened"] == w.time["day_index"]


def test_class_rises_only_with_a_valid_source():
    w = world()
    skill(w).update(tier="T2", ceiling_evidence=20)
    run_react(w, minutes=480, rest="sleep")
    assert skill(w)["class"] == "NORMAL" and skill(w)["ceiling_evidence"] == 20          # no source: nothing happens
    run_react(w, minutes=480, rest="sleep", class_sources={"navigation_and_errands": "a guild navigator's method"})
    s = skill(w)
    assert s["class"] == "ELITE" and s["ceiling_evidence"] == 0 and s["class_source"] == "a guild navigator's method"


def test_nothing_grows_in_an_ordinary_turn():
    w = world()
    w.player["skills"]["navigation_and_errands"]["growth_evidence"] = 50
    run_react(w, minutes=30)
    assert w.player["skills"]["navigation_and_errands"]["tier"] == "T1"


# ---------- XP, capability, gear ----------

def test_a_won_roll_with_a_challenge_pays_xp_and_levels_up(monkeypatch):
    force_check(monkeypatch, True)
    w = world("ashfall_hunter")
    lv = w.player["progression"]["state"]
    lv["xp"] = M.XP_REQ[lv["level"]] - 5
    llm = Scripted([LOOP_JUDGE, roll_form(challenge=5, scope="meaningful", committed=True), "ok", OK])
    t = flow.run_turn(w, llm, "I solve it")
    assert w.player["progression"]["state"]["level"] == 5 and any("Level up" in f for f in t.facts)


def test_capability_is_computed_from_level_skill_and_gear_in_numeric_worlds():
    w = world("ashfall_hunter")
    lv = w.player["progression"]["state"]["level"]
    base = {"capability": -4, "base": 3, "challenge": lv + 3 + 2, "skill": "close_combat"}      # AI's band is ignored
    cap, tool, diff, notes = rules.roll_inputs(w, {**base, "stakes": {}})
    assert diff == 10 and cap == M.capmod(lv + 2, lv + 5) and not notes
    gear = next(e for e in w.player["equipment"] if e.get("tier") == "T2")
    cap2, tool2, _, notes2 = rules.roll_inputs(w, {**base, "equipment": gear["item_id"], "tool": {"fit": 2}, "stakes": {}})
    assert cap2 == M.capmod(lv + 2 + 1, lv + 5) and tool2 == 0 and notes2          # +1 boost, and no ToolMod as well


def test_combat_xp_is_paid_once_per_foe_against_the_starting_level():
    w = world("ashfall_hunter")
    out = {"foes": [{"id": "imp", "name": "Imp", "v": 3, "size": "small"}],
           "exchanges": [{"foe": "imp", "roll": {"capability": 4, "base": 1}, "on_success": "full", "my_source": "two-handed",
                          "on_failure": "setback", "attackers": [{"who": "Imp", "source": "small"}]}] * 6}
    import random
    xp0 = (w.player["progression"]["state"]["level"], w.player["progression"]["state"]["xp"])
    lines, facts, owed = combat.run(w, out, random.Random(1))
    assert w.state_of("imp") != "standing" and w.tree["npcs"]["imp"]["xp_paid"]
    st = w.player["progression"]["state"]
    assert (st["level"], st["xp"]) != xp0 and any("XP" in f for f in facts)
    before = (st["level"], st["xp"])
    combat.run(w, out, random.Random(1))                         # the foe is already down: no second payment
    assert (st["level"], st["xp"]) == before


# ---------- lasting injuries ----------

def test_a_heavy_hit_makes_the_ai_name_an_injury_and_the_program_records_it(monkeypatch):
    force_check(monkeypatch, False)
    monkeypatch.setattr(combat, "damage_roll", lambda src, rng=None: (9, "x"))
    w = world()
    llm = Scripted([LOOP_JUDGE, roll_form(stakes={"harm": "loss", "source": "man-sized", "failure": "a heavy blow"}),
                    {"injury": "cracked ribs", "home": "nonsense", "effect": "x"},
                    {"injury": "cracked ribs", "home": "position", "effect": "position +1 on actions that need twisting"},
                    "You are hurt.", OK])
    flow.run_turn(w, llm, "I charge")
    inj = w.player["condition"]["injuries"]
    assert inj == [{"injury": "cracked ribs", "home": "position", "effect": "position +1 on actions that need twisting"}]


# ---------- quests ----------

def test_quest_rules_are_enforced_on_commit():
    w = world("ashfall_hunter")
    qid = "find_eli_voss"
    assert w.commit([{"op": "set", "path": f"quests.{qid}.status", "value": "completed"}]) == []
    assert w.commit([{"op": "set", "path": f"quests.{qid}.status", "value": "active"}])             # closed stays closed
    assert w.commit([{"op": "set", "path": "quests.laundromat_job.quest_level", "value": 9}])       # level is immutable
    assert w.commit([{"op": "set", "path": "quests.laundromat_job.status", "value": "done"}])       # unknown status
    two = {"role": "MAIN", "type": "SHORT", "objective": "o", "status": "available", "quest_level": 2}
    assert w.commit([{"op": "set", "path": "quests.m2", "value": two}])                             # a second open MAIN


def test_a_new_offer_is_rolled_by_the_program_and_the_quest_must_match(monkeypatch):
    rolls = iter([8])                                     # 8..9 -> LONG
    monkeypatch.setattr(M, "roll", lambda n, sides, rng=None: [next(rolls)])
    w = world()
    new = lambda t: {"op": "set", "path": "quests.dock_job", "value": {"role": "SIDE", "type": t, "objective": "unload the boat", "status": "available"}}
    llm = Scripted([QUEST, {"new_offer": True}, {"ops": [new("SHORT")]}, {"ops": [new("LONG")]}, "ok", OK])
    t = flow.run_turn(w, llm, "Hobb offers me a job")
    assert "→ LONG" in llm.seen[2][1] and "exactly that" in llm.seen[3][1]
    assert w.tree["quests"]["dock_job"]["type"] == "LONG"


def test_completing_a_quest_pays_its_xp_once():
    w = world("ashfall_hunter")
    set_done = {"op": "set", "path": "quests.find_eli_voss.status", "value": "completed"}
    llm = Scripted([QUEST, {"new_offer": False}, {"ops": [set_done]}, "ok", OK])
    flow.run_turn(w, llm, "I found Eli")
    paid = w.tree["quests"]["find_eli_voss"]["xp_awarded"]
    lv = w.player["progression"]["state"]
    assert paid > 0 and (lv["level"], lv["xp"]) != (4, 0)
    import copy
    assert rules.quest_xp(w, copy.deepcopy(w.tree)) == []       # nothing newly completed: nothing paid


# ---------- item entitlement ----------

def test_item_points_buy_one_detail_at_a_price_set_by_the_program():
    w = world("ashfall_hunter")
    assert w.player["item_points"] == 1
    llm = Scripted([LOOP_REACT, {"asks": []}, react(entitlement={"item": "Spare flashlight", "tier": "T1", "reason": "packed in the jacket"}),
                    react(entitlement={"item": "Spare flashlight", "tier": "ordinary", "reason": "left in the van last week by Nadia's driver"}),
                    "ok", OK])
    flow.run_turn(w, llm, "I check my pockets")
    assert "costs 2 item points" in llm.seen[3][1]
    assert w.player["item_points"] == 0 and any(e["name"] == "Spare flashlight" for e in w.player["equipment"])
    assert w.commit([{"op": "set", "path": "player.item_points", "value": 99}])              # not the AI's to write
    t, _ = run_react(w, item_points_gain={"amount": 2, "source": "the old patron's blank favour"})
    assert w.player["item_points"] == 2


def test_item_points_are_refused_in_a_world_without_the_module():
    w = world()
    with pytest.raises(M.RuleError):
        rules.spend_entitlement(w, {"item": "x", "tier": "ordinary", "reason": "y"})


# ---------- endings ----------

def endings_world():
    w = world()
    w.tree["enabled_modules"]["bounded_scenario_endings"] = True
    w.tree["ending_conditions"] = {"core_conditions": ["the envelope reaches Tobias"], "hidden_conditions": ["Hobb is exposed as the thief"]}
    return w


def test_a_met_ending_ends_the_scenario_and_conditions_cannot_be_rewritten():
    w = endings_world()
    assert w.commit([{"op": "set", "path": "ending_conditions.core_conditions", "value": []}])
    llm = Scripted([{"kind": "loop", "steps": ["judge"]}, {"verdict": "certain"}, {"met": ["core.0"], "closed": []}, "Done.", OK])
    t = flow.run_turn(w, llm, "I hand Tobias the envelope")
    assert any("ENDING REACHED" in f for f in t.facts) and w.tree["ending_state"]["met"] == "core.0"
    with pytest.raises(flow.ScenarioEnded):
        flow.run_turn(w, Scripted([FAST]), "more")


def test_closed_endings_stay_closed_and_when_none_remain_the_scenario_ends():
    w = endings_world()
    assert rules.ending_update(w, [], ["hidden.0"]) == []
    with pytest.raises(M.RuleError):
        rules.ending_update(w, ["hidden.0"], [])
    out = rules.ending_update(w, [], ["core.0"])
    assert "out of reach" in out[0] and w.tree["ending_state"]["met"] == "none-left"


# ---------- hidden truth ----------

def hidden_world():
    w = world()
    w.tree["locked_case_truths"] = {"theft": {"cause": "the ferryman Ostrava stole the ledger", "evidence": {"where": "under the Quillon pier"},
                                              "discovered_information": {}}}
    return w


def test_secret_names_are_found_and_a_leaking_story_is_sent_back_then_cut():
    w = hidden_world()
    assert rules.secret_terms(w) == {"Ostrava", "Quillon"}
    llm = Scripted([FAST, "Hobb says Ostrava did it.", "A man named Quillon waits.", OK])
    t = flow.run_turn(w, llm, "I wait")
    assert "Ostrava" in llm.seen[2][1] and "A man named Quillon" not in t.prose        # second try still leaks: that sentence is cut
    w.player["knowledge"]["facts"]["ledger"] = "The ledger was stolen by Ostrava"          # once learned, it is no secret
    assert rules.secret_terms(w) == {"Quillon"}


def test_records_of_hidden_things_are_not_handed_to_the_narrator():
    w = hidden_world()
    ops = [{"op": "set", "path": "npcs.hobb_marren.drives.wants", "value": ["Ostrava's silence"]},
           {"op": "set", "path": "npcs.hobb_marren.state.mood", "value": "tense"}]
    t, llm = run_react(w, ops=ops)
    told = llm.seen[-2][1]                                    # the telling step's prompt
    assert "tense" in told and "silence" not in told
