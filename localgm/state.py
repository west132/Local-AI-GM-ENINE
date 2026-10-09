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
         r"trackers", r"journal", r"pending", r"player\.item_points", r"player\.growth_period",
         r"ending_conditions", r"ending_state", r"resolved",
         r"npcs\.[^.]+\.capability\.(tracked|overall_level|xp)", r"(npcs|factions)\.[^.]+\.(work_source|temper)")
_OWNED = [re.compile(p + r"(\.|$)") for p in OWNED]


class WriteRefused(ValueError):
    pass


def _same_shape(old, new) -> bool:
    if isinstance(old, bool) or isinstance(new, bool):
        return isinstance(old, bool) and isinstance(new, bool)
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return True
    return type(old) is type(new)


def plain(v):
    """YAML turns an unquoted 2026-10-07 into a date object; a save must hold only text, numbers, lists and objects."""
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat()
    return v


def background_tree(text: str) -> dict:
    """A filled BACKGROUND has many ```yaml blocks; merge them into one tree."""
    tree: dict = {}
    for b in re.findall(r"```ya?ml\n(.*?)```", text, re.S):
        d = yaml.safe_load(b)
        if isinstance(d, dict):
            tree.update(d)
    if not tree.get("background_id"):
        raise ValueError("BACKGROUND needs a background_id")
    return plain(tree)


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


WORK_WHAT = ("WORK SOURCE: did fitting work come in for the player? Ask it: YES it contacts the player · "
             "NO, BUT thin, or it went to a rival · NO, AND a dry spell")


def _every_days(v) -> int:
    """'weekly' | 'daily' | 'monthly' | '3 days' | 3 | {pace: ...} -> whole days (default weekly)."""
    if isinstance(v, dict):
        v = v.get("pace") or v.get("every_days") or "weekly"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return max(1, int(v))
    m = re.search(r"(\d+)\s*(day|week|month)", str(v), re.I)
    if m:
        return max(1, int(m.group(1)) * {"day": 1, "week": 7, "month": 30}[m.group(2).lower()])
    return {"daily": 1, "weekly": 7, "monthly": 30, "fortnightly": 14}.get(str(v).strip().lower(), 7)


_LEAD = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}:\d{2}|dawn|morning|noon|midday|afternoon|dusk|evening|night|midnight)\b[\s,:\-]*(.*)$",
                   re.I | re.S)
_ANY_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _day_of(t: dict, y: int, mo: int, d: int) -> int | None:
    m0 = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(t.get("date") or ""))
    if not m0:
        return None
    try:
        return t["day_index"] + (_dt.date(y, mo, d) - _dt.date(*map(int, m0.groups()))).days
    except ValueError:
        return None


_DATE_TOKEN = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[ T]+(\d{1,2}:\d{2}|dawn|morning|noon|midday|afternoon|dusk|evening|night|midnight)\b)?", re.I)


def _tidy(text: str) -> str:
    text = re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\s+", " ", text)).strip(" ,;:-")
    return re.sub(r"^(?:,|;)\s*", "", text)


def parse_note(note: str, t: dict, move: str = ""):
    """A plan note is clauses split by ';'. The calendar is the program's one calendar, written 'YYYY-MM-DD [HH:MM | dawn | noon …]'.
    A clause with such a date is a due on the clock (no time given: morning); the words around the date are what happens.
    A clause with no date and no clock time is a trigger (a condition). Any other kind of calendar or clock time: return None
    and the one-time intake step reads the note, its dates then checked against this text (dates_in)."""
    dues, trig = [], []
    for clause in [c.strip() for c in str(note).split(";") if c.strip()]:
        found = list(_DATE_TOKEN.finditer(clause))
        if found:
            what = _tidy(_DATE_TOKEN.sub("", clause)) or move
            for m in found:
                day = _day_of(t, int(m.group(1)), int(m.group(2)), int(m.group(3)))
                try:
                    at = at_minutes(m.group(4) or "morning")
                except ValueError:
                    return None
                if day is None:
                    return None
                dues.append({"day": day, "clock": at, "what": what})
        elif re.search(r"\d{1,2}:\d{2}", clause):
            return None          # a clock time with no date in the program's calendar
        else:
            trig.append(clause)
    return dues, trig


