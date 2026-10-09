import pathlib, sys, random
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from localgm import combat, flow, mechanics as M
from localgm.state import World, background_tree, WriteRefused

ROOT = pathlib.Path(__file__).resolve().parent.parent / "examples"
HARD = ["ashfall_hunter", "cyberpunk_red_south_nc", "last_scion_boundary", "tarnstead_low_fantasy"]


class Scripted:
    """Stand-in for the model: canned replies in the order the steps ask for them."""
    def __init__(self, replies): self.replies, self.seen = list(replies), []
    def ask(self, system, user, schema=None, max_tokens=None):
        self.seen.append((system, user))
        r = self.replies.pop(0)
        if isinstance(r, Exception): raise r
        return r


def world(name="harbour_guesthouse"):
    return World(background_tree((ROOT / name / "background.md").read_text()))


FAST = {"kind": "fast", "steps": [], "note": "It simply happens."}
OK = {"ok": True}
LOOP_REACT = {"kind": "loop", "steps": ["react"]}
LOOP_JUDGE = {"kind": "loop", "steps": ["judge"]}


_N = [0]


def roll_form(**kw):
    stakes = {"success": "it works", "failure": "it fails", "harm": "none", **kw.pop("stakes", {})}
    _N[0] += 1
    cites = kw.pop("cites", [])
    return {"verdict": "roll", "cites": cites, "roll": {"subject": kw.pop("subject", f"attempt {_N[0]}"), "capability": 0, "base": 10, "stakes": stakes, **kw}}


def force_check(monkeypatch, success: bool):
    monkeypatch.setattr(M, "check", lambda cap, tool, diff, rng=None: {"dice": [6, 6] if success else [1, 1], "cap": cap, "tool": tool,
                                                                       "total": 12 if success else 2, "difficulty": diff, "success": success})


# ---------- one workflow, defined once ----------

def test_the_yaml_is_the_whole_workflow():
    steps = flow.load_steps()
    w = world()
    t = flow.Turn(w, "x")
    for s in steps:
        assert s["program"] in flow.HANDLERS, s["id"]
        flow._when(s["when"], t)                        # every condition evaluates
        if s.get("ai") is not False:
            for r in s["rules"]:
                assert (flow.ENGINE / "rules" / f"{r}.md").exists()
            flow.inputs(s, t)                           # every input name is known
    ids = [s["id"] for s in steps]
    assert ids.index("judge") < ids.index("wonder") < ids.index("react") < ids.index("tell")   # roll before consequence


def test_fast_turn_is_sort_tell_audit_only():
    w = world()
    llm = Scripted([{"kind": "fast", "steps": [], "note": "You pick up the broom."}, "You pick up the broom.", OK])
    t = flow.run_turn(w, llm, "I pick up the broom")
    assert t.ran == ["sort", "tell", "audit"] and len(llm.seen) == 3 and w.round == 1


# ---------- the dice decide, then the AI is told ----------

def test_the_ai_sees_the_ask_result_before_it_decides_the_consequence(monkeypatch):
    monkeypatch.setattr(M, "ask", lambda l, rng=None: {"dice": [1, 2], "likelihood": l, "total": 3 + l, "band": "NO, AND"})
    w = world()
    llm = Scripted([LOOP_REACT,
                    {"asks": [{"question": "Does Hobb let me stay?", "obvious": "none", "likelihood": 1, "for": "the house is half empty"}]},
                    {"minutes": 10, "ops": [{"op": "set", "path": "npcs.hobb_marren.state.mood", "value": "hostile"}]},
                    "He refuses.", OK])
    t = flow.run_turn(w, llm, "I ask Hobb for a room")
    wonder_prompt, react_prompt = llm.seen[1][1], llm.seen[2][1]
    assert "NO, AND" not in wonder_prompt            # nothing was decided yet when the question was asked
    assert "'Does Hobb let me stay?' → NO, AND" in react_prompt   # the AI is told the result before it writes consequences
    assert w.get("npcs.hobb_marren.state.mood") == "hostile"
    assert any(l.startswith("ask 2d10") for l in t.lines)


