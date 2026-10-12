"""Every step of the workflow runs inside a real turn, in the order steps.yaml gives, and every typed change reaches the world."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from localgm import combat, flow, mechanics as M
from test_flow import world, force_check, FAST, roll_form, OK


class Bot:
    """Answers each form by what it asks for. `r` maps a form name to a reply (or a list used in order)."""
    def __init__(self, **r):
        self.r = {"sort": FAST, "judge": {"verdict": "certain", "cites": ["player"]}, "fight": None, "wonder": {"asks": []},
                  "react": {"asks": [], "report": "It happens.", "minutes": 5, "ops": []}, "offer": {"new_offer": False}, "quest": {"ops": []}, "injury": None,
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
    monkeypatch.setattr(combat, "damage_roll", lambda source, rng=None: (20, "1d8 (forced) = 20"))
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
        react={"asks": [], "report": "It happens.", "minutes": 5, "ops": [], "draw": [{"resource": "torches", "amount": 2}]})
    assert w.player["resources"]["torches"]["count"] == 3
    w.player["resources"]["torches"]["count"] = 0
    t, _ = run(w, sort={"kind": "loop", "steps": ["react"]}, react={"asks": [], "report": "It happens.", "minutes": 5, "ops": [], "resupply": [{"resource": "torches", "count": 4}]})
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
                 react=[{"asks": [], "report": "It happens.", "minutes": 5, "ops": [], "heal": [{"who": "Hobb Marren", "source": "standard"}]},
                        {"asks": [], "report": "It happens.", "minutes": 5, "ops": [], "heal": [{"who": "hobb_marren", "source": "standard"}]}])
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


def test_the_sorters_decision_reaches_the_telling():
    w = world()
    t, bot = run(w, "I put the envelope on the desk", sort={"kind": "fast", "steps": [], "note": "The envelope lies on the desk, squared to its edge."})
    assert any("THE GM'S DECISION" in f and "squared to its edge" in f for f in t.facts)
    from localgm import flow as F
    tell = next(s for s in F.load_steps() if s["id"] == "tell")
    assert "squared to its edge" in F.inputs(tell, t)


def test_a_quiet_kind_without_a_note_is_sent_back():
    w = world()
    t, bot = run(w, sort=[{"kind": "fast", "steps": []}, {"kind": "fast", "steps": [], "note": "ok"}])
    assert bot.seen.count("sort") == 2 and t.sort["note"] == "ok"


def test_a_retrieval_is_answered_from_the_records_the_program_hands_over():
    w = world()
    t, _ = run(w, "What am I carrying?", sort={"kind": "retrieval", "steps": [], "note": "A rucksack, a sealed envelope and a phone."})
    text = "\n".join(t.facts)
    assert "THE PLAYER CHARACTER'S RECORDS" in text and "sealed_envelope" in text and "QUESTS" in text


def test_carrying_on_takes_time_and_the_world_answers():
    w = world()
    before = (w.time["day_index"], w.time["clock_minutes"])
    t, bot = run(w, "I wait for an hour", sort={"kind": "continuation", "steps": [], "note": "An hour passes at the desk."},
                 react={"asks": [], "report": "It happens.", "minutes": 60, "ops": []})
    assert "react" in t.ran and (w.time["day_index"], w.time["clock_minutes"]) > before and w.time["clock_minutes"] == before[1] + 60


def test_the_gms_account_reaches_the_telling_and_secrets_stay_out_of_it():
    w = world()
    t, bot = run(w, "I ask Hobb for a room", sort={"kind": "loop", "steps": ["react"]},
                 react={"asks": [], "report": "Hobb checks the register, finds a free room and hands over the key.", "minutes": 5, "ops": []})
    assert any(f.startswith("WHAT HAPPENED") and "hands over the key" in f for f in t.facts)
    tell = next(s for s in flow.load_steps() if s["id"] == "tell")
    assert "hands over the key" in flow.inputs(tell, t)


def test_a_reaction_without_an_account_is_sent_back():
    w = world()
    t, bot = run(w, sort={"kind": "loop", "steps": ["react"]},
                 react=[{"asks": [], "minutes": 5, "ops": []}, {"asks": [], "report": "Nothing the player notices.", "minutes": 5, "ops": []}])
    assert bot.seen.count("react") == 2 and w.round == 1


def test_a_reaction_that_cannot_be_recorded_drops_the_whole_turn():
    w = world()
    snap, rnd = repr(w.tree), w.round
    bad = {"asks": [], "report": "Gone.", "minutes": 30, "ops": [{"op": "set", "path": "npcs.hobb_marren", "value": "gone"}]}
    with pytest.raises(flow.TurnFailed):
        flow.run_turn(w, Bot(sort={"kind": "loop", "steps": ["react"]}, react=bad), "I wait")
    assert repr(w.tree) == snap and w.round == rnd


def test_a_reply_that_is_never_a_usable_form_drops_the_turn_too():
    w = world()
    class Junk:
        def ask(self, system, user, schema=None, max_tokens=None):
            if schema is None:
                return "text"
            raise ValueError("not json")
    with pytest.raises(flow.TurnFailed, match="'sort' step"):
        flow.run_turn(w, Junk(), "x")
    assert w.round == 0


def test_a_report_that_names_a_hidden_thing_is_sent_back():
    from test_rules import hidden_world
    w = hidden_world()
    t, bot = run(w, "I wait", sort={"kind": "loop", "steps": ["react"]},
                 react=[{"asks": [], "report": "Ostrava slips away from the pier.", "minutes": 5, "ops": []},
                        {"asks": [], "report": "Someone slips away from the pier.", "minutes": 5, "ops": []}])
    assert bot.seen.count("react") == 2 and not any("Ostrava" in f for f in t.facts)


def test_how_many_ai_calls_a_turn_needs():
    """The fewest calls each kind of turn can take, with the two call-saving choices on. (Choices off: +1 audit, +1 separate asking call for a world step.)"""
    from localgm import flow as F
    def calls(sort, **r):
        t_bot = Bot(sort=sort, **r)
        F.run_turn(world(), t_bot, "I act", merge_questions=True, check_telling=False)
        return t_bot.seen
    assert calls({"kind": "fast", "steps": [], "note": "It happens."}) == ["sort", "tell"]
    assert calls({"kind": "retrieval", "steps": [], "note": "A rucksack."}) == ["sort", "tell"]
    assert calls({"kind": "loop", "steps": ["react"]}, react={"asks": [], "report": "Hobb nods.", "minutes": 5, "ops": []}) == ["sort", "react", "tell"]
    ask = {"asks": [{"question": "Does he agree?", "obvious": "none", "likelihood": 0}]}
    assert calls({"kind": "loop", "steps": ["react"]}, react=[ask, {"asks": [], "report": "Hobb nods.", "minutes": 5, "ops": []}]) == ["sort", "react", "react", "tell"]
    assert calls({"kind": "loop", "steps": ["judge", "react"]}, judge=roll_form(committed=True), react={"asks": [], "report": "It works.", "minutes": 5, "ops": []}) == ["sort", "judge", "react", "tell"]


def test_the_judges_reason_for_a_settled_action_is_handed_on():
    w = world()
    t, _ = run(w, sort={"kind": "loop", "steps": ["judge", "react"]},
               judge={"verdict": "certain", "cites": ["player"], "reason": "A trained courier opens an unlocked door."},
               react={"asks": [], "report": "The door opens.", "minutes": 1, "ops": []})
    assert any("SETTLED (no roll): A trained courier" in r for r in t.results)


def test_the_ai_is_shown_the_exact_paths_it_must_cite_and_write():
    w = world("ashfall_hunter")
    t = flow.Turn(w, "x")
    for sid in ("judge", "wonder", "react", "fight"):
        step = next(s for s in flow.load_steps() if s["id"] == sid)
        text = flow.inputs(step, t)
        assert "npcs.nadia_voss —" in text and "PLACES" in text and "hale_workshop" in text and "player.skills" in text, sid


def test_obvious_misspellings_of_a_record_path_are_read_the_programs_way():
    from localgm import rules
    assert rules.canon_path("npc.hobb_marren.state.status") == "npcs.hobb_marren.state.status"
    assert rules.canon_path("person/hobb_marren/drives/wants") == "npcs.hobb_marren.drives.wants"
    assert rules.canon_path("player.money") == "player.money" and rules.canon_path("world_state.location") == "world_state.location"
    w = world()
    rules.check_cites(w, ["npc.hobb_marren.state.status"])                 # was refused before: the record exists, only the spelling was off
    with pytest.raises(M.RuleError):
        rules.check_cites(w, ["npc.nobody.state.status"])                   # a record that does not exist is still refused
    t, _ = run(w, sort={"kind": "loop", "steps": ["react"]},
               react={"asks": [], "report": "Hobb relaxes.", "minutes": 1, "ops": [{"op": "set", "path": "npc.hobb_marren.state.mood", "value": "calm"}]})
    assert w.get("npcs.hobb_marren.state.mood") == "calm"


def test_the_world_step_knows_the_player_it_is_deciding_for():
    w = world("ashfall_hunter")
    step = next(s for s in flow.load_steps() if s["id"] == "react")
    text = flow.inputs(step, flow.Turn(w, "x"))
    assert "THE PLAYER CHARACTER NOW" in text and "Rin Hale" in text and "1950" in text and "Nightglass Blade" in text and "demonic_channeling" in text


def test_a_telling_that_pastes_the_programs_labels_is_sent_back():
    w = world()
    scene = "Hobb runs a thick finger down the register, grunts, and slides a brass key across the desk. \"Room four. Breakfast is at seven.\""
    t, bot = run(w, "I ask Hobb for a room", sort={"kind": "loop", "steps": ["react"]},
                 react={"asks": [], "report": "Hobb checks the register and hands Mira a key.", "minutes": 5, "ops": []},
                 tell=["WHAT HAPPENED: Hobb checks the register and hands Mira a key.", scene])
    assert bot.seen.count("tell") == 2 and t.prose == scene


def test_a_telling_that_only_copies_the_account_is_sent_back():
    w = world()
    scene = "Hobb runs a thick finger down the register, grunts, and slides a brass key across the desk. \"Room four. Breakfast is at seven.\""
    t, bot = run(w, "I ask Hobb for a room", sort={"kind": "loop", "steps": ["react"]},
                 react={"asks": [], "report": "Hobb checks the register and hands Mira a key.", "minutes": 5, "ops": []},
                 tell=["Hobb checks the register and hands Mira a key.", scene])
    assert bot.seen.count("tell") == 2 and t.prose == scene


def test_labels_are_stripped_if_the_ai_still_pastes_them_on_the_last_try():
    w = world()
    t, _ = run(w, "I wait", sort={"kind": "loop", "steps": ["react"]},
               react={"asks": [], "report": "Nothing the player notices.", "minutes": 5, "ops": []}, tell="WHAT HAPPENED: The rain keeps falling on the quay outside.")
    assert "WHAT HAPPENED" not in t.prose and "rain keeps falling" in t.prose


def test_going_to_a_named_place_always_runs_the_world_step_and_moves_the_player():
    w = world()
    t, _ = run(w, "I walk down to the Net Loft on Mill Lane", sort={"kind": "fast", "steps": [], "note": "She walks there."},
               react={"asks": [], "report": "Mira reaches the loft.", "minutes": 15, "moved_to": "net_loft", "ops": []})
    assert t.sort["kind"] == "loop" and "react" in t.sort["steps"] and w.get("world_state.location") == "net_loft"


def test_a_fight_against_a_bystander_who_was_never_attacked_is_sent_back():
    w = world()
    good = {"foes": [{"id": "rat", "name": "rat", "v": 1, "size": "small"}], "stop": "x", "kill": True,
            "exchanges": [{"foe": "rat", "roll": {"capability": 4, "base": 18}, "on_success": "full", "my_source": "unarmed", "on_failure": "setback", "attackers": []}]}
    bad = dict(good, foes=[], exchanges=[dict(good["exchanges"][0], foe="hobb_marren")])
    t, bot = run(w, "I attack the rat", sort={"kind": "loop", "steps": ["fight", "react"]}, fight=[bad, good])
    assert bot.seen.count("fight") == 2 and w.state_of("hobb_marren") == "standing"


def test_every_ai_step_ends_its_message_with_a_task_and_the_sorter_sees_no_secrets():
    w = world("ashfall_hunter")
    steps = [s for s in flow.load_steps() if s.get("ai") is not False]
    assert all(len(s.get("task", "")) > 40 for s in steps), [s["id"] for s in steps if len(s.get("task", "")) <= 40]
    tasks = {s["id"]: s["task"] for s in steps}
    seen = {}
    class Spy:
        def ask(self, system, user, schema=None, max_tokens=None):
            seen["user"], seen["system"] = user, system
            raise ValueError("stop")
    for s in steps:
        t = flow.Turn(w, "I ask Nadia for the locator")
        try:
            flow.run_step(Spy(), s, t)
        except ValueError:
            pass
        assert seen["user"].rstrip().endswith(tasks[s["id"]].strip()[-60:]) or "YOUR TASK NOW" in seen["user"], s["id"]
        assert seen["user"].index("YOUR TASK NOW") >= len(flow.inputs(s, t)), s["id"]          # the task comes after every record the step shows
        if s["id"] == "sort":
            assert "drives" not in seen["user"] and "knowledge" not in seen["user"] and len(seen["system"]) < 9000


# ---------- whole games: the parts working together ----------
# A practice GM (localgm/simgm.py) that reads the real prompts plays whole games through the real loop, the real saves and the real world,
# and after every turn the world must agree with itself (localgm/coherence.py).

WORLDS = ["harbour_guesthouse", "ashfall_hunter", "tarnstead_low_fantasy", "last_scion_boundary", "cyberpunk_red_south_nc"]


def _script(w):
    from localgm import flow as F
    people = [r["name"].split()[0] for r in w.actors_here().values()]
    places = [(i, l["name"]) for i, l in w.tree["locations"].items() if i != w.tree["world_state"]["location"]]
    text = ["I look around.", "What do I have?"]
    if people:
        text.append(f"I ask {people[0]} what is going on.")
    text += ["I wait for an hour.", "I try to climb something nearby."]
    if places:
        text.append(f"I go to {places[0][1]}.")
    text += ["I wait.", "I attack the creature.", "I sleep until morning.", "I wait for a day.", "I wait for a day.", "I wait for a day."]
    return text, places[0][0] if places else None


@pytest.mark.parametrize("name", WORLDS)
def test_a_whole_game_keeps_the_world_in_agreement_with_itself(name, tmp_path):
    import random
    from localgm import coherence
    from localgm.store import Game
    random.seed(7)
    g = Game.new(tmp_path, "g", (__import__("test_flow").ROOT / name / "background.md").read_text(encoding="utf-8"))
    w = g.world
    from localgm.simgm import SimGM
    flow.intake(w, SimGM())
    base = coherence.check(w)
    assert base == [], base                                             # the start of every bundled world agrees with itself
    texts, target = _script(w)
    gm = SimGM()
    for i, text in enumerate(texts, 1):
        before = __import__("copy").deepcopy(w)
        t = flow.run_turn(w, gm, text)
        assert t.prose.strip() and "WHAT HAPPENED" not in t.prose, (text, t.prose)
        found = coherence.check(w) + coherence.check_step(before, w)
        assert found == [], (name, text, found)
        if text.startswith("I go to") and target:
            assert w.get("world_state.location") == target, (text, w.get("world_state.location"))
        if i % 4 == 0:
            g.save()
            assert Game.open(tmp_path, "g").world.tree == w.tree                 # what is on disk is what is in memory
    assert w.round == len(texts) and w.time["day_index"] >= 3                   # three days of waiting really passed, dues and clocks included


def test_a_game_can_be_rewound_exported_imported_and_carried_on(tmp_path):
    import random
    from localgm import coherence, savefile
    from localgm.simgm import SimGM
    from localgm.store import Game
    random.seed(3)
    bg = (__import__("test_flow").ROOT / "ashfall_hunter" / "background.md").read_text(encoding="utf-8")
    g = Game.new(tmp_path, "g", bg)
    flow.intake(g.world, SimGM()); g.save()
    gm = SimGM()
    for text in ["I look around.", "I ask Nadia what is going on.", "I wait for an hour.", "I go to the Canal Street embankment relay huts.", "I wait."]:
        flow.run_turn(g.world, gm, text); g.save()
    assert g.world.get("world_state.location") == "canal_embankment"
    snap2 = Game.open(tmp_path, "g"); snap2.rewind(2)
    assert snap2.world.round == 2 and snap2.world.get("world_state.location") == "hale_workshop"          # back before the trip
    flow.run_turn(snap2.world, gm, "I ask Nadia again.")                                                 # and the game goes on from there
    assert snap2.world.round == 3 and coherence.check(snap2.world) == []
    text = savefile.export_save(g.world, bg, "g")
    w3, notes = savefile.import_save(text, bg)
    assert w3.round == g.world.round and w3.get("world_state.location") == "canal_embankment"
    flow.run_turn(w3, gm, "I wait for an hour.")
    assert w3.round == g.world.round + 1 and coherence.check(w3) == []


def test_a_made_world_and_an_imported_save_play_too(tmp_path):
    import random
    from localgm import coherence, generate, savefile
    from localgm.simgm import SimGM
    from localgm.state import World, background_tree
    random.seed(5)
    text, _ = generate.generate(SimGM(), "a grim road fantasy")
    w = World(background_tree(text))
    flow.intake(w, SimGM())
    assert coherence.check(w) == [], coherence.check(w)
    for line in ["I look around.", "I wait for a day.", "I go to the Ash Pit.", "I wait."]:
        flow.run_turn(w, SimGM(), line)
        assert coherence.check(w) == [], (line, coherence.check(w))
    root = __import__("test_flow").ROOT
    save = (pathlib.Path(__file__).resolve().parent / "data" / "ashfall_R10.md").read_text(encoding="utf-8")
    w2, _ = savefile.import_save(save, (root / "ashfall_hunter" / "background.md").read_text(encoding="utf-8"))
    for line in ["I look around.", "I wait for an hour.", "I sleep until morning."]:
        flow.run_turn(w2, SimGM(), line)
    assert w2.round == 13 and coherence.check(w2) == [], coherence.check(w2)


def test_a_script_with_headings_and_words_written_for_the_player_is_sent_back():
    w = world()
    good = "Hobb looks up from the register and shakes his head. \"The big rooms are taken,\" he says, \"but the attic is free if you don't mind the stairs.\""
    for bad in ("**THE GM'S DECISION**\n\nHobb looks up from the register.\n\n**YOU**\n\n\"Is there a room?\" you ask.",
                "Hobb looks up. \"Is there a room for tonight?\" you ask, and he nods."):
        t, bot = run(w, "I ask Hobb for a room", sort={"kind": "loop", "steps": ["react"]},
                     react={"asks": [], "report": "Hobb offers the attic.", "minutes": 5, "ops": []}, tell=[bad, good])
        assert bot.seen.count("tell") == 2 and t.prose == good, bad[:30]
    # words the player really said may be quoted back
    t, _ = run(w, 'I say "good evening" to Hobb', sort={"kind": "loop", "steps": ["react"]},
               react={"asks": [], "report": "Hobb nods.", "minutes": 1, "ops": []}, tell='You say, "good evening," and Hobb nods without looking up from his book.')
    assert "good evening" in t.prose