def dates_in(note: str, t: dict) -> list[tuple[int, int | None]]:
    """Every 'YYYY-MM-DD [HH:MM]' written in a note as (day_index, clock minutes or None): what the AI's answer must contain."""
    out = []
    for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{1,2}:\d{2}))?", str(note)):
        day = _day_of(t, int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if day is not None:
            out.append((day, at_minutes(m.group(4)) if m.group(4) else None))
    return out


_EVERY = re.compile(r"\b(?:every|each)\s+(?:(\d+|a|one|two|three|second|third|other)\s+)?(?:(?:full|elapsed|in-world|in-game|whole)\s+)*(night|day|week|month|hour)s?\b", re.I)
_NUM = {"a": 1, "one": 1, "two": 2, "second": 2, "other": 2, "three": 3, "third": 3}


def clock_interval(pace: str) -> int | None:
    m = _EVERY.search(str(pace))
    if not m:
        return None
    n = m.group(1)
    n = 1 if n is None else (int(n) if n.isdigit() else _NUM[n.lower()])
    return n * {"hour": 60, "night": 1440, "day": 1440, "week": 10080, "month": 43200}[m.group(2).lower()]


def _normalize_clocks(tree: dict) -> None:
    """A pressure's first check written as 'YYYY-MM-DD HH:MM' with a pace 'every N units' is read here, not by the AI."""
    t = tree["world_state"]["time"]
    for pr in (tree.get("active_world_pressures") or {}).values():
        c = pr.get("clock") if isinstance(pr, dict) else None
        if not isinstance(c, dict) or c.get("due_at") or not c.get("due"):
            continue
        m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}:\d{2})\s*$", str(c["due"]))
        iv = clock_interval(c.get("pace", ""))
        day = _day_of(t, *map(int, m.groups()[:3])) if m else None
        if m and iv and day is not None:
            c["due_at"] = {"day": day, "clock": at_minutes(m.group(4))}
            c["interval_minutes"] = iv


def _normalize_plans(tree: dict) -> None:
    """BACKGROUND writes an actor's plan as state.plan + state.due (free text). Make one plan record:
    {move, dues:[{day, clock, what}], triggers:[text]}. A single plain ISO due is converted here; anything
    else is kept as `text` for the one-time intake step (flow.intake) to split."""
    t = tree["world_state"]["time"]
    for kind in ("npcs", "factions"):
        for rec in (tree.get(kind) or {}).values():
            st = rec.get("state") if isinstance(rec, dict) else None
            if isinstance(st, dict) and "work_source" in st:        # a role that routes work to the player (V5 §13.1 WORK SOURCE)
                every = _every_days(st.pop("work_source"))
                rec["work_source"] = {"every_days": every, "next": {"day": t["day_index"] + every, "clock": 540}}
            if not isinstance(st, dict) or "plan" not in st or isinstance(st["plan"], dict):
                continue
            plan = {"move": st.pop("plan"), "dues": [], "triggers": []}
            due = st.pop("due", None)
            parsed = parse_note(str(due), t, plan["move"]) if due else None
            if parsed:                                   # every clause is a plain clock time or a plain condition: the program reads it
                plan["dues"], plan["triggers"] = parsed
            elif due:                                    # a date buried in a sentence: the one-time intake step reads it, and its dates are checked
                plan["text"] = str(due)
            rec["plan"] = plan


