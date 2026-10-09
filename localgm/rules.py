"""V5 rules that need world state, not just arithmetic: capability, rest, growth, quests, entitlement, endings,
hidden truth. Each function takes a World, changes it only through its own methods, and returns facts."""
from __future__ import annotations
import re

from . import mechanics as M
from .state import World

TIER_BOOST = {"T1": 0, "T2": 1, "T3": 2, "T4": 4}            # equipment (B)
ENTITLEMENT_COST = {"trivial": 0, "ordinary": 1, "T1": 2, "T2": 4, "T3": 8, "T4": 16}
HOMES = ("capability", "feasibility", "environment", "time", "sensory", "position", "simultaneous")
QUEST_STATUS = ("available", "active", "completed", "failed", "abandoned", "blocked")
TERMINAL = ("completed", "failed", "abandoned")
VITALITY = {"ordinary": 1, "seasoned": 3, "veteran": 5, "exceptional": 8, "heroic": 11, "legendary": 20}


def module(w: World, name: str) -> bool:
    return bool((w.tree.get("enabled_modules") or {}).get(name))


def level(w: World) -> int | None:
    p = w.player.get("progression")
    return int(p["state"]["level"]) if p and module(w, "numeric_level_xp") else None


# ---------- capability (A, B) ----------

def roll_inputs(w: World, r: dict, foe_level: int | None = None) -> tuple[int, int, int, list[str]]:
    """(capability modifier, tool modifier, difficulty, notes) for a roll form.
    Numeric worlds: the program computes capability from level + skill tier + equipment and the AI's Challenge;
    the base is then always 10. Otherwise the AI's band stands."""
    notes = []
    tool = M.tool_mod(**{k: v for k, v in (r.get("tool") or {}).items() if k in ("fit", "condition")})
    challenge = r.get("challenge") or foe_level
    lv = level(w)
    if lv is not None and challenge:
        skill = (w.player.get("skills") or {}).get(r.get("skill") or "")
        actor = lv + (M.TIER_BONUS[skill["tier"]] if skill else 0)
        eq = r.get("equipment")
        if eq and module(w, "equipment_power_tiers"):
            item = next((e for e in (w.player.get("equipment") or []) if e.get("item_id") == eq or e.get("name") == eq), None)
            if item and item.get("tier") in TIER_BOOST:
                actor += TIER_BOOST[item["tier"]]
                tool = 0                                   # never also ToolMod (I8)
                notes.append(f"{item.get('name', eq)} {item['tier']} +{TIER_BOOST[item['tier']]}")
        cap = M.capmod(actor, int(challenge))
        return cap, tool, M.difficulty(10, r.get("conditions")), notes
    return r["capability"], tool, M.difficulty(r["base"], r.get("conditions")), notes


# ---------- rest and growth (10.5, 11) ----------

def hp_max(w: World, who: str = "player") -> int:
    return w._vitals(who)[2]


