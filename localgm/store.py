"""Saves. One folder per game; a snapshot after every round, so any round can be returned to."""
from __future__ import annotations
import json, os, pathlib, shutil

from .state import World, background_tree


def _write(path: pathlib.Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Game:
    def __init__(self, folder: pathlib.Path, world: World):
        self.dir, self.world = folder, world

    @classmethod
    def new(cls, root, name: str, background_text: str) -> "Game":
        d = pathlib.Path(root) / name
        if d.exists():
            raise FileExistsError(f"{d} exists")
        (d / "snapshots").mkdir(parents=True)
        (d / "background.md").write_text(background_text, encoding="utf-8")
        g = cls(d, World(background_tree(background_text)))
        g.save()
        return g

    @classmethod
    def from_world(cls, root, name: str, background_text: str, world: World) -> "Game":
        d = pathlib.Path(root) / name
        if d.exists():
            raise FileExistsError(f"{d} exists")
        (d / "snapshots").mkdir(parents=True)
        (d / "background.md").write_text(background_text, encoding="utf-8")
        g = cls(d, world)
        g.save()
        return g

    @classmethod
    def open(cls, root, name: str) -> "Game":
        d = pathlib.Path(root) / name
        s = json.loads((d / "state.json").read_text(encoding="utf-8"))
        return cls(d, World(s["tree"], s["round"]))

    def save(self) -> None:
        text = json.dumps({"round": self.world.round, "tree": self.world.tree}, ensure_ascii=False, indent=1)
        _write(self.dir / "snapshots" / f"{self.world.round:05d}.json", text)
        _write(self.dir / "state.json", text)

    def log(self, entry: dict) -> None:
        with open(self.dir / "journal.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"round": self.world.round, **entry}, ensure_ascii=False) + "\n")

    def rewind(self, round_no: int) -> None:
        """Return to the state after `round_no`; later snapshots and journal lines are dropped."""
        snap = self.dir / "snapshots" / f"{round_no:05d}.json"
        if not snap.exists():
            raise FileNotFoundError(f"no save for round {round_no}")
        for f in (self.dir / "snapshots").glob("*.json"):
            if int(f.stem) > round_no:
                f.unlink()
        j = self.dir / "journal.jsonl"
        if j.exists():
            keep = [l for l in j.read_text(encoding="utf-8").splitlines() if json.loads(l)["round"] <= round_no]
            _write(j, "".join(l + "\n" for l in keep))
        s = json.loads(snap.read_text(encoding="utf-8"))
        self.world = World(s["tree"], s["round"])
        _write(self.dir / "state.json", snap.read_text(encoding="utf-8"))
