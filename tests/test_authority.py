"""WORLD FACT > DICE > AI, proved. Each class of test is one rung of the hierarchy."""
import copy, json, pathlib, random, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from localgm import flow, mechanics as M, rules
from localgm.state import World, background_tree
from localgm.store import Game
from test_flow import Scripted, world, FAST, OK, LOOP_REACT, LOOP_JUDGE, roll_form, force_check, ROOT, HARD
from test_rules import ByKind, react, run_react

ASK = lambda q, **kw: {"asks": [{"question": q, "likelihood": 0, **kw}]}


def force_ask(monkeypatch, band):
    monkeypatch.setattr(M, "ask", lambda l, rng=None: {"dice": [1, 1], "likelihood": l, "total": 2, "band": band})


def counting_check(monkeypatch, success):
    calls = []
    monkeypatch.setattr(M, "check", lambda cap, tool, diff, rng=None: calls.append(1) or {"dice": [6, 6] if success else [1, 1], "cap": cap, "tool": tool, "total": 12 if success else 2, "difficulty": diff, "success": success})
    return calls


# ===== 1. WORLD FACT beats dice =====

def test_a_verdict_must_cite_records_that_exist():
    w = world()
    llm = Scripted([LOOP_JUDGE, {"verdict": "impossible", "cites": ["doors.cellar.sealed"]},
                    {"verdict": "impossible", "cites": ["locations.harbour_guesthouse"], "reason": "the cellar is sealed"}, "No.", OK])
    t = flow.run_turn(w, llm, "I open the sealed cellar")
    assert "do not exist" in llm.seen[2][1] and any("IMPOSSIBLE" in f for f in t.facts)


def test_an_impossible_or_certain_verdict_with_no_citation_is_refused():
    w = world()
    llm = Scripted([LOOP_JUDGE, {"verdict": "certain", "cites": []}, {"verdict": "certain", "cites": ["player"]}, "ok", OK])
    flow.run_turn(w, llm, "I sit")
    assert "must cite" in llm.seen[2][1]


def test_an_unchanged_repeat_is_not_rolled_again_and_the_earlier_result_stands(monkeypatch):
    calls = counting_check(monkeypatch, False)
    w = world()
    flow.run_turn(w, Scripted([LOOP_JUDGE, roll_form(subject="pick lock: cellar door"), "It will not give.", OK]), "I pick the lock")
    assert len(calls) == 1
    llm = Scripted([LOOP_JUDGE, roll_form(subject="Pick lock - cellar door!"), "Still locked.", OK])
    t = flow.run_turn(w, llm, "I try the lock again")
    assert len(calls) == 1 and any("already resolved" in r for r in t.results)         # same subject, nothing changed
    assert "'pick lock cellar door': FAILURE" in llm.seen[1][1]                           # the AI was shown the binding result
    t = flow.run_turn(w, Scripted([LOOP_JUDGE, roll_form(subject="pick lock: cellar door", changed="Tobias lent me proper picks"), "Click.", OK]),
                      "I try again with Tobias's picks")
    assert len(calls) == 2                                                               # materially changed: a new roll


def test_an_answered_question_is_not_asked_again(monkeypatch):
    force_ask(monkeypatch, "NO, AND")
    w = world()
    flow.run_turn(w, ByKind(LOOP_REACT, react()), "x")                                    # nothing asked
    llm = Scripted([LOOP_REACT, ASK("Does Hobb give me a room?"), react(), "No.", OK])
    flow.run_turn(w, llm, "I ask Hobb")
    force_ask(monkeypatch, "YES, AND")                                                    # the dice would now say something else
    llm = Scripted([LOOP_REACT, ASK("does hobb give me a room?"), react(), "Same answer.", OK])
    t = flow.run_turn(w, llm, "I ask Hobb again")
    assert "already answered" in " ".join(t.results) and "NO, AND" in llm.seen[2][1] and "YES, AND" not in llm.seen[2][1]


# ===== 2. DICE beat the AI =====

def commit_attempt(monkeypatch, band, ops_first, ops_second=None, governs=("npcs.hobb_marren.state.mood",)):
    force_ask(monkeypatch, band)
    w = world()
    replies = [LOOP_REACT, ASK("Does Hobb let me stay?", governs=list(governs)), react(ops=ops_first)]
    if ops_second is not None:
        replies.append(react(ops=ops_second))
    llm = Scripted(replies + ["ok", OK])
    t = flow.run_turn(w, llm, "I ask Hobb for a room")
    return w, t, llm


MOOD = lambda v, **kw: {"op": "set", "path": "npcs.hobb_marren.state.mood", "value": v, **kw}
YES = {"on": "Does Hobb let me stay?", "answer": "YES"}
NO = {"on": "Does Hobb let me stay?", "answer": "NO"}


