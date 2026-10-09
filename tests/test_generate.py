import copy, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from localgm import generate as G
from localgm.state import World, background_tree
from localgm.store import Game

from localgm.demo_forms import PREMISE, ECONOMY, PLAYER, PLACES, CAST, STORY, GOOD


class Forms:
    """Answers each form by the fields it asks for. `bad` swaps in a faulty first answer for one form."""
    def __init__(self, bad=None):
        self.bad, self.calls, self.seen = bad or {}, [], []

    def ask(self, system, user, schema=None, max_tokens=None):
        stage = next(k for k, v in {"premise": "title", "economy": "groups", "player": "source_abilities", "places": "start_location",
                                    "cast": "npcs", "story": "quests"}.items() if k_in(schema, v))
        self.calls.append(stage); self.seen.append(user)
        if self.bad.get(stage) and self.calls.count(stage) == 1:
            return copy.deepcopy(self.bad[stage])
        return copy.deepcopy(GOOD[stage])


def k_in(schema, name):
    return name in (schema or {}).get("properties", {})


def test_generates_a_world_that_loads_and_plays():
    text, ctx = G.generate(Forms(), "A grim road fantasy in Ember Road")
    w = World(background_tree(text))
    t = w.tree
    assert t["enabled_modules"] == {"numeric_level_xp": True, "equipment_power_tiers": True, "bounded_scenario_endings": False, "flexible_item_entitlement": True}
    assert t["player"]["progression"]["state"]["level"] == 4 and t["player"]["starting_item_points"]["points"] == 2
    assert t["setting_anchors"]["prices"]["gear"]["short_sword"] == "40 silver"
    assert "Parry Strike" in t["player"]["skills"]["swordwork"]["abilities"]
    assert all(" " in n["name"] for n in t["npcs"].values()) and all(n["gender"] for n in t["npcs"].values())
    assert t["npcs"]["mara_voss"]["plan"]["dues"][0]["clock"] == 540        # 09:00 became a due the program tracks
    assert w.needs_intake() == ["npcs.dorn_pell", "active_world_pressures.wolf_spread"]  # a trigger and a clock go to the start-up step
    assert t["world_state"]["location"] == "toll_gate" and t["locked_case_truths"]["pit_cause"]["evidence"]["routes"]


def test_the_world_opens_as_a_game(tmp_path):
    text, _ = G.generate(Forms(), "x")
    wid = G.save_world(tmp_path, text)
    assert (tmp_path / "worlds" / wid / "background.md").exists()
    g = Game.new(tmp_path / "saves", "g", text)
    assert g.world.round == 0


@pytest.mark.parametrize("stage,mutate,word", [
    ("player", lambda p: p.update(name="Kell"), "full name"),
    ("player", lambda p: p.update(gender="  "), "gender"),
    ("player", lambda p: p.update(source_abilities=[{"ability": "Fire Leap", "skill": "swordwork"}]), "must also be listed"),
    ("player", lambda p: p["equipment"][0].update(price_ref="moon sword"), "price list"),
    ("economy", lambda e: e["groups"][0]["items"][0].update(price="a fair sum"), "has no number"),
    ("cast", lambda c: c["npcs"][0].update(name="Mara"), "full name"),
    ("cast", lambda c: c["npcs"][1].update(due="sometime soon"), "due"),
    ("cast", lambda c: c["npcs"][0].update(position="the moon"), "place id"),
    ("story", lambda s: s["pressures"][0].update(pace="monthly"), "pace"),
])
def test_faults_are_sent_back_and_fixed(stage, mutate, word):
    bad = copy.deepcopy(GOOD[stage]); mutate(bad if stage != "cast" and stage != "economy" else bad)
    f = Forms(bad={stage: bad})
    text, _ = G.generate(f, "x")
    assert f.calls.count(stage) == 2                       # one bad answer, one fixed
    assert any(word in u for u in f.seen if "last answer had these faults" in u)
    assert World(background_tree(text))


def test_gives_up_with_the_reason_when_the_ai_will_not_fix_it():
    bad = copy.deepcopy(PLAYER); bad["name"] = "Kell"
    class Stubborn(Forms):
        def ask(self, system, user, schema=None, max_tokens=None):
            if k_in(schema, "source_abilities"):
                return copy.deepcopy(bad)
            return super().ask(system, user, schema, max_tokens)
    with pytest.raises(ValueError, match="full name"):
        G.generate(Stubborn(), "x")


def test_modules_cannot_be_dropped_without_a_reason():
    p = copy.deepcopy(PREMISE); p["modules"]["equipment_power_tiers"] = {"on": False, "why": "no"}
    f = Forms(bad={"premise": p})
    G.generate(f, "x")
    assert f.calls.count("premise") == 2


def test_original_world_needs_no_source_abilities():
    p = copy.deepcopy(PREMISE); p.update(mode="original", source_game="", canon_scope="")
    pl = copy.deepcopy(PLAYER); pl["source_abilities"] = []
    class Orig(Forms):
        def ask(self, system, user, schema=None, max_tokens=None):
            if k_in(schema, "title"): return copy.deepcopy(p)
            if k_in(schema, "source_abilities"): return copy.deepcopy(pl)
            return super().ask(system, user, schema, max_tokens)
    text, _ = G.generate(Orig(), "an original idea")
    assert background_tree(text)["setting"]["mode"] == "original"


def test_a_work_source_gets_its_check_and_it_survives_a_replan():
    g = copy.deepcopy(CAST); g["npcs"][0]["work_source"] = "weekly"
    class W(Forms):
        def ask(self, system, user, schema=None, max_tokens=None):
            return copy.deepcopy(g) if k_in(schema, "npcs") else super().ask(system, user, schema, max_tokens)
    text, _ = G.generate(W(), "x")
    w = World(background_tree(text))
    due = [d for d in w.tree["npcs"]["mara_voss"]["plan"]["dues"] if d.get("work")]
    assert due and due[0]["day"] == 7
    w.tree["npcs"]["mara_voss"]["plan"] = {"move": "x", "dues": [], "triggers": []}       # a replan that loses it
    w.ensure_work()
    assert any(d.get("work") for d in w.tree["npcs"]["mara_voss"]["plan"]["dues"])