def test_a_failed_roll_costs_hp_in_code_and_a_win_earns_evidence(monkeypatch):
    force_check(monkeypatch, False)
    monkeypatch.setattr(combat, "damage_roll", lambda src, rng=None: (4, "1d6 (4)"))
    w = world()
    hp0 = w.player["condition"]["hp"]
    llm = Scripted([LOOP_JUDGE, roll_form(stakes={"harm": "loss", "source": "man-sized", "failure": "a blow lands"}), "You are hit.", OK])
    t = flow.run_turn(w, llm, "I shove past the man")
    assert w.player["condition"]["hp"] == hp0 - 4
    assert any("HP" in l for l in t.lines) and any("RESULT harm" in r for r in t.results)

    force_check(monkeypatch, True)
    w2 = world()
    skill = next(iter(w2.player["skills"]))
    llm = Scripted([LOOP_JUDGE, roll_form(base=16, skill=skill, committed=True), "It works.", OK])
    flow.run_turn(w2, llm, "I try")
    sk = w2.player["skills"][skill]
    assert sk.get("growth_evidence", 0) + sk.get("ceiling_evidence", 0) == 1
    assert skill in w2.player["growth_period"]["credited"]


def test_harm_without_a_source_goes_back_to_the_ai(monkeypatch):
    force_check(monkeypatch, True)
    w = world()
    llm = Scripted([LOOP_JUDGE, roll_form(stakes={"harm": "loss"}),
                    roll_form(stakes={"harm": "loss", "source": "light"}), "ok", OK])
    flow.run_turn(w, llm, "I jump")
    assert "needs stakes.source" in llm.seen[2][1]


def test_odds_stop_waits_for_the_player_then_rolls_unchanged(monkeypatch):
    rolled = []
    monkeypatch.setattr(M, "check", lambda cap, tool, diff, rng=None: rolled.append(diff) or {"dice": [9, 9], "cap": cap, "tool": tool, "total": 18, "difficulty": diff, "success": True})
    w = world()
    llm = Scripted([LOOP_JUDGE, roll_form(base=20, stakes={"failure": "you fall"})])      # ~ under 25%, not committed
    t = flow.run_turn(w, llm, "I leap the gap")
    assert t.halt and rolled == [] and w.tree["pending"]["roll"]["base"] == 20 and "%" in t.prose and len(llm.seen) == 2
    llm = Scripted([{"kind": "confirm", "steps": []}, "You land it.", OK])
    flow.run_turn(w, llm, "yes, go")
    assert rolled == [20] and "pending" not in w.tree
    # a different answer drops it without a roll
    w.tree["pending"] = {"roll": {"capability": 0, "base": 20, "stakes": {}}, "ask": "x", "action": "y"}
    flow.run_turn(w, Scripted([FAST, "Fine.", OK]), "never mind, I wait")
    assert "pending" not in w.tree and rolled == [20]


# ---------- time, dues, clocks, money ----------

def test_a_due_that_falls_during_the_action_is_resolved_in_the_same_turn():
    w = world()
    w.apply({"op": "plan", "path": "npcs.tobias_wren", "value": "locks up the loft", "due_in_minutes": 30})
    llm = Scripted([LOOP_REACT, {"asks": []}, {"minutes": 60, "ops": []},
                    {"minutes": 0, "ops": [{"op": "set", "path": "npcs.tobias_wren.state.status", "value": "walking home"}]},
                    "Tobias leaves.", OK])
    flow.run_turn(w, llm, "I read for an hour")
    assert "locks up the loft" not in llm.seen[2][1]            # not yet due when the action began
    assert "locks up the loft" in llm.seen[3][1]                # shown in a second pass, same turn
    assert w.get("npcs.tobias_wren.state.status") == "walking home"
    assert not any("locks up the loft" in d["what"] for d in w.get("npcs.tobias_wren.plan.dues"))


def test_money_and_time_are_applied_by_the_program_and_overspending_is_refused():
    w = world()
    cash = w.cash()[0]
    t0 = w.time["clock_minutes"]
    llm = Scripted([LOOP_REACT, {"asks": []}, {"minutes": 20, "ops": [], "money": -3}, "You pay.", OK])
    flow.run_turn(w, llm, "I pay for tea")
    assert w.cash()[0] == cash - 3 and w.time["clock_minutes"] == t0 + 20
    llm = Scripted([LOOP_REACT, {"asks": []}, {"minutes": 5, "ops": [], "money": -9999},
                    {"minutes": 5, "ops": [], "money": 0}, "No.", OK])
    flow.run_turn(w, llm, "I buy the harbour")
    assert w.cash()[0] == cash - 3 and "not enough money" in llm.seen[3][1]