class World:
    def __init__(self, tree: dict, round_no: int = 0):
        self.tree = tree
        self.round = round_no
        _normalize_plans(tree)
        _normalize_clocks(tree)
        self.ensure_work()
        p = tree.get("player") or {}
        if (tree.get("enabled_modules") or {}).get("flexible_item_entitlement") and "item_points" not in p:
            p["item_points"] = int((p.get("starting_item_points") or {}).get("points", 0))

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

    # ----- AI-proposed ops: all or nothing -----
    def clone(self) -> "World":
        return World(copy.deepcopy(self.tree), self.round)

    def commit(self, ops: list[dict]) -> list[str]:
        """Apply every op to a copy, check the result, and swap it in only if all of it is sound.
        Returns the faults; on any fault nothing at all has changed."""
        trial = self.clone()
        faults = []
        for i, op in enumerate(ops):
            try:
                trial._check(op)
                trial.apply(op)
            except (WriteRefused, KeyError, TypeError, ValueError, AttributeError) as e:
                faults.append(f"op {i + 1} ({op.get('op')} {op.get('path')}): {e}")
        faults += trial._broken_by(self)
        if faults:
            return faults
        self.tree = trial.tree
        self.ensure_work()
        return []

    RECORDS = ("npcs", "factions", "locations", "quests", "active_world_pressures", "development_threads",
               "rights_obligations")

    def _check(self, op: dict) -> None:
        """Structure checks on one op, against the state it is about to change."""
        kind, path = op.get("op"), op.get("path", "")
        if kind not in ("set", "append", "remove", "plan", "tracker"):
            raise WriteRefused(f"unknown op {kind!r}")
        if kind == "tracker":
            return
        if not path or path.startswith(".") or ".." in path:
            raise WriteRefused("bad path")
        keys = path.split(".")
        if keys[0] not in self.tree:
            raise WriteRefused(f"{keys[0]!r} is not part of this world's records")
        if keys[0] in self.RECORDS:
            if len(keys) == 2 and kind == "remove":
                raise WriteRefused("a record is never deleted; change its status")
            if len(keys) == 2 and kind == "set" and (keys[1] in self.tree[keys[0]] or not isinstance(op.get("value"), dict)):
                raise WriteRefused("change a record's fields one at a time; a new record must be an object")
            if len(keys) == 1:
                raise WriteRefused("name the record")
        if kind == "set":
            old = self.get(path)
            new = op.get("value")
            if old is not None and not _same_shape(old, new):
                raise WriteRefused(f"{path} holds {type(old).__name__}; the new value is {type(new).__name__}")
        if kind == "plan" and not isinstance(self.get(path), dict):
            raise WriteRefused(f"{path} is not a record that can plan")

    def _broken_by(self, before: "World") -> list[str]:
        """Invariants the whole world must still satisfy after the ops."""
        out = []
        for kind in self.RECORDS:
            was, now = before.tree.get(kind) or {}, self.tree.get(kind) or {}
            if not isinstance(now, dict) or any(rid not in now for rid in was):
                out.append(f"{kind}: a record would disappear")
            elif any(not isinstance(r, dict) for r in now.values()):
                out.append(f"{kind}: every record must stay an object")
        if before.player.get("identity") != self.player.get("identity"):
            out.append("player.identity cannot change")
        from . import rules
        out += rules.record_faults(before.tree, self.tree)
        out += rules.quest_faults(before.tree, self.tree, bool((self.tree.get("enabled_modules") or {}).get("numeric_level_xp")))
        return out

    def apply(self, op: dict) -> None:
        path, kind = op["path"], op["op"]
        if any(p.match(path) for p in _OWNED):
            raise WriteRefused(f"{path} is kept by the program; state what happened and it is applied")
        if kind == "plan":
            self._plan(op)
            return
        if kind == "tracker":
            self._tracker(op)
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

    def _tracker(self, op: dict) -> None:
        """Trackers own a countable fact {name, current, target}. The AI says what happened; the program counts."""
        v = op.get("value") or {}
        trackers = self.tree.setdefault("trackers", {})
        tid = op["path"]
        if "create" in v:
            c = v["create"]
            if tid in trackers:
                raise WriteRefused(f"tracker {tid} exists")
            trackers[tid] = {"name": str(c["name"]), "current": int(c.get("current", 0)), "target": int(c["target"])}
        elif "add" in v:
            if tid not in trackers:
                raise WriteRefused(f"no tracker {tid}")
            t = trackers[tid]
            t["current"] = M.clamp(t["current"] + int(v["add"]), 0, t["target"])
        else:
            raise WriteRefused("tracker value is {create:{name,target}} or {add:n}")

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
        for pid, pr in (self.tree.get("active_world_pressures") or {}).items():
            c = pr.get("clock") if isinstance(pr, dict) else None
            at = c.get("due_at") if isinstance(c, dict) else None
            if at and (at["day"], at["clock"]) <= now and c.get("filled", 0) < c.get("segments", 0):
                out.append(((at["day"], at["clock"]), f"active_world_pressures.{pid}",
                            {**at, "is_clock": True, "what": f"clock '{c.get('name', pid)}' ({c.get('filled', 0)}/{c.get('segments')}) is due its check; "
                             f"pace: {c.get('pace', '')}"}))
        return [(path, d) for _, path, d in sorted(out, key=lambda x: x[0])]

    def clear_due(self, path: str, entry: dict) -> None:
        """A due the AI has been shown is spent. A clock is not removed: it is moved on by tick_clock."""
        plan = self.get(path + ".plan")
        if plan and entry in plan["dues"]:
            plan["dues"].remove(entry)
        ws = self.get(path + ".work_source")
        if ws and entry.get("work"):                 # the program sets the next check; a replan cannot lose it
            day = entry["day"] + ws["every_days"]
            if day <= self.time["day_index"]:
                day = self.time["day_index"] + ws["every_days"]
            ws["next"] = {"day": day, "clock": entry["clock"]}
            self.ensure_work(path)

    def ensure_work(self, only: str | None = None) -> None:
        """Every work source always has its next check on the books, whatever the AI did to the plan."""
        for kind in ("npcs", "factions"):
            for rid, rec in (self.tree.get(kind) or {}).items():
                path = f"{kind}.{rid}"
                ws = rec.get("work_source") if isinstance(rec, dict) else None
                if not ws or (only and only != path) or "dead" in str((rec.get("state") or {}).get("status", "")).lower():
                    continue
                plan = rec.setdefault("plan", {"move": "routes work to the player", "dues": [], "triggers": []})
                if not any(d.get("work") for d in plan["dues"]):
                    plan["dues"].append({**ws["next"], "what": WORK_WHAT, "work": True})

    def tick_clock(self, path: str, operated: bool, extra: bool = False) -> dict:
        """The AI judged whether the process operated; the program fills the segments and sets the next check."""
        c = self.get(path + ".clock")
        if not isinstance(c, dict) or not c.get("due_at"):
            raise WriteRefused(f"{path} has no clock to check")
        gain = (1 + (1 if extra else 0)) if operated else 0
        c["filled"] = min(int(c["segments"]), int(c.get("filled", 0)) + gain)
        step = c.get("interval_minutes")
        if step and c["filled"] < c["segments"]:
            total = c["due_at"]["clock"] + int(step)
            c["due_at"] = {"day": c["due_at"]["day"] + total // 1440, "clock": total % 1440}
        else:
            c.pop("due_at", None)            # full, or no regular pace: the AI sets the next check when it matters
        return {"filled": c["filled"], "segments": c["segments"], "full": c["filled"] >= c["segments"],
                "on_fill": c.get("on_fill", "")}

    def set_clock(self, path: str, due: dict, interval_minutes: int | None) -> None:
        c = self.get(path + ".clock")
        clock_ = at_minutes(due["at"])
        day = self.time["day_index"] + int(due["day_offset"])
        if (day, clock_) < (self.time["day_index"], self.time["clock_minutes"]):
            raise ValueError(f"{path}: the first check is in the past")
        c["due_at"] = {"day": day, "clock": clock_}
        if interval_minutes:
            c["interval_minutes"] = int(interval_minutes)

    def needs_intake(self) -> list[str]:
        out = [f"{k}.{rid}" for k in ("npcs", "factions") for rid, r in (self.tree.get(k) or {}).items()
               if isinstance(r, dict) and r.get("plan")
               and (r["plan"].get("text") or not (r["plan"].get("dues") or r["plan"].get("triggers")))]
        out += [f"active_world_pressures.{pid}" for pid, r in (self.tree.get("active_world_pressures") or {}).items()
                if isinstance(r, dict) and isinstance(r.get("clock"), dict) and r["clock"].get("due")
                and not r["clock"].get("due_at") and r["clock"].get("filled", 0) < r["clock"].get("segments", 0)]
        return out

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

    def cash(self) -> tuple[int, str]:
        """(amount, currency). BACKGROUND money is a number, or {cash_and_accessible_funds, currency, note}."""
        m = self.player.get("money", 0)
        if isinstance(m, dict):
            return int(m.get("cash_and_accessible_funds", 0)), str(m.get("currency", ""))
        return int(m), ""

    def pay(self, amount: int) -> None:
        """Spend (negative) or receive (positive) money; never below zero."""
        new = self.cash()[0] + amount
        if new < 0:
            raise M.RuleError("not enough money")
        if isinstance(self.player.get("money"), dict):
            self.player["money"]["cash_and_accessible_funds"] = new
        else:
            self.player["money"] = new

    def _vitals(self, who: str):
        """(record, condition dict, max HP) for the player or an npc id."""
        if who == "player":
            rec, cond = self.player, self.player.setdefault("condition", {})
        else:
            rec = self.tree["npcs"][who]
            cond = rec.setdefault("state", {})
        v = rec.get("v")
        if v is None and (rec.get("capability") or {}).get("overall_level"):
            v = rec["capability"]["overall_level"]
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
            cond.pop("down", None); cond.pop("down_since", None); cond.pop("stable", None)
        else:
            cond["down"] = r["state"]
            cond.setdefault("down_since", self.minutes_now())
        return {**r, "before": before}

    def minutes_now(self) -> int:
        return self.time["day_index"] * 1440 + self.time["clock_minutes"]

    def down_checks(self, rng=None) -> list[dict]:
        """Down and untreated for an hour: 2d10, 11+ wakes at 1 HP, else dies (once). Treatment first stabilises."""
        out = []
        who_all = ["player"] + [k for k, r in (self.tree.get("npcs") or {}).items() if isinstance(r, dict)]
        for who in who_all:
            _, cond, _top = self._vitals(who)
            if cond.get("down") != "down" or cond.get("stable") or cond.get("down_checked"):
                continue
            if self.minutes_now() - int(cond.get("down_since", self.minutes_now())) < 60:
                continue
            dice = M.roll(2, 10, rng)
            woke = sum(dice) >= 11
            cond["down_checked"] = True
            if woke:
                cond["hp"] = 1
                for k in ("down", "down_since", "down_checked"):
                    cond.pop(k, None)
            else:
                cond["down"] = "dead"
            out.append({"who": who, "dice": dice, "woke": woke})
        return out

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

    def is_here(self, position) -> bool:
        """A position is an id or free text ("hiding in relay hut 3 on the disused Canal Street embankment"):
        it is here if it names this place's id, or shares at least two meaningful words with its name."""
        here = self.tree["world_state"]["location"]
        pos = str(position or "").lower()
        if not pos:
            return False
        if pos == here.lower() or here.lower() in pos:
            return True
        name = str(self.location().get("name", "")).lower()
        words = {w for w in re.findall(r"[a-z]{4,}", name)}
        return len(words & set(re.findall(r"[a-z]{4,}", pos))) >= 2

    def actors_here(self) -> dict[str, dict]:
        return {rid: r for rid, r in (self.tree.get("npcs") or {}).items()
                if isinstance(r, dict) and self.is_here((r.get("state") or {}).get("position"))}