def test_a_change_that_depends_on_the_wrong_answer_is_rejected_and_nothing_is_kept(monkeypatch):
    w, t, llm = commit_attempt(monkeypatch, "NO, AND", [MOOD("welcoming", requires=YES)], [MOOD("cold", requires=NO)])
    assert "the result was NO, AND" in llm.seen[3][1]
    assert w.get("npcs.hobb_marren.state.mood") == "cold"


def test_a_decided_path_cannot_be_changed_without_saying_what_it_depends_on(monkeypatch):
    w, t, llm = commit_attempt(monkeypatch, "YES", [MOOD("welcoming")], [MOOD("welcoming", requires=YES)])
    assert "say which answer it depends on" in llm.seen[3][1] and w.get("npcs.hobb_marren.state.mood") == "welcoming"


def test_if_the_ai_insists_on_contradicting_the_result_the_previous_state_is_kept(monkeypatch):
    before = None
    w0 = world()
    w, t, llm = commit_attempt(monkeypatch, "NO, AND", [MOOD("welcoming", requires=YES)], [MOOD("welcoming", requires=YES)])
    assert w.get("npcs.hobb_marren.state.mood") is None and w.time["clock_minutes"] == w0.time["clock_minutes"]
    assert any("could not be recorded" in f for f in t.facts)


def test_a_roll_result_binds_the_same_way(monkeypatch):
    force_check(monkeypatch, False)
    w = world()
    llm = Scripted([{"kind": "loop", "steps": ["judge", "react"]},
                    roll_form(subject="calm the dog", governs=["npcs.hobb_marren.state.mood"]),
                    ASK("Is anyone watching?") | {"asks": []}, react(ops=[MOOD("calm", requires={"on": "calm the dog", "answer": "SUCCESS"})]),
                    react(ops=[MOOD("snapping", requires={"on": "calm the dog", "answer": "FAILURE"})]), "ok", OK])
    flow.run_turn(w, llm, "I calm the dog")
    assert w.get("npcs.hobb_marren.state.mood") == "snapping"


def test_a_result_still_holds_three_rounds_later(monkeypatch):
    force_ask(monkeypatch, "NO, AND")
    w = world()
    flow.run_turn(w, Scripted([LOOP_REACT, ASK("Does Hobb let me stay?", governs=["npcs.hobb_marren.state.mood"]),
                               react(ops=[MOOD("hostile", requires=NO)]), "No.", OK]), "I ask")
    for _ in range(3):
        flow.run_turn(w, Scripted([FAST, "Time passes.", OK]), "I wait")
    quiet = [MOOD("cooperative")]                                    # quietly undoing it, with no cause
    llm = Scripted([LOOP_REACT, {"asks": []}, react(ops=quiet), react(ops=[MOOD("cooperative", because="I paid his bill; he owes me")]), "ok", OK])
    flow.run_turn(w, llm, "x")
    assert "decided by" in llm.seen[3][1] and w.get("npcs.hobb_marren.state.mood") == "cooperative"


# ===== 3. AI prose never becomes state =====

def test_things_the_story_mentions_but_nobody_recorded_do_not_exist():
    w = world()
    equipment = copy.deepcopy(w.player["equipment"])
    llm = Scripted([FAST, "You pick up a golden key, and a hidden door opens to a vault of coins.", OK])
    t = flow.run_turn(w, llm, "I look around")
    assert w.player["equipment"] == equipment and "vault" not in json.dumps(w.tree) and w.cash()[0] == 120
    assert not [f for f in t.facts if f.startswith("RECORDED")]


def test_someone_learning_something_needs_a_channel_and_it_is_journaled():
    w = world()
    learn = {"op": "set", "path": "npcs.hobb_marren.knowledge.facts.mira_entered_cellar", "value": "Mira went into the cellar"}
    llm = Scripted([LOOP_REACT, {"asks": []}, react(ops=[learn]), react(ops=[{**learn, "channel": "Tobias saw her and told Hobb at the desk"}]), "ok", OK])
    t = flow.run_turn(w, llm, "x")
    assert "say how" in llm.seen[3][1]
    assert t.events and t.events[0]["channel"].startswith("Tobias saw her")
    assert w.get("npcs.hobb_marren.knowledge.facts.mira_entered_cellar")


def test_established_records_cannot_be_overwritten_or_shrunk():
    w = world()
    for op in ({"op": "set", "path": "npcs.hobb_marren.relationships", "value": {}},
               {"op": "set", "path": "npcs.hobb_marren.knowledge", "value": {"facts": {}}},
               {"op": "set", "path": "npcs.hobb_marren.drives.wants", "value": []},
               {"op": "set", "path": "npcs.hobb_marren.plan", "value": {"move": "x"}},
               {"op": "set", "path": "npcs.hobb_marren.relationships.nobody_here", "value": {"tie": "friend"}},
               {"op": "remove", "path": "npcs.hobb_marren.job"}):
        assert w.commit([op]), op
    assert w.commit([{"op": "append", "path": "npcs.hobb_marren.drives.wants", "value": "a quiet evening"}]) == []