def test_a_due_clock_must_be_answered_and_the_program_fills_it():
    w = world("tarnstead_low_fantasy")
    pid = "rising_water"
    w.tree["active_world_pressures"][pid]["clock"]["due_at"] = {"day": 0, "clock": 0}
    w.tree["active_world_pressures"][pid]["clock"]["interval_minutes"] = 1440
    before = w.tree["active_world_pressures"][pid]["clock"]["filled"]
    llm = Scripted([LOOP_REACT, {"asks": []}, {"minutes": 5, "ops": []},
                    {"minutes": 5, "ops": [], "clocks": [{"pressure": pid, "operated": True}]}, "Rain.", OK])
    flow.run_turn(w, llm, "I wait")
    assert "answer it in 'clocks'" in llm.seen[3][1]
    c = w.tree["active_world_pressures"][pid]["clock"]
    assert c["filled"] == before + 1 and c["due_at"]["day"] == 1


# ---------- the AI cannot corrupt the world ----------

def test_owned_paths_and_bad_shapes_are_refused_and_nothing_partial_survives():
    w = world()
    snapshot = repr(w.tree)
    for op in ({"op": "set", "path": "player.money", "value": 999},
               {"op": "set", "path": "npcs.hobb_marren", "value": "gone"},
               {"op": "remove", "path": "npcs.hobb_marren"},
               {"op": "set", "path": "npcs.hobb_marren.name", "value": ["a", "list"]},
               {"op": "set", "path": "invented_top_level.x", "value": 1}):
        good = {"op": "set", "path": "npcs.hobb_marren.state.mood", "value": "calm"}
        faults = w.commit([good, op])
        assert faults, op
        assert repr(w.tree) == snapshot          # the good op did not stay behind
    assert w.commit([{"op": "set", "path": "npcs.hobb_marren.state.mood", "value": "calm"}]) == []


def test_a_turn_whose_ops_are_refused_twice_changes_nothing_and_tells_the_narrator():
    w = world()
    bad = {"minutes": 30, "ops": [{"op": "set", "path": "npcs.hobb_marren", "value": "gone"}]}
    llm = Scripted([LOOP_REACT, {"asks": []}, bad, bad, "Nothing happens.", OK])
    t = flow.run_turn(w, llm, "I wait")
    assert isinstance(w.get("npcs.hobb_marren"), dict) and w.time["clock_minutes"] == 975
    assert any("could not be recorded" in f for f in t.facts)


def test_the_real_world_is_untouched_when_a_turn_crashes():
    w = world()
    snap, rnd = repr(w.tree), w.round
    llm = Scripted([LOOP_REACT, {"asks": []}, {"minutes": 30, "ops": [], "money": -1}, RuntimeError("model died")])
    with pytest.raises(RuntimeError):
        flow.run_turn(w, llm, "I wait")
    assert repr(w.tree) == snap and w.round == rnd


def test_quest_step_runs_without_a_minutes_field_and_trackers_are_counted_by_the_program():
    w = world()
    llm = Scripted([{"kind": "loop", "steps": ["quest"]}, {"new_offer": False},
                    {"ops": [{"op": "tracker", "path": "fish", "value": {"create": {"name": "Fish", "target": 3}}}]}, "ok", OK])
    flow.run_turn(w, llm, "I start counting fish")
    llm = Scripted([{"kind": "loop", "steps": ["quest"]}, {"new_offer": False},
                    {"ops": [{"op": "tracker", "path": "fish", "value": {"add": 9}}]}, "ok", OK])
    flow.run_turn(w, llm, "more fish")
    assert w.tree["trackers"]["fish"]["current"] == 3        # clamped at the target
    assert w.commit([{"op": "set", "path": "trackers.fish.current", "value": 0}])   # the AI cannot write it directly


# ---------- start of game ----------

