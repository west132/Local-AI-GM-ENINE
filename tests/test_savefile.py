import copy, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from localgm import flow, rules, savefile
from localgm.state import World, background_tree
from localgm.store import Game
from test_flow import Scripted, world, ROOT, OK, LOOP_REACT
from test_rules import react

DATA = pathlib.Path(__file__).resolve().parent / "data"
SAVE = (DATA / "ashfall_R10.md").read_text(encoding="utf-8")
BG = (ROOT / "ashfall_hunter" / "background.md").read_text(encoding="utf-8")


def test_a_real_chat_made_save_loads_and_plays():
    w, notes = savefile.import_save(SAVE, BG)
    assert w.round == 10 and w.tree["world_state"]["location"] == "hale_workshop"
    assert (w.time["date"], w.time["clock_minutes"]) == ("2026-10-07", 430)
    assert w.player["progression"]["state"] == {"level": 4, "xp": 41} and w.cash()[0] == 2650
    assert w.get("quests.find_eli_voss.status") == "completed" and w.get("quests.laundromat_job.status") == "active"
    assert w.get("npcs.eli_voss.state.position") == "hale_workshop sofa, staying the night"
    assert w.get("npcs.embankment_cinderling.name").startswith("cinderling") and w.get("npcs.eli_voss.state.hp") == 12
    assert "eli_condition" not in w.tree["active_world_pressures"]                         # retired in the save
    assert isinstance(w.get("world_state.material_history"), dict)                         # keyed entries kept
    # a turn can be committed on it: the validators accept an imported world
    t = flow.run_turn(w, Scripted([{"kind": "loop", "steps": ["react"]}, {"asks": []}, react(minutes=5, ops=[{"op": "set", "path": "npcs.eli_voss.state.status", "value": "eats breakfast", "because": "morning"}]), react(), "ok", OK]), "I make breakfast")
    assert w.get("npcs.eli_voss.state.status") == "eats breakfast" and w.round == 11


def test_plans_written_as_text_in_the_save_are_read_by_the_program():
    w, _ = savefile.import_save(SAVE, BG)
    assert not any(w.get(p + ".plan.text") for p in w.needs_intake() if not p.startswith("active"))      # no AI needed to read a date
    assert w.get("npcs.dale.plan.dues")[0]["day"] == 3 and w.get("npcs.ada_hale.plan.dues")[0]["day"] == 5     # R10 stamps and all
    assert w.get("active_world_pressures.glass_spread.clock.due_at")


def test_export_then_import_gives_the_same_world_back(tmp_path):
    w = world("ashfall_hunter")
    flow.run_turn(w, Scripted([{"kind": "loop", "steps": ["react"]}, {"asks": []},
                               react(minutes=30, money=-5, ops=[{"op": "set", "path": "npcs.nadia_voss.state.status", "value": "waits"},
                                                                 {"op": "set", "path": "world_state.location", "value": "canal_embankment"}]),
                               react(), "ok", OK]), "x")
    text = savefile.export_save(w, BG, "t")
    assert "# PART A" in text and "# PART B" in text and "npcs.nadia_voss.state.status :: R1: waits" in text
    w2, notes = savefile.import_save(text, BG)
    assert w2.round == w.round and w2.tree == w.tree, [k for k in w.tree if w.tree[k] != w2.tree.get(k)]


def test_the_exported_file_is_a_save_the_old_reader_format_understands():
    text = savefile.export_save(world(), (ROOT / "harbour_guesthouse" / "background.md").read_text(), "t")
    records, retired = savefile.capsule_lines(text)
    assert isinstance(records, list) and all(len(r) == 3 for r in records)


def test_crlf_save_imports_the_same():
    a, _ = savefile.import_save(SAVE, BG)
    b, _ = savefile.import_save(SAVE.replace("\n", "\r\n"), BG.replace("\n", "\r\n"))
    assert a.tree == b.tree and b.round == 10
