import copy, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from localgm import clock, flow, generate as G
from localgm.state import World, background_tree, parse_note, dates_in
from test_generate import Forms, PREMISE, k_in
from test_flow import ROOT

TABLE = {"era": "Year", "months": [{"name": "Thawmonth", "days": 30}, {"name": "Floodmonth", "days": 31}, {"name": "Harvestwane", "days": 29}],
         "leap": {"every": 4, "month": "Thawmonth", "extra": 1}, "weekdays": ["Moonday", "Fireday", "Starday"], "start_weekday": "Fireday"}


def test_a_table_gives_exact_dates_weeks_and_leap_days():
    c = clock.Custom(TABLE)
    a = c.ordinal_of(318, "Floodmonth", 6)
    assert c.fmt(a) == "Year 318, Floodmonth 6" and c.fmt(a + 26) == "Year 318, Harvestwane 1"      # Floodmonth has 31 days
    assert c.fmt(a + 55) == "Year 319, Thawmonth 1"                                                       # 25 days left in Floodmonth + 29; 318 is no leap year
    assert c.ordinal_of(320, "Thawmonth", 31) and clock.date_ordinal(c, "Year 319, Thawmonth 31") is None   # only leap years have a 31st
    assert c.weekday(a + 3) == c.weekday(a)                                                              # three-day week


def test_a_bad_table_is_refused_with_the_reason():
    for bad, word in (({"months": []}, "months"), ({"months": [{"name": "A", "days": 0}]}, "months"),
                      ({"months": [{"name": "A", "days": 5}, {"name": "a", "days": 5}]}, "different"),
                      ({"months": [{"name": "A", "days": 5}], "leap": {"every": 1, "month": "A", "extra": 1}}, "leap"),
                      ({"months": [{"name": "A", "days": 5}], "weekdays": ["X"], "start_weekday": "Y"}, "start_weekday")):
        with pytest.raises(ValueError, match=word):
            clock.Custom(bad)


def _world(extra_tree=None):
    text = (ROOT / "harbour_guesthouse" / "background.md").read_text(encoding="utf-8")
    t = background_tree(text)
    t["calendar"] = TABLE
    t["world_state"]["time"]["date"] = "Year 318, Floodmonth 30"
    for n in ("tobias_wren", "edda_pryce"):
        t["npcs"][n]["state"]["due"] = "when the day ends"
    t["npcs"]["hobb_marren"]["state"]["due"] = "Year 318, Floodmonth 31 19:00 starts serving supper; Year 318, Harvestwane 2 dawn the ferry strike ends; when the desk phone rings"
    return World(t)


def test_the_program_reads_the_worlds_own_dates_in_plan_notes():
    w = _world()
    p = w.tree["npcs"]["hobb_marren"]["plan"]
    assert not w.needs_intake() and [(d["day"], d["clock"]) for d in p["dues"]] == [(1, 1140), (3, 360)] and p["triggers"] == ["when the desk phone rings"]


def test_time_moves_the_date_through_the_table():
    w = _world()
    w.advance(24 * 60 * 3)
    assert w.time["date"] == "Year 318, Harvestwane 2" and w.time["day_index"] == 3


def test_dates_in_a_note_are_found_for_the_check():
    w = _world()
    assert dates_in("on Year 318, Harvestwane 1 10:00 and later", w.time, w.cal) == [(2, 600)]


def test_the_calendar_is_the_programs_not_the_ais():
    from localgm.state import WriteRefused
    w = _world()
    with pytest.raises(WriteRefused):
        w.apply({"op": "set", "path": "calendar.months", "value": []})


def test_the_generator_can_make_a_world_with_its_own_calendar():
    p = copy.deepcopy(PREMISE)
    p["calendar"] = TABLE
    p["start"]["date"] = "Year 318, Floodmonth 6"
    class Cal(Forms):
        def ask(self, system, user, schema=None, max_tokens=None):
            if k_in(schema, "title"):
                return copy.deepcopy(p)
            out = super().ask(system, user, schema, max_tokens)
            if k_in(schema, "npcs"):          # the scripted cast still writes ISO dates: the calendar check must send them back
                return out
            return out
    f = Cal()
    with pytest.raises(ValueError, match="real date in the calendar"):
        G.generate(f, "x")
    from localgm.demo_forms import CAST, STORY
    fixed_cast = copy.deepcopy(CAST)
    fixed_cast["npcs"][0]["due"] = "Year 318, Floodmonth 7 09:00 opens the taproom"
    fixed_cast["npcs"][2]["due"] = "Year 318, Floodmonth 8 06:00 sets traps"
    story = copy.deepcopy(STORY)
    story["pressures"][0]["first_check"] = "Year 318, Floodmonth 9 06:00"
    class Good(Cal):
        def ask(self, system, user, schema=None, max_tokens=None):
            if k_in(schema, "npcs"): return copy.deepcopy(fixed_cast)
            if k_in(schema, "quests"): return copy.deepcopy(story)
            return super().ask(system, user, schema, max_tokens)
    text, _ = G.generate(Good(), "x")
    w = World(background_tree(text))
    assert w.tree["calendar"]["months"][0]["name"] == "Thawmonth" and w.time["date"] == "Year 318, Floodmonth 6"
    assert w.tree["npcs"]["mara_voss"]["plan"]["dues"][0]["day"] == 1 and not w.needs_intake()
