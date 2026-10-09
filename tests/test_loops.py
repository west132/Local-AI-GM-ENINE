"""Every step of the workflow runs inside a real turn, in the order steps.yaml gives, and every typed change reaches the world."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from localgm import flow, mechanics as M
from test_flow import world, force_check, FAST, roll_form, OK


class Bot:
    """Answers each form by what it asks for. `r` maps a form name to a reply (or a list used in order)."""
    def __init__(self, **r):
        self.r = {"sort": FAST, "judge": {"verdict": "certain", "cites": ["player"]}, "fight": None, "wonder": {"asks": []},
                  "react": {"asks": [], "minutes": 5, "ops": []}, "offer": {"new_offer": False}, "quest": {"ops": []}, "injury": None,
                  "ending": {"met": [], "closed": []}, "checkpoint": {"ops": [], "notes": []}, "audit": OK, "tell": "It happens.",
                  "epilogue": "And so it ended."}
        self.r.update(r)
        self.seen = []

    def kind(self, system):
        if "REPLY with one JSON object only:" not in system:
            return "epilogue" if "epilogue" in system.lower()[:300] or "## 21" in system else "tell"
        form = system.split("REPLY with one JSON object only:")[1].lstrip()
        for key, name in (("kind:", "sort"), ("verdict:", "judge"), ("foes?:", "fight"), ("new_offer:", "offer"), ("injury:", "injury"),
                          ("met:", "ending"), ("ok:", "audit")):
            if form.startswith(key):
                return name
        if form.startswith("asks:"):
            return "wonder"
        if form.startswith("asks?:") or "minutes:" in form:
            return "react"
        return "checkpoint" if "notes?:" in form else "quest"

    def ask(self, system, user, schema=None, max_tokens=None):
        k = self.kind(system)
        self.seen.append(k)
        r = self.r[k]
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        return r


def run(w, text="x", **r):
    bot = Bot(**r)
    return flow.run_turn(w, bot, text), bot


def test_every_step_in_steps_yaml_runs_in_a_real_turn(monkeypatch):
    ran = set()

    def go(w, **r):
        t, _ = run(w, **r)
        ran.update(t.ran)
        return t

    go(world(), sort=FAST)                                                                   # sort, tell, audit
    force_check(monkeypatch, False)
    w = world(); w.player["condition"]["hp"] = 2
    t = go(w, sort={"kind": "loop", "steps": ["judge"]},
           judge=roll_form(committed=True, stakes={"harm": "severe", "source": "man-sized", "failure": "you are cut"}),
           injury={"injury": "a torn arm", "home": "capability", "effect": "the right arm cannot lift much"})
    assert "injury" in t.ran                                                                 # injury
    w = world(); w.tree["pending"] = {"roll": {"subject": "leap the gap", "capability": 0, "base": 20, "stakes": {"success": "s", "failure": "f", "harm": "none"}}, "ask": "x", "action": "y"}
    go(w, sort={"kind": "confirm", "steps": []})                                             # confirmed
    w = world()
    go(w, sort={"kind": "loop", "steps": ["fight", "react"]},
       fight={"foes": [{"id": "rat", "name": "rat", "v": 1, "size": "small"}], "stop": "x", "kill": True,
              "exchanges": [{"foe": "rat", "roll": {"capability": 4, "base": 18}, "on_success": "full", "my_source": "unarmed", "on_failure": "setback", "attackers": []}]})
    go(world(), sort={"kind": "loop", "steps": ["quest"]})                                   # offer, quest
    w = world(); w.tree["enabled_modules"]["bounded_scenario_endings"] = True
    w.tree["ending_conditions"] = {"core_conditions": ["the envelope reaches Tobias"], "hidden_conditions": []}
    go(w, sort={"kind": "loop", "steps": ["react"]}, ending={"met": ["core.0"], "closed": []})   # ending, epilogue
    w = world(); w.round = 9
    go(w, sort=FAST)                                                                         # checkpoint
    expected = {s["id"] for s in flow.load_steps()}
    assert expected - ran == set(), f"never ran in a turn: {expected - ran}"


def test_a_fight_turn_goes_through_the_whole_loop(monkeypatch):
    force_check(monkeypatch, True)
    w = world()
    t, bot = run(w, "I hit the rat", sort={"kind": "loop", "steps": ["fight", "react"]},
                 fight={"foes": [{"id": "rat", "name": "rat", "v": 1, "size": "small"}], "stop": "x", "kill": True,
                        "exchanges": [{"foe": "rat", "roll": {"capability": 4, "base": 18}, "on_success": "full", "my_source": "unarmed",
                                       "on_failure": "setback", "attackers": []}] * 3})
    assert t.in_fight and bot.seen.index("fight") < bot.seen.index("wonder") < bot.seen.index("react") < bot.seen.index("tell")
    assert any("Exchange 1" in l for l in t.lines) and w.state_of("rat") == "dead" and w.round == 1
    assert not any("already" in r for r in t.results)


def test_a_supply_draw_and_a_resupply_are_applied_by_the_program():
    w = world()
    w.player["resources"] = {"torches": {"name": "torches", "tracking": "exact", "count": 5}}
    run(w, sort={"kind": "loop", "steps": ["react"]},
        react={"asks": [], "minutes": 5, "ops": [], "draw": [{"resource": "torches", "amount": 2}]})
    assert w.player["resources"]["torches"]["count"] == 3
    w.player["resources"]["torches"]["count"] = 0
    t, _ = run(w, sort={"kind": "loop", "steps": ["react"]}, react={"asks": [], "minutes": 5, "ops": [], "resupply": [{"resource": "torches", "count": 4}]})
    assert w.player["resources"]["torches"]["count"] == 4


def test_a_chain_offer_rolls_a_first_child(monkeypatch):
    monkeypatch.setattr(M, "roll", lambda n, s, rng=None: [10] if s == 10 else [2])
    w = world()
    t = flow.Turn(w, "x")
    flow.h_shape_roll(t, {"new_offer": True})
    assert t.shape == "CHAIN" and any("first child" in l for l in t.lines)


def test_a_name_where_an_id_belongs_is_sent_back_not_a_crash():
    w = world()
    t, bot = run(w, sort={"kind": "loop", "steps": ["react"]},
                 react=[{"asks": [], "minutes": 5, "ops": [], "heal": [{"who": "Hobb Marren", "source": "standard"}]},
                        {"asks": [], "minutes": 5, "ops": [], "heal": [{"who": "hobb_marren", "source": "standard"}]}])
    assert w.round == 1 and bot.seen.count("react") >= 2          # the first reply was refused with the reason, the second was recorded


def test_any_stray_exception_from_a_reply_becomes_a_retry(monkeypatch):
    w = world()
    calls = []
    real = flow.h_commit
    def flaky(turn, out):
        calls.append(1)
        if len(calls) == 1:
            raise KeyError("Nadia Voss")
        return real(turn, out)
    monkeypatch.setitem(flow.HANDLERS, "commit", flaky)
    t, _ = run(w, sort={"kind": "loop", "steps": ["react"]})
    assert len(calls) >= 2 and w.round == 1