@pytest.mark.parametrize("name", HARD)
def test_hard_backgrounds_load_and_nothing_is_silently_dropped(name):
    w = world(name)
    assert w.actors_here()
    todo = w.needs_intake()
    for kind in ("npcs", "factions"):
        for rid, r in (w.tree.get(kind) or {}).items():
            p = (r.get("plan") or {}) if isinstance(r, dict) else {}
            assert p.get("dues") or p.get("text") or p.get("triggers") or not p or f"{kind}.{rid}" in todo
    assert len(flow.scene(w, True)) < 8000


def test_intake_sets_dues_clocks_and_refuses_the_past():
    # the cases the program cannot read: an actor with no plan at all, a note in some other calendar, a pace in words
    w = world("tarnstead_low_fantasy")
    names = [i for i, r in w.tree["npcs"].items() if r.get("plan")][:3]
    w.get(f"npcs.{names[0]}.plan").update(dues=[], triggers=[], text="Day 3 at 14:00 the market closes")
    w.get(f"npcs.{names[1]}.plan").update(dues=[], triggers=[], text=None)
    w.get(f"npcs.{names[2]}.plan").update(dues=[], triggers=[], text=None)
    pid = next(iter(w.tree["active_world_pressures"]))
    w.tree["active_world_pressures"][pid]["clock"].update(pace="whenever the tide turns", due="0318-01-07 16:45")
    w.tree["active_world_pressures"][pid]["clock"].pop("due_at", None)
    keep = [f"npcs.{n}" for n in names] + [f"active_world_pressures.{pid}"]
    assert set(keep) <= set(w.needs_intake())
    for p in set(w.needs_intake()) - set(keep):
        (w.get(p + ".plan") or {}).update(triggers=["x"], text=None) if p.split(".")[0] != "active_world_pressures" else w.get(p + ".clock").pop("due")
    good = {"actors": [{"id": p, "dues": [{"day_offset": 1, "at": "dawn", "what": "x"}], "triggers": [], "interval_minutes": 1440} for p in keep]}
    bad = {"actors": [{"id": p, "dues": [{"day_offset": 0, "at": "00:10", "what": "past"}], "triggers": []} for p in keep]}
    llm = Scripted([bad, good])
    flow.intake(w, llm, batch=4)
    assert not [p for p in keep if p in w.needs_intake()]
    assert "past" in llm.seen[1][1]
    assert w.get(f"active_world_pressures.{pid}.clock.due_at") == {"day": 1, "clock": 360} and w.get(f"active_world_pressures.{pid}.clock.interval_minutes") == 1440


# ---------- small things that stayed true ----------

def test_ai_cannot_write_owned_paths_and_plans_fire_in_order():
    w = world()
    for p in ("player.money", "player.condition.hp", "world_state.time.clock_minutes", "round", "pending"):
        with pytest.raises(WriteRefused):
            w.apply({"op": "set", "path": p, "value": 999})
    w.apply({"op": "plan", "path": "npcs.hobb_marren", "value": "opens the shutters", "due_in_minutes": 90})
    w.apply({"op": "plan", "path": "npcs.tobias_wren", "value": "leaves", "due_in_minutes": 30})
    assert w.due() == []
    w.advance(100)
    assert [p for p, _ in w.due()] == ["npcs.tobias_wren", "npcs.edda_pryce", "npcs.hobb_marren"]


def test_fight_runs_in_code():
    w = world()
    out = {"foes": [{"id": "thug", "name": "Thug", "v": 1, "size": "normal"}],
           "exchanges": [{"foe": "thug", "roll": {"capability": 0, "base": 10}, "on_success": "full", "my_source": "unarmed",
                          "on_failure": "loss", "attackers": [{"who": "Thug", "source": "man-sized"}]}] * 6}
    lines, facts, owed = combat.run(w, out, random.Random(3))
    assert any("Exchange 1" in l for l in lines) and 0 <= w.player["condition"]["hp"] <= M.max_hp(1)


def test_down_then_hit_is_dead_and_sticks():
    w = world()
    w.player["condition"]["hp"] = 0
    w.hurt([3])
    assert w.player_state() == "dead"


