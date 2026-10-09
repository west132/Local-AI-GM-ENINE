import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from localgm.store import Game

BG = pathlib.Path("/home/user/Claude-Engine-V5/examples/harbour_guesthouse/background.md").read_text()


def test_save_open_rewind(tmp_path):
    g = Game.new(tmp_path, "g", BG)
    for i in range(3):
        g.world.round += 1
        g.world.pay(-1) if i == 0 else None
        g.world.advance(30)
        g.log({"input": f"turn {i + 1}"})
        g.save()
    m3 = g.world.time["clock_minutes"]
    g2 = Game.open(tmp_path, "g")
    assert g2.world.round == 3 and g2.world.time["clock_minutes"] == m3
    g2.rewind(1)
    assert g2.world.round == 1
    assert not (tmp_path / "g" / "snapshots" / "00002.json").exists()
    assert len((tmp_path / "g" / "journal.jsonl").read_text().splitlines()) == 1
    assert Game.open(tmp_path, "g").world.round == 1
