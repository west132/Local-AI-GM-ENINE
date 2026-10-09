"""The one live state: the BACKGROUND tree plus what play changed. The program is the only writer.

The AI proposes ops; `World.apply` accepts an op only if its path is not program-owned.
Numbers the AI must not write (HP, money, XP, evidence, the clock) change only through the typed
methods below, which call mechanics.
"""
from __future__ import annotations
import copy, re
import yaml

from . import clock, mechanics as M

# AI may not write under these prefixes (program-owned)
OWNED = (r"round", r"world_state\.time", r"player\.condition\.(hp|mp)", r"player\.money",
         r"player\.resources", r"player\.progression", r"player\.skills\.[^.]+\.(class|tier|growth_evidence|ceiling_evidence)",
         r"trackers", r"journal")
_OWNED = [re.compile(p + r"(\.|$)") for p in OWNED]


class WriteRefused(ValueError):
    pass


def background_tree(text: str) -> dict:
    """A filled BACKGROUND has many ```yaml blocks; merge them into one tree."""
    tree: dict = {}
    for b in re.findall(r"```ya?ml\n(.*?)```", text, re.S):
        d = yaml.safe_load(b)
        if isinstance(d, dict):
            tree.update(d)
    if not tree.get("background_id"):
        raise ValueError("BACKGROUND needs a background_id")
    return tree


def _walk(tree, path: str, create=False):
    keys = path.split(".")
    cur = tree
    for k in keys[:-1]:
        if not isinstance(cur, dict) or k not in cur:
            if not create:
                raise KeyError(path)
            cur[k] = {}
        cur = cur[k]
    return cur, keys[-1]


class World:
    def __init__(self, tree: dict, round_no: int = 0):
        self.tree = tree
        self.round = round_no

    # ----- reading -----
    def get(self, path: str, default=None):
        try:
            d, k = _walk(self.tree, path)
            return d.get(k, default)
        except (KeyError, AttributeError):
            return default

    @property
    def time(self) -> dict:
        return self.tree["world_state"]["time"]

    @property
    def player(self) -> dict:
        return self.tree["player"]

    # ----- AI-proposed ops -----
    def apply(self, op: dict) -> None:
        path, kind = op["path"], op["op"]
        if any(p.match(path) for p in _OWNED):
            raise WriteRefused(f"{path} is kept by the program; state what happened and it is applied")
        if kind == "plan":
            self._plan(op)
            return
        d, k = _walk(self.tree, path, create=(kind == "set"))
        if kind == "set":
            d[k] = copy.deepcopy(op["value"])
        elif kind == "append":
            d.setdefault(k, [])
            if not isinstance(d[k], list):
                raise WriteRefused(f"{path} is not a list")
            d[k].append(copy.deepcopy(op["value"]))
        elif kind == "remove":
            if k not in d:
                raise WriteRefused(f"{path} does not exist")
            del d[k]
        else:
            raise WriteRefused(f"unknown op {kind!r}")

    def _plan(self, op: dict) -> None:
        """Store an actor's next move with an absolute due, so the program can fire it."""
        t = self.time
        due = t["clock_minutes"] + int(op.get("due_in_minutes", 0))
        d, k = _walk(self.tree, op["path"] + ".plan", create=True)
        d[k] = {"move": op["value"], "due_day": t["day_index"] + due // 1440, "due_clock": due % 1440}

    # ----- program-owned changes -----
    def advance(self, minutes: int) -> int:
        new, days = clock.advance(self.time, minutes)
        self.tree["world_state"]["time"] = new
        return days

    def due(self) -> list[tuple[str, dict]]:
        """Every actor plan whose due has passed, earliest first."""
        now = (self.time["day_index"], self.time["clock_minutes"])
        out = []
        for kind in ("npcs", "factions"):
            for rid, rec in (self.tree.get(kind) or {}).items():
                p = rec.get("plan") if isinstance(rec, dict) else None
                if isinstance(p, dict) and (p["due_day"], p["due_clock"]) <= now:
                    out.append(((p["due_day"], p["due_clock"]), f"{kind}.{rid}", p))
        return [(path, p) for _, path, p in sorted(out, key=lambda x: x[0])]

    def pay(self, amount: int) -> None:
        """Spend (negative) or receive (positive) money; never below zero."""
        new = int(self.player.get("money", 0)) + amount
        if new < 0:
            raise M.RuleError("not enough money")
        self.player["money"] = new

    def hurt(self, damage: list[int], soak: int = 0, who: str = "player") -> dict:
        rec = self.player if who == "player" else self.tree["npcs"][who]
        cond = rec.setdefault("condition", {}) if who == "player" else rec.setdefault("state", {})
        v = {"ordinary": 1, "seasoned": 3, "veteran": 5, "exceptional": 8, "heroic": 11,
             "legendary": 20}.get(rec.get("vitality", "ordinary"), 1)
        if "progression" in rec:
            v = rec["progression"]["state"]["level"]
        hp_max = M.max_hp(v, rec.get("size", "normal"))
        r = M.harm(int(cond.get("hp", hp_max)), hp_max, damage, soak)
        cond["hp"] = r["hp"]
        return r

    def credit_skill(self, skill: str, success: bool, diff: int, challenge=None) -> int:
        """Add evidence from one roll; at most once per skill per growth period."""
        s = self.player["skills"][skill]
        credited = self.player.setdefault("growth_period", {}).setdefault("credited", [])
        if skill in credited:
            return 0
        gain = M.evidence(success, diff, challenge)
        if gain:
            key = "ceiling_evidence" if s["tier"] == M.CEILING[s["class"]] else "growth_evidence"
            s[key] = s.get(key, 0) + gain
            credited.append(skill)
        return gain