def test_unknown_damage_source_is_refused():
    with pytest.raises(M.RuleError):
        combat.damage_roll("laser")


def test_money_as_a_record_still_pays_and_never_goes_below_zero():
    w = world("tarnstead_low_fantasy")
    amount, cur = w.cash()
    w.pay(-5)
    assert w.cash()[0] == amount - 5 and cur
    with pytest.raises(M.RuleError):
        w.pay(-10 ** 6)


def test_wh_question_and_unsupported_likelihood_are_not_rolled():
    t = flow.Turn(world(), "x")
    t.final = True
    flow.h_ask_roll(t, {"asks": [
        {"question": "What has been happening in town?", "obvious": "none", "likelihood": 3},
        {"question": "Does Hobb have a spare room?", "obvious": "none", "likelihood": 2},
        {"question": "Does Hobb have a spare room?", "obvious": "none", "likelihood": 2, "for": "the house is half empty"}]})
    assert len([l for l in t.lines if l.startswith("ask")]) == 1


def test_a_looping_narrator_is_cut_off_by_the_program():
    loop = "You step onto the quay. Gulls circle overhead.\n\n" + "\n".join(
        f'You tell him your favourite thing is number {i}, and he smiles. "That is a great thing."' for i in range(1, 60))
    out = flow.clean("```text\n" + loop + "\n```")
    assert len(out.split()) <= flow.MAX_WORDS and "```" not in out
    assert flow.clean("The door opens. The door opens. The door opens. A man enters.") == "The door opens. A man enters."


def test_naming_a_person_who_is_here_is_never_a_fast_action():
    w = world()
    llm = Scripted([FAST, {"asks": []}, {"minutes": 5, "ops": []}, "Hobb nods.", OK])
    t = flow.run_turn(w, llm, "I ask Hobb whether he has a room")
    assert "react" in t.ran and t.sort["kind"] == "loop"
    w2 = world()
    t = flow.run_turn(w2, Scripted([FAST, "You sit.", OK]), "I sit down")
    assert "react" not in t.ran


def test_the_player_is_moved_by_the_program_when_the_ai_says_where_they_end_up():
    w = world()
    w.tree["locations"]["yard"] = {"name": "Yard", "conditions": {}, "challenge_band": {"min": 1, "max": 3, "basis": "x"}}
    turn = flow.Turn(w, "go to the yard")
    flow.h_commit(turn, {"minutes": 10, "ops": [], "moved_to": "yard"})
    assert w.tree["world_state"]["location"] == "yard"
    with pytest.raises(M.RuleError, match="not a place"):
        flow.h_commit(flow.Turn(w, "x"), {"minutes": 1, "ops": [], "moved_to": "the moon"})
    assert w.tree["world_state"]["location"] == "yard"


def test_extra_exchanges_after_the_foe_fell_do_not_add_noise():
    w = world()
    out = {"foes": [{"id": "rat", "name": "rat", "v": 1, "size": "small"}], "stop": "x", "kill": True,
           "exchanges": [{"foe": "rat", "roll": {"capability": 4, "base": 18, "skill": None}, "on_success": "full", "my_source": "unarmed",
                          "on_failure": "setback", "attackers": []} for _ in range(3)]}
    lines, facts, owed = combat.run(w, out)
    assert not any("already" in f for f in facts)


def test_confirm_with_nothing_pending_is_refused():
    w = world()
    with pytest.raises(M.RuleError, match="nothing is waiting"):
        flow.h_route(flow.Turn(w, "I take the case"), {"kind": "confirm", "steps": []})


def test_a_telling_that_just_repeats_the_player_is_sent_back():
    w = world()
    t = flow.Turn(w, "I take Nadia's case at $700 flat, $350 up front.")
    with pytest.raises(M.RuleError, match="repeats the player"):
        flow.h_show(t, "I take Nadia's case at $700 flat, $350 up front.")
    flow.h_show(t, "Nadia reads the figure back off her folder and nods once.")
    assert t.prose.startswith("Nadia")