def rest(w: World, kind: str, minutes: int) -> list[str]:
    """kind rest: a quarter of max HP (min 1) per full hour. sleep: full HP, full MP. Injuries stay."""
    if kind == "none":
        return []
    cond = w.player.setdefault("condition", {})
    if w.player_state() == "dead":
        return []
    top = hp_max(w)
    hp = int(cond.get("hp", top))
    if kind == "sleep":
        new = top
    else:
        new = M.heal(hp, top, max(1, top // 4) * (minutes // 60))
    out = []
    if new != hp:
        cond["hp"] = new
        cond.pop("down", None)
        out.append(f"The player recovered to HP {new}/{top}.")
    return out


def growth_boundary(w: World, sources: dict[str, str]) -> list[str]:
    """Settle stored evidence into tiers and (with a valid source) class, then open a new growth period."""
    out = []
    for name, s in (w.player.get("skills") or {}).items():
        src = (sources or {}).get(name)
        g = M.grow(s["class"], s["tier"], int(s.get("growth_evidence", 0)), int(s.get("ceiling_evidence", 0)), bool(src))
        s["tier"], s["class"] = g["tier"], g["class"]
        s["growth_evidence"], s["ceiling_evidence"] = g["growth_evidence"], g["ceiling_evidence"]
        if g["tiers_raised"]:
            out.append(f"Skill {name} rose to {g['tiers_raised'][-1]} (a quiet, noticed change).")
        if g["class_raised"]:
            s["class_source"] = src
            out.append(f"Skill {name} was raised to {g['class_raised']} through {src}.")
    gp = w.player.setdefault("growth_period", {})
    gp["opened"], gp["credited"] = w.time["day_index"], []
    return out


# ---------- XP ----------

def award_xp(w: World, challenge: int, scope: str) -> str | None:
    lv = w.player.get("progression")
    if not lv or not module(w, "numeric_level_xp"):
        return None
    st = lv["state"]
    amount = M.xp_award(challenge, st["level"], scope)
    st["level"], st["xp"], ups = M.add_xp(st["level"], st["xp"], amount)
    return f"The player earned {amount} XP." + (f" Level up to {ups[-1]}." if ups else "")


# ---------- quests (14) ----------

def quest_faults(before: dict, after: dict, numeric: bool) -> list[str]:
    out, main_open = [], 0
    qs, old = after.get("quests") or {}, before.get("quests") or {}
    children = {c for q in qs.values() if isinstance(q, dict) for c in (q.get("child_quests") or [])}
    for qid, q in qs.items():
        if not isinstance(q, dict):
            continue
        if q.get("role") not in ("MAIN", "SIDE") or q.get("type") not in ("SHORT", "LONG", "CHAIN") or not str(q.get("objective", "")).strip():
            out.append(f"quest {qid}: needs role MAIN|SIDE, type SHORT|LONG|CHAIN and an objective")
        if q.get("status") not in QUEST_STATUS:
            out.append(f"quest {qid}: status must be one of {QUEST_STATUS}")
        if q.get("role") == "MAIN" and q.get("status") not in TERMINAL and qid not in children:
            main_open += 1
        if numeric and q.get("type") == "SHORT" and not isinstance(q.get("quest_level"), int):
            out.append(f"quest {qid}: a SHORT quest needs quest_level before it is available")
        if q.get("type") == "CHAIN" and q.get("quest_level") is not None:
            out.append(f"quest {qid}: a CHAIN root has no level; each child has its own")
        for c in q.get("child_quests") or []:
            if c not in qs:
                out.append(f"quest {qid}: child {c} does not exist")
        o = old.get(qid)
        if isinstance(o, dict):
            if o.get("status") in TERMINAL and q.get("status") != o.get("status"):
                out.append(f"quest {qid}: it is {o['status']}; a closed quest stays closed")
            if o.get("quest_level") is not None and q.get("quest_level") != o.get("quest_level"):
                out.append(f"quest {qid}: quest_level is immutable; a changed challenge is a new quest or segment")
            if o.get("type") != q.get("type"):
                out.append(f"quest {qid}: type cannot change")
    if main_open > 1:
        out.append("only one MAIN quest may be unfinished at a time")
    return out


def quest_closed(before: dict, after: dict) -> list[tuple[str, dict, str]]:
    """Quests and segments that became completed in this change: (id, record, kind)."""
    out = []
    for qid, q in (after.get("quests") or {}).items():
        o = (before.get("quests") or {}).get(qid) or {}
        if q.get("status") == "completed" and o.get("status") != "completed":
            out.append((qid, q, "quest"))
        for sid, s in (q.get("segments") or {}).items():
            os_ = (o.get("segments") or {}).get(sid) or {}
            if isinstance(s, dict) and s.get("status") == "completed" and os_.get("status") != "completed":
                out.append((f"{qid}.{sid}", s, "segment"))
    return out


def quest_xp(w: World, before: dict) -> list[str]:
    """XP for what just completed, once each (xp_awarded is stored on the record)."""
    out = []
    for qid, rec, kind in quest_closed(before, w.tree):
        lvl = rec.get("quest_level") if kind == "quest" else rec.get("segment_level")
        if lvl is None and kind == "segment":
            lvl = (w.tree["quests"][qid.split(".")[0]]).get("quest_level")
        if not lvl or rec.get("xp_awarded") or rec.get("type") == "CHAIN":
            continue
        msg = award_xp(w, int(lvl), rec.get("xp_scope", "meaningful"))
        if msg:
            rec["xp_awarded"] = int(re.search(r"earned (\d+)", msg).group(1))
            out.append(f"Quest {qid} completed. {msg}")
    return out


# ---------- item entitlement (D) ----------

def spend_entitlement(w: World, e: dict) -> str:
    if not module(w, "flexible_item_entitlement"):
        raise M.RuleError("flexible item entitlement is not enabled in this world")
    cost = ENTITLEMENT_COST.get(e["tier"])
    if cost is None:
        raise M.RuleError(f"tier must be one of {sorted(ENTITLEMENT_COST)}")
    if not str(e.get("reason", "")).strip():
        raise M.RuleError("an in-world reason is required before narration")
    pts = int(w.player.get("item_points", 0))
    if pts < cost:
        raise M.RuleError(f"costs {cost} item points; the player has {pts}")
    w.player["item_points"] = pts - cost
    item = {"item_id": re.sub(r"\W+", "_", e["item"].lower()).strip("_"), "name": e["item"], "source": e["reason"]}
    if e["tier"] in TIER_BOOST and module(w, "equipment_power_tiers"):
        item["tier"] = e["tier"]
    w.player.setdefault("equipment", []).append(item)
    return f"ENTITLEMENT: {e['item']} is now the player's ({cost} point(s) spent, {w.player['item_points']} left). In-world reason: {e['reason']}"


def gain_entitlement(w: World, g: dict) -> str:
    if not module(w, "flexible_item_entitlement"):
        raise M.RuleError("flexible item entitlement is not enabled in this world")
    if not 1 <= int(g["amount"]) <= 4 or len(str(g.get("source", "")).strip()) < 5:
        raise M.RuleError("a gain is 1 to 4 points from a named open-ended source")
    w.player["item_points"] = int(w.player.get("item_points", 0)) + int(g["amount"])
    return f"The player gained {g['amount']} item point(s) from {g['source']}."


# ---------- endings (C) ----------

def ending_list(w: World) -> dict[str, str]:
    ec = w.tree.get("ending_conditions") or {}
    out = {f"core.{i}": str(c) for i, c in enumerate(ec.get("core_conditions") or [])}
    out |= {f"hidden.{i}": str(c) for i, c in enumerate(ec.get("hidden_conditions") or [])}
    return out


def ending_update(w: World, met: list[str], closed: list[str]) -> list[str]:
    known = ending_list(w)
    st = w.tree.setdefault("ending_state", {"closed": [], "met": None})
    out = []
    for i in met + closed:
        if i not in known:
            raise M.RuleError(f"no ending condition {i!r}; they are {sorted(known)}")
        if i in st["closed"]:
            raise M.RuleError(f"{i} is permanently closed")
    for i in closed:
        st["closed"].append(i)
    if met and not st["met"]:
        st["met"] = met[0]
        out.append(f"ENDING REACHED: {known[met[0]]}. The scenario ends here.")
    left = [i for i in known if i not in st["closed"]]
    if not left and not st["met"]:
        st["met"] = "none-left"
        out.append("Every ending is permanently out of reach; the scenario ends in this state.")
    return out


# ---------- hidden truth (I5, I9) ----------

HIDDEN_PATH = re.compile(r"^(locked_case_truths|open_suspicions|ending_conditions|ending_state|active_world_pressures)\b|"
                         r"\.(drives|knowledge|plan|relationships|discovered_information)\b")


def _flatten(v) -> str:
    if isinstance(v, dict):
        return " ; ".join(_flatten(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return " ; ".join(_flatten(x) for x in v)
    return "" if v is None else str(v)


def _hidden_text(w: World) -> str:
    t, parts = w.tree, []
    for kind in ("locked_case_truths", "open_suspicions"):
        for c in (t.get(kind) or {}).values():
            parts.append(_flatten({k: v for k, v in c.items() if k != "discovered_information"}) if isinstance(c, dict) else str(c))
    for kind in ("npcs", "factions"):
        for r in (t.get(kind) or {}).values():
            if isinstance(r, dict):
                parts.append(_flatten({k: r.get(k) for k in ("drives", "knowledge", "plan")}))
    for p in (t.get("active_world_pressures") or {}).values():
        if isinstance(p, dict):
            parts.append(_flatten({k: p.get(k) for k in ("origin", "trajectory", "clock")}))
    parts.append(_flatten((t.get("ending_conditions") or {}).get("hidden_conditions")))
    parts.append(_flatten(((t.get("world_state") or {}).get("unowned_facts") or {}).get("hidden")))
    return " ".join(parts)


def _visible_text(w: World, extra: str) -> str:
    t = w.tree
    parts = [extra, _flatten(w.player), _flatten(t.get("locations")), _flatten(t.get("world_state")), _flatten(t.get("quests")),
             _flatten(t.get("rights_obligations"))]
    for kind in ("npcs", "factions"):
        for r in (t.get(kind) or {}).values():
            if isinstance(r, dict):
                parts.append(_flatten({k: v for k, v in r.items() if k not in ("drives", "knowledge", "plan", "relationships")}))
                parts.append(_flatten(r.get("discovered_information")))
    for kind in ("locked_case_truths", "active_world_pressures"):
        for r in (t.get(kind) or {}).values():
            if isinstance(r, dict):
                parts.append(_flatten(r.get("discovered_information")))
    return " ".join(parts)


_CALENDAR = {d for d in ("Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April June July "
                         "August September October November December Seven Eight Three Four Five Nine Twelve").split()}


_VOCAB = None


def _vocab() -> set[str]:
    """Ordinary words, from the rule files: a capitalised word found here is not a name."""
    global _VOCAB
    if _VOCAB is None:
        import pathlib
        text = " ".join(p.read_text(encoding="utf-8") for p in (pathlib.Path(__file__).resolve().parent.parent / "engine" / "rules").glob("*.md"))
        _VOCAB = set(re.findall(r"\b[a-z]+\b", text))
    return _VOCAB


def secret_terms(w: World, extra_visible: str = "") -> set[str]:
    """Proper names that occur only in hidden records and nowhere the player has seen or learned."""
    hidden = _hidden_text(w).replace("’", "'")
    seen = _visible_text(w, extra_visible).lower()
    lower = set(re.findall(r"\b[a-z]+\b", hidden)) | set(re.findall(r"\b[a-z]+\b", seen)) | _vocab()
    # a name is capitalised mid-clause or possessive; a word that merely opens a sentence is not taken for one
    cands = re.findall(r"(?<=[a-z,] )([A-Z][a-z]{3,})\b", hidden) + re.findall(r"\b([A-Z][a-z]{3,})'s\b", hidden)
    names = {m for m in cands if m.lower() not in lower} - _CALENDAR
    return {n for n in names if not re.search(r"\b" + re.escape(n.lower()) + r"\b", seen)}


def leaks(prose: str, terms: set[str]) -> list[str]:
    return sorted(t for t in terms if re.search(r"\b" + re.escape(t) + r"\b", prose))


def redact(prose: str, terms: set[str]) -> str:
    """Last resort: drop every sentence that names a secret."""
    sents = re.findall(r"[^.!?。！？\n]+[.!?。！？]*[\"”')]*\s*|\n+", prose)
    return "".join(s for s in sents if not leaks(s, terms)).strip()
