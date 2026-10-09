"""The one live state: the BACKGROUND tree plus what play changed. The program is the only writer.

The AI proposes ops; `World.apply` accepts an op only if its path is not program-owned.
Numbers the AI must not write (HP, money, XP, evidence, the clock) change only through the typed
methods below, which call mechanics.
"""
from __future__ import annotations
import copy, datetime as _dt, re
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


_ISO_DUE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2}) (\d{1,2}):(\d{2})\s+([^;]*)$")

AT_WORDS = {"dawn": 360, "morning": 540, "noon": 720, "midday": 720, "afternoon": 900, "dusk": 1110,
            "evening": 1140, "night": 1260, "midnight": 1439}


def at_minutes(at: str) -> int:
    """'HH:MM' or a part-of-day word -> minutes since midnight."""
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", at)
    if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
        return int(m.group(1)) * 60 + int(m.group(2))
    if at.strip().lower() in AT_WORDS:
        return AT_WORDS[at.strip().lower()]
    raise ValueError(f"time {at!r}: use HH:MM or one of {sorted(AT_WORDS)}")


def _normalize_plans(tree: dict) -> None:
    """BACKGROUND writes an actor's plan as state.plan + state.due (free text). Make one plan record:
    {move, dues:[{day, clock, what}], triggers:[text]}. A single plain ISO due is converted here; anything
    else is kept as `text` for the one-time intake step (flow.intake) to split."""
    t = tree["world_state"]["time"]
    for kind in ("npcs", "factions"):
        for rec in (tree.get(kind) or {}).values():
            st = rec.get("state") if isinstance(rec, dict) else None
            if not isinstance(st, dict) or "plan" not in st or isinstance(st["plan"], dict):
                continue
            plan = {"move": st.pop("plan"), "dues": [], "triggers": []}
            due = st.pop("due", None)
            m = _ISO_DUE.match(str(due or ""))
            m0 = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(t.get("date") or ""))
            if m and m0 and "immediately" not in due:
                days = (_dt.date(*map(int, m.groups()[:3])) - _dt.date(*map(int, m0.groups()))).days
                plan["dues"].append({"day": t["day_index"] + days, "clock": int(m.group(4)) * 60 + int(m.group(5)),
                                     "what": m.group(6).strip()})
            elif due:
                plan["text"] = str(due)
            rec["plan"] = plan


class World:
    def __init__(self, tree: dict, round_no: int = 0):
        self.tree = tree
        self.round = round_no
        _normalize_plans(tree)

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
        d[k] = {"move": op["value"], "triggers": [],
                "dues": [{"day": t["day_index"] + due // 1440, "clock": due % 1440, "what": op["value"]}]}

    # ----- program-owned changes -----
    def advance(self, minutes: int) -> int:
        new, days = clock.advance(self.time, minutes)
        self.tree["world_state"]["time"] = new
        return days

    def due(self) -> list[tuple[str, dict]]:
        """Every actor due whose time has passed, earliest first: (actor path, {day, clock, what})."""
        now = (self.time["day_index"], self.time["clock_minutes"])
        out = []
        for kind in ("npcs", "factions"):
            for rid, rec in (self.tree.get(kind) or {}).items():
                for d in ((rec.get("plan") or {}).get("dues") or []) if isinstance(rec, dict) else []:
                    if (d["day"], d["clock"]) <= now:
                        out.append(((d["day"], d["clock"]), f"{kind}.{rid}", d))
        return [(path, d) for _, path, d in sorted(out, key=lambda x: x[0])]

    def clear_due(self, path: str, entry: dict) -> None:
        plan = self.get(path + ".plan")
        if plan and entry in plan["dues"]:
            plan["dues"].remove(entry)

    def needs_intake(self) -> list[str]:
        return [f"{k}.{rid}" for k in ("npcs", "factions") for rid, r in (self.tree.get(k) or {}).items()
                if isinstance(r, dict) and r.get("plan")
                and (r["plan"].get("text") or not (r["plan"].get("dues") or r["plan"].get("triggers")))]

    def set_dues(self, path: str, dues: list[dict], triggers: list[str]) -> None:
        plan = self.get(path + ".plan")
        for d in dues:
            clock_ = at_minutes(d["at"])
            day = self.time["day_index"] + int(d["day_offset"])
            if (day, clock_) < (self.time["day_index"], self.time["clock_minutes"]) or d["day_offset"] > 400:
                raise ValueError(f"{path}: due '{d['what']}' is in the past or absurdly far")
            plan["dues"].append({"day": day, "clock": clock_, "what": d["what"]})
        if not dues and not triggers:
            raise ValueError(f"{path}: give at least one due or trigger")
        plan["triggers"] += list(triggers)
        plan.pop("text", None)

    def pay(self, amount: int) -> None:
        """Spend (negative) or receive (positive) money; never below zero."""
        new = int(self.player.get("money", 0)) + amount
        if new < 0:
            raise M.RuleError("not enough money")
        self.player["money"] = new

    def _vitals(self, who: str):
        """(record, condition dict, max HP) for the player or an npc id."""
        if who == "player":
            rec, cond = self.player, self.player.setdefault("condition", {})
        else:
            rec = self.tree["npcs"][who]
            cond = rec.setdefault("state", {})
        v = rec.get("v")
        if v is None:
            v = {"ordinary": 1, "seasoned": 3, "veteran": 5, "exceptional": 8, "heroic": 11,
                 "legendary": 20}.get(rec.get("vitality", "ordinary"), 1)
            if "progression" in rec:
                v = rec["progression"]["state"]["level"]
        return rec, cond, M.max_hp(int(v), rec.get("size", "normal"))

    def hurt(self, damage: list[int], soak: int = 0, who: str = "player") -> dict:
        _, cond, hp_max = self._vitals(who)
        before = int(cond.get("hp", hp_max))
        r = M.harm(before, hp_max, damage, soak)
        cond["hp"] = r["hp"]
        if r["state"] == "standing":
            cond.pop("down", None)
        else:
            cond["down"] = r["state"]
        return {**r, "before": before}

    def state_of(self, who: str) -> str:
        _, cond, hp_max = self._vitals(who)
        hp = int(cond.get("hp", hp_max))
        return "standing" if hp > 0 else cond.get("down", "down")

    def player_state(self) -> str:
        return self.state_of("player")

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

    # ----- what is here, for the prompts -----
    def location(self) -> dict:
        return self.tree.get("locations", {}).get(self.tree["world_state"]["location"], {})

    def actors_here(self) -> dict[str, dict]:
        here = self.tree["world_state"]["location"]
        return {rid: r for rid, r in (self.tree.get("npcs") or {}).items()
                if isinstance(r, dict) and (r.get("state") or {}).get("position") == here}