def test_the_program_reads_dated_notes_itself():
    from localgm.state import parse_note
    t = {"date": "2026-10-06", "day_index": 0}
    dues, trig = parse_note("2026-10-07 00:30 on Rusk's freight run; immediately if discovered", t, "m")
    assert dues == [{"day": 1, "clock": 30, "what": "on Rusk's freight run"}] and trig == ["immediately if discovered"]
    assert parse_note("2026-10-07 dawn to reconsider", t)[0][0]["clock"] == 360
    dues, trig = parse_note("at the first reply on Oct 6 evening; if unanswered, 2026-10-06 20:30 she leaves", t)
    assert dues == [{"day": 0, "clock": 1230, "what": "if unanswered, she leaves"}] and trig == ["at the first reply on Oct 6 evening"]
    dues, _ = parse_note("next assessment 2026-10-20, or sooner on a valid resonance", t)
    assert dues == [{"day": 14, "clock": 540, "what": "next assessment, or sooner on a valid resonance"}]      # no time written: morning
    assert parse_note("Day 12 at 12:00 messenger due back", t) is None                                         # not the program's calendar


def test_no_example_world_needs_the_ai_to_read_a_date():
    for name in ("ashfall_hunter", "tarnstead_low_fantasy", "last_scion_boundary", "cyberpunk_red_south_nc", "harbour_guesthouse"):
        w = world(name)
        todo = w.needs_intake()
        assert all(w.get(p + ".plan") and not w.get(p + ".plan.text") for p in todo), (name, todo)     # only actors with no plan at all remain


def test_the_ai_cannot_move_a_date_the_note_gives():
    w = world("harbour_guesthouse")
    path = "npcs.hobb_marren"
    w.get(path + ".plan")["text"] = "Day-end ledger; 2026-10-05 19:30 closes the desk"
    wrong = {"id": path, "dues": [{"day_offset": 1, "at": "19:30", "what": "x"}], "triggers": []}
    with pytest.raises(ValueError, match="no due of yours is on it"):
        flow._check_dates(w, wrong)
    flow._check_dates(w, {"id": path, "dues": [{"day_offset": 0, "at": "19:30", "what": "x"}], "triggers": []})


def test_a_pressure_with_a_dated_first_check_and_a_pace_is_set_by_the_program():
    w = world("ashfall_hunter")
    c = w.tree["active_world_pressures"]["glass_spread"]["clock"]
    assert c["due_at"] == {"day": 4, "clock": 19 * 60 + 40} and c["interval_minutes"] == 4 * 1440


def test_the_telling_is_told_who_the_player_character_is():
    w = world("ashfall_hunter")
    t = flow.Turn(w, "I look around")
    for sid in ("tell", "audit", "sort"):
        step = next(s for s in flow.load_steps() if s["id"] == sid)
        text = flow.inputs(step, t)
        assert "THE PLAYER CHARACTER" in text and "Rin Hale" in text, sid


def test_a_reply_cut_off_by_the_token_limit_is_closed_and_checked():
    from localgm.backend import parse_json
    cut = '{"kind": "loop", "steps": ["react", "quest"], "note": "Nadia is affected: she came to hire Ri'
    out = parse_json(cut)
    assert out["kind"] == "loop" and out["steps"] == ["react", "quest"] and out["note"].startswith("Nadia")
    assert parse_json('{"a": [1, 2, {"b": "x"}, "tr')["a"][:2] == [1, 2]


def test_arrays_in_a_form_have_a_length_limit():
    from localgm import schema
    sch = flow.load_steps()[0]["output"]
    capped = schema.cap_arrays(sch)
    assert capped["properties"]["steps"]["maxItems"] == 6 and "maxItems" not in sch["properties"]["steps"]


def test_the_decision_gate_stops_the_turn_and_shows_the_options_without_rolling(monkeypatch):
    rolled = []
    monkeypatch.setattr(M, "check", lambda *a, **k: rolled.append(1))
    w = world()
    before = w.round
    t = flow.run_turn(w, Scripted([LOOP_JUDGE, {"verdict": "certain", "cites": ["player"],
                                                 "decision": {"question": "The ferry leaves now. Which way do you go?",
                                                              "options": ["Take the ferry (leaves the envelope undelivered)", "Stay and deliver it (miss the ferry)"]}}]),
                      "I go")
    assert t.halt and "1. Take the ferry" in t.prose and "2. Stay and deliver" in t.prose and not rolled