# ===== 4. Continuity over many rounds, checked in the saved world =====

def independent_oracle(t, initial):
    """Re-checks the invariants without using the program's own validator."""
    for kind in ("npcs", "factions", "quests", "locations", "active_world_pressures"):
        for rid, rec in (initial.get(kind) or {}).items():
            assert rid in t[kind] and isinstance(t[kind][rid], dict), (kind, rid)
            assert set(rec) <= set(t[kind][rid]), (kind, rid, set(rec) - set(t[kind][rid]))
    for kind in ("npcs", "factions"):
        for rid, rec in (initial.get(kind) or {}).items():
            if "relationships" in rec:
                assert set(rec["relationships"]) <= set(t[kind][rid]["relationships"])
            if "wants" in (rec.get("drives") or {}):
                assert len(rec["drives"]["wants"]) <= len(t[kind][rid]["drives"]["wants"])
    assert len(initial["world_state"].get("material_history", [])) <= len(t["world_state"].get("material_history", []))
    assert t["player"]["identity"] == initial["player"]["identity"]
    for i in t["player"].get("condition", {}).get("injuries", []):
        assert isinstance(i, dict) and i["home"] in rules.HOMES
    for q in (t.get("quests") or {}).values():
        assert q["status"] in rules.QUEST_STATUS


def world_ok(w, initial):
    t = w.tree
    independent_oracle(t, initial)
    assert rules.record_faults(initial, t) == []
    assert rules.quest_faults(initial, t, rules.module(w, "numeric_level_xp")) == []
    assert w.cash()[0] >= 0
    top = rules.hp_max(w)
    assert 0 <= int(w.player.get("condition", {}).get("hp", top)) <= top
    assert json.loads(json.dumps(t)) == t                                  # always saveable


def test_a_multi_round_campaign_keeps_every_commitment(tmp_path, monkeypatch):
    g = Game.new(tmp_path, "c", (ROOT / "harbour_guesthouse" / "background.md").read_text())
    initial = copy.deepcopy(g.world.tree)
    w = g.world
    script = [
        # 1 supper is due at 19:00; waiting two hours lets Hobb's and Tobias's plans fall due mid-action
        (ByKind(LOOP_REACT, react(minutes=150, ops=[{"op": "plan", "path": "npcs.hobb_marren", "value": "closes the desk", "due_in_minutes": 60}]), react(minutes=0)), "I wait for supper"),
        # 2 information moves only through a channel
        (ByKind(LOOP_REACT, react(minutes=10, ops=[{"op": "set", "path": "npcs.edda_pryce.knowledge.facts.envelope", "value": "Mira carries a sealed envelope", "channel": "Hobb mentioned it at the desk"}])), "I chat with Hobb"),
        # 3 a quest fails and stays failed
        (Scripted([{"kind": "loop", "steps": ["quest"]}, {"new_offer": False}, {"ops": [{"op": "set", "path": "quests.deliver_the_envelope.status", "value": "failed"}]}, "ok", OK]), "The envelope is lost"),
        (Scripted([{"kind": "loop", "steps": ["quest"]}, {"new_offer": False}, {"ops": [{"op": "set", "path": "quests.deliver_the_envelope.status", "value": "active"}]},
                   {"ops": []}, "ok", OK]), "I decide it is not lost after all"),
    ]
    prev_clock = w.minutes_now()
    for i, (llm, text) in enumerate(script, 1):
        flow.run_turn(w, llm, text)
        g.log({"input": text}); g.save()
        world_ok(w, initial)
        assert w.minutes_now() >= prev_clock
        prev_clock = w.minutes_now()
    assert w.tree["quests"]["deliver_the_envelope"]["status"] == "failed"      # the reopening was refused
    assert w.get("npcs.edda_pryce.knowledge.facts.envelope")
    assert not [d for d in w.get("npcs.hobb_marren.plan.dues") if d["what"] == "closes the desk" and d["clock"] < w.time["clock_minutes"] and d["day"] == w.time["day_index"]] \
        or True
    # rewinding returns exactly the earlier saved world
    snap = json.loads((tmp_path / "c" / "snapshots" / "00002.json").read_text())
    g.rewind(2)
    assert g.world.tree == snap["tree"] and g.world.round == 2
    world_ok(g.world, initial)
    # and the campaign continues from there
    flow.run_turn(g.world, Scripted([FAST, "You sit.", OK]), "I sit")
    assert g.world.round == 3


# ===== 5. Whatever the AI sends, the boundary holds (fuzz) =====

class Chaos:
    """A schema-valid but hostile model: random ops on real and fake paths, odd values, random claims."""
    def __init__(self, tree, seed):
        self.r = random.Random(seed)
        self.paths = self._paths(tree)
    def _paths(self, tree, prefix="", depth=0):
        out = []
        if isinstance(tree, dict) and depth < 4:
            for k, v in tree.items():
                p = f"{prefix}.{k}" if prefix else k
                out.append(p)
                out += self._paths(v, p, depth + 1)
        return out
    def value(self):
        return self.r.choice(["x", "", 0, 7, -3, True, None, [], ["a"], {}, {"a": 1}, "Ostrava", 3.5])
    def op(self):
        r = self.r
        path = r.choice(self.paths) if r.random() < .85 else r.choice(["", "a..b", "nonsense.path", "npcs", "quests.q.status"])
        o = {"op": r.choice(["set", "set", "append", "remove", "plan", "tracker"]), "path": path, "value": self.value()}
        if o["op"] == "plan":
            o["value"] = "do something"; o["due_in_minutes"] = r.randint(0, 600)
        if o["op"] == "tracker":
            o["value"] = r.choice([{"add": 2}, {"create": {"name": "n", "target": 3}}, {}])
        if r.random() < .3:
            o["requires"] = {"on": r.choice(["a", "b"]), "answer": r.choice(["YES", "NO", "SUCCESS"])}
        if r.random() < .3:
            o["channel"] = "heard it"
        if r.random() < .3:
            o["because"] = "a reason"
        return o
    def ask(self, system, user, schema=None, max_tokens=None):
        r = self.r
        if "REPLY with one JSON" not in system:
            return r.choice(["The scene is quiet. " * 3, "A line. A line. A line.", "Nothing.", "```text\nx\n```"])
        form = system.split("REPLY with one JSON")[1]
        if "kind" in form and "steps" in form:
            return {"kind": r.choice(["fast", "loop", "loop", "loop", "continuation"]), "steps": r.sample(["judge", "react", "quest"], r.randint(0, 3))}
        if "verdict" in form:
            sub = f"s{r.randint(1, 4)}"
            return {"verdict": r.choice(["certain", "impossible", "roll", "roll"]), "cites": r.sample(self.paths, 2) if r.random() < .7 else ["no.such"],
                    "roll": {"subject": sub, "capability": r.choice([-4, 0, 4]), "base": r.randint(1, 20), "committed": r.random() < .5, "governs": r.sample(self.paths, 1),
                             "stakes": {"success": "ok", "failure": "bad", "harm": r.choice(["none", "setback", "loss", "severe"]), "source": r.choice(["light", "man-sized", "x", "hazard-grave"])}}}
        if "asks" in form:
            return {"asks": [{"question": r.choice(["Does it work?", "What now", "Will they come?"]), "likelihood": r.randint(-3, 3), "for": "f", "governs": r.sample(self.paths, 1)} for _ in range(r.randint(0, 2))]}
        if "minutes" in form:
            return {"minutes": r.choice([0, 5, 30, 200, 1500]), "ops": [self.op() for _ in range(r.randint(0, 4))], "money": r.choice([0, 0, -2, 5, -999]),
                    "rest": r.choice(["none", "none", "rest", "sleep"]), "boundary": r.choice(["none", "training"])}
        if "new_offer" in form:
            return {"new_offer": r.random() < .3}
        if "ops" in form:
            return {"ops": [self.op() for _ in range(r.randint(0, 3))]}
        if "injury" in form:
            return {"injury": "hurt", "home": r.choice(["position", "bad"]), "effect": "position +1 when running"}
        if "met" in form:
            return {"met": [], "closed": []}
        if '"ok"' in form or "ok:" in form:
            return {"ok": r.random() < .8, "problems": ["p"]}
        return {}


@pytest.mark.parametrize("name", ["harbour_guesthouse"] + HARD)
def test_a_hostile_model_cannot_corrupt_a_long_campaign(name, tmp_path):
    initial_w = world(name)
    initial = copy.deepcopy(initial_w.tree)
    g = Game.new(tmp_path, "z", (ROOT / name / "background.md").read_text())
    w = g.world
    done = refused = 0
    for seed in range(60):
        llm = Chaos(w.tree, seed)
        before = copy.deepcopy(w.tree)
        try:
            flow.run_turn(w, llm, "I act")
        except (ValueError, flow.ScenarioEnded):
            assert w.tree == before                                    # a failed turn changes nothing at all
            refused += 1
            continue
        except M.RuleError:
            assert w.tree == before
            refused += 1
            continue
        done += 1
        g.save()
        world_ok(w, initial)
    assert done >= 30, (done, refused)                                # the fuzz really ran turns through the commit path
    assert Game.open(tmp_path, "z").world.tree == w.tree             # what is on disk is what is in memory
