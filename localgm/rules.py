"""V5 rules that need world state, not just arithmetic: capability, rest, growth, quests, entitlement, endings,
hidden truth. Each function takes a World, changes it only through its own methods, and returns facts."""
from __future__ import annotations
import json, re

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
    """kind rest: a quarter of max HP (min 1) per full hour. sleep: full HP. MP by the setting's recovery. Injuries stay."""
    if kind == "none":
        return []
    cond = w.player.setdefault("condition", {})
    if w.player_state() == "dead" or cond.get("down") == "down":
        return []                                  # someone who is down needs treatment, not rest
    top = hp_max(w)
    hp = int(cond.get("hp", top))
    if kind == "sleep":
        new = top
    else:
        new = M.heal(hp, top, max(1, top // 4) * (minutes // 60))
    out = []
    if new != hp:
        cond["hp"] = new
        if new > 0:
            for k in ("down", "down_since", "down_checked", "stable"):
                cond.pop(k, None)
        out.append(f"The player recovered to HP {new}/{top}.")
    return out + mp_recover(w, kind, minutes)


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
    for rid, r in companions(w).items():
        for name, sk in ((r.get("capability") or {}).get("skills") or {}).items():
            g = M.grow(sk["class"], sk["tier"], int(sk.get("growth_evidence", 0)), int(sk.get("ceiling_evidence", 0)), False)
            sk["tier"], sk["class"] = g["tier"], g["class"]
            sk["growth_evidence"], sk["ceiling_evidence"] = g["growth_evidence"], g["ceiling_evidence"]
            if g["tiers_raised"]:
                out.append(f"{r.get('name', rid)}'s {name} rose to {g['tiers_raised'][-1]}.")
    return out + injury_boundary(w)


def add_history(w: World, text: str) -> None:
    """One line in the world's material history; a chat-made save keys its entries, a background lists them."""
    mh = w.tree["world_state"].setdefault("material_history", [])
    if isinstance(mh, dict):
        mh[f"r{w.round + 1}_{len(mh) + 1}"] = text
    else:
        mh.append(text)


# ---------- XP ----------

def companions(w: World) -> dict[str, dict]:
    """Tracked companions: people whose level and skills the engine follows alongside the player's."""
    return {rid: r for rid, r in (w.tree.get("npcs") or {}).items()
            if isinstance(r, dict) and (r.get("capability") or {}).get("tracked")}


def xp_pass(w: World, challenges: list[int], scope: str) -> list[str]:
    """One pass when a scope resolves: the player and every tracked companion each get the full award against
    their own level, together (never split by party size)."""
    if not module(w, "numeric_level_xp") or not w.player.get("progression") or not challenges:
        return []
    out = []
    st = w.player["progression"]["state"]
    amount = sum(M.xp_award(c, st["level"], scope) for c in challenges)
    st["level"], st["xp"], ups = M.add_xp(st["level"], st["xp"], amount)
    out.append(f"The player earned {amount} XP." + (f" Level up to {ups[-1]}." if ups else ""))
    for rid, r in companions(w).items():
        cap = r["capability"]
        amt = sum(M.xp_award(c, int(cap["overall_level"]), scope) for c in challenges)
        cap["overall_level"], cap["xp"], ups = M.add_xp(int(cap["overall_level"]), int(cap.get("xp", 0)), amt)
        out.append(f"{r.get('name', rid)} earned {amt} XP." + (f" Level up to {ups[-1]}." if ups else ""))
    return out


def award_xp(w: World, challenge: int, scope: str) -> str | None:
    msgs = xp_pass(w, [challenge], scope)
    return " ".join(msgs) if msgs else None


def set_companion(w: World, rid: str, level: int | None, joins: bool) -> str:
    r = (w.tree.get("npcs") or {}).get(rid)
    if not isinstance(r, dict):
        raise M.RuleError(f"no such person {rid!r}")
    cap = r.setdefault("capability", {})
    if joins:
        if level is None or not 1 <= int(level) <= M.LEVEL_CAP:
            raise M.RuleError("a companion needs its level (1..35)")
        cap.update(tracked=True, overall_level=int(level), xp=int(cap.get("xp", 0)))
        return f"{r.get('name', rid)} now travels with the player and gains experience alongside them."
    cap["tracked"] = False
    return f"{r.get('name', rid)} no longer travels with the player."


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


# ---------- MP and casting (10.5) ----------

def powers(w: World) -> dict[str, tuple[str, int]]:
    """MP-drawing powers the setting names -> (skill that holds it, the power's tier number)."""
    draws = ((w.tree.get("setting_anchors") or {}).get("mp_powers") or {}).get("draws_mp") or []
    out = {}
    for pid in draws:
        for sk, s in (w.player.get("skills") or {}).items():
            for ab in s.get("abilities") or []:
                if str(ab).strip().startswith(pid):
                    m = re.search(r"\bT([1-4])\b", str(ab))
                    out[pid] = (sk, int(m.group(1)) if m else 1)
    return out


def mp_max(w: World) -> int | None:
    held = powers(w)
    if not held:
        return None
    bonus = max(M.TIER_BONUS[w.player["skills"][sk]["tier"]] for sk, _ in held.values())
    return 2 * _vitality(w) + 4 * bonus


def _vitality(w: World) -> int:
    rec = w.player
    if level(w) is not None:
        return level(w)
    return VITALITY.get(rec.get("vitality", "ordinary"), 1)


def mp_now(w: World) -> int:
    top = mp_max(w) or 0
    return int(w.player.setdefault("condition", {}).get("mp", top))


def can_cast(w: World, pid: str) -> int:
    """Cost of casting power `pid` now, or a RuleError saying why not."""
    held = powers(w)
    if pid not in held:
        raise M.RuleError(f"{pid!r} is not an MP-drawing power of this world: {sorted(held) or 'none'}")
    sk, tier = held[pid]
    if tier > M.TIER_BONUS[w.player["skills"][sk]["tier"]]:
        raise M.RuleError(f"{pid} is above the caster's skill tier")
    cost = M.cast_cost(f"T{tier}")
    if mp_now(w) < cost:
        raise M.RuleError(f"{pid} costs {cost} MP; the player has {mp_now(w)}")
    return cost


def cast(w: World, pid: str) -> int:
    cost = can_cast(w, pid)
    w.player["condition"]["mp"] = mp_now(w) - cost          # paid whether or not it works
    return cost


def mp_recover(w: World, kind: str, minutes: int) -> list[str]:
    top = mp_max(w)
    if top is None or kind == "none":
        return []
    mode = (((w.tree.get("setting_anchors") or {}).get("mp_powers") or {}).get("recovery")) or "rest_only"
    now = mp_now(w)
    if kind == "sleep" or (mode == "fast" and minutes >= 10):
        new = top
    elif mode == "slow":
        new = min(top, now + max(1, top // 4) * (minutes // 60))
    else:
        new = now
    if new != now:
        w.player["condition"]["mp"] = new
        return [f"The player's MP is {new}/{top}."]
    return []


# ---------- healing and treatment (10.5) ----------

HEAL_DICE = {"minor": (2, 6), "standard": (4, 6), "T1": (1, 8), "T2": (2, 6), "T3": (3, 6), "T4": (4, 6)}


def heal_target(w: World, who: str, source: str) -> tuple[str, str]:
    """Apply a healing item or power. Returns (printed line, fact). Healing stabilises first."""
    _, cond, top = w._vitals(who)
    hp = int(cond.get("hp", top))
    if source == "stabilise":
        if cond.get("down") != "down":
            raise M.RuleError(f"{who} is not down")
        cond["stable"] = True
        return f"{who} stabilised", f"{who} was stabilised (will not die of the wound)."
    if source in ("strong", "night"):
        gain, how = top, "full"
    elif source == "hour":
        gain, how = max(1, top // 4), "a quarter"
    elif source in HEAL_DICE:
        n, sides = HEAL_DICE[source]
        d = M.roll(n, sides)
        gain, how = sum(d), f"{n}d{sides} ({'+'.join(map(str, d))})"
    else:
        raise M.RuleError(f"healing source must be stabilise, strong or one of {sorted(HEAL_DICE)}")
    new = M.heal(hp, top, gain)
    cond["hp"] = new
    if new > 0:
        for k in ("down", "down_since", "down_checked", "stable"):
            cond.pop(k, None)
    return f"Healing {who}: {how} | HP {hp} → {new}", f"{who} was healed to HP {new}."


def treat_injury(w: World, action: str, injury: str, deep: bool) -> str:
    inj = next((i for i in w.player.get("condition", {}).get("injuries", []) if injury.lower() in i["injury"].lower()), None)
    if not inj:
        raise M.RuleError(f"the player has no lasting injury like {injury!r}")
    if action == "start":
        inj["treatment_since"] = w.minutes_now()
        inj["days_needed"] = 7 if deep else 3
        return f"Treatment of {inj['injury']} began ({inj['days_needed']} days needed)."
    inj.pop("treatment_since", None)
    return f"Treatment of {inj['injury']} stopped."


def injury_boundary(w: World) -> list[str]:
    """At a growth boundary: injuries whose treatment has run its full time are removed."""
    out, keep = [], []
    for i in w.player.get("condition", {}).get("injuries", []):
        done = i.get("treatment_since") is not None and w.minutes_now() - i["treatment_since"] >= i.get("days_needed", 3) * 1440
        if done:
            out.append(f"The player's {i['injury']} has healed.")
        else:
            keep.append(i)
    if out:
        w.player["condition"]["injuries"] = keep
    return out


# ---------- supplies (15) ----------

DIE = ["d12", "d10", "d8", "d6", "d4"]


def draw(w: World, rid: str, amount: int = 1) -> str:
    res = (w.player.get("resources") or {}).get(rid)
    if not res:
        raise M.RuleError(f"no resource {rid!r}; the player has {sorted(w.player.get('resources') or {})}")
    if res.get("tracking") == "exact":
        if int(res.get("count", 0)) < amount:
            raise M.RuleError(f"only {res.get('count', 0)} {res['name']} left")
        res["count"] = int(res["count"]) - amount
        return f"{res['name']}: {res['count']} left."
    die = res.get("usage_die")
    if die == "empty":
        raise M.RuleError(f"{res['name']} is exhausted")
    r = M.roll(1, int(die[1:]))[0]
    if r <= 2:
        res["usage_die"] = DIE[DIE.index(die) + 1] if die != "d4" else "empty"
    return f"{res['name']}: usage {die} rolled {r}" + (f" → {res['usage_die']}" if res["usage_die"] != die else " (no change)")


def resupply(w: World, rid: str, die: str | None, count: int | None) -> str:
    res = (w.player.get("resources") or {}).get(rid)
    if not res:
        raise M.RuleError(f"no resource {rid!r}")
    if res.get("tracking") == "exact":
        res["count"] = int(res.get("count", 0)) + int(count or 0)
    else:
        if die not in DIE or (res.get("usage_die") in DIE and DIE.index(die) >= DIE.index(res["usage_die"])):
            raise M.RuleError(f"a resupply must raise the die above {res.get('usage_die')}: one of {DIE}")
        res["usage_die"] = die
    return f"{res['name']} resupplied."


# ---------- persistent records: nothing established may be lost (I1, I7) ----------

# subtrees that only grow: values may change, but keys and list items are never dropped
GROWS = [re.compile(x) for x in (
    r"^(npcs|factions)\.[^.]+\.(relationships|drives|knowledge|discovered_information)$",
    r"^world_state\.material_history$",
    r"^locked_case_truths\.[^.]+\.(prior_events|evidence|discovered_information)$",
    r"^active_world_pressures\.[^.]+\.discovered_information$",
    r"^player\.knowledge$")]


def _lost(before, after, path: str, out: list[str]) -> None:
    if isinstance(before, dict):
        if not isinstance(after, dict):
            out.append(f"{path} stopped being an object")
            return
        for k, v in before.items():
            if k not in after:
                out.append(f"{path}.{k} was dropped")
            else:
                _lost(v, after[k], f"{path}.{k}", out)
    elif isinstance(before, list):
        if not isinstance(after, list) or len(after) < len(before):
            out.append(f"{path} lost entries")


def _paths(tree: dict, pat) -> list[tuple[str, object]]:
    out = []
    for top in ("npcs", "factions", "locked_case_truths", "active_world_pressures"):
        for rid, rec in (tree.get(top) or {}).items():
            if isinstance(rec, dict):
                for k, v in rec.items():
                    if pat.match(f"{top}.{rid}.{k}"):
                        out.append((f"{top}.{rid}.{k}", v))
    for fixed in ("world_state.material_history", "player.knowledge"):
        node = tree
        for part in fixed.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node is not None and pat.match(fixed):
            out.append((fixed, node))
    return out


def _ids(tree: dict) -> set[str]:
    ids = set(tree.get("npcs") or {}) | set(tree.get("factions") or {})
    name = ((tree.get("player") or {}).get("identity") or {}).get("name")
    if name:
        ids.add(re.sub(r"\W+", "_", str(name).lower()).strip("_"))
    return ids


def player_faults(after: dict) -> list[str]:
    """The player's own record: strict where the program does arithmetic on it."""
    p, out = after.get("player") or {}, []
    cond = p.get("condition") or {}
    if not isinstance(cond, dict):
        return ["player.condition must stay an object"]
    inj = cond.get("injuries", [])
    if not isinstance(inj, list) or any(not (isinstance(i, dict) and isinstance(i.get("injury"), str) and i.get("home") in HOMES
                                             and str(i.get("effect", "")).strip()) for i in inj):
        out.append(f"player.condition.injuries: each is {{injury, home (one of {HOMES}), effect}}")
    eq = p.get("equipment", [])
    if not isinstance(eq, list) or any(not (isinstance(e, dict) and str(e.get("name", "")).strip()) for e in eq):
        out.append("player.equipment: each item is an object with a name")
    skills = p.get("skills", {})
    if not isinstance(skills, dict):
        return out + ["player.skills must stay an object"]
    for sid, s in skills.items():
        if not (isinstance(s, dict) and s.get("class") in M.CEILING and s.get("tier") in M.TIERS
                and M.TIERS.index(s["tier"]) <= M.TIERS.index(M.CEILING[s["class"]])
                and isinstance(s.get("growth_evidence", 0), int) and isinstance(s.get("ceiling_evidence", 0), int)):
            out.append(f"player.skills.{sid}: needs a valid class, a tier within its ceiling and whole-number evidence")
    for key, kind in (("routines", dict), ("fighting_style", list), ("knowledge", dict)):
        if key in p and not isinstance(p[key], kind):
            out.append(f"player.{key} must stay a {kind.__name__}")
    if "money" in p and not isinstance(p["money"], (int, dict)):
        out.append("player.money must stay a number or a record")
    return out


def record_faults(before: dict, after: dict) -> list[str]:
    """Whole-world checks run on every commit: established facts survive, shapes hold, references resolve."""
    out = []
    for pat in GROWS:
        old = dict(_paths(before, pat))
        new = dict(_paths(after, pat))
        for path, v in old.items():
            if path not in new:
                out.append(f"{path} was removed")
            else:
                _lost(v, new[path], path, out)
    for kind in ("npcs", "factions", "locations", "quests", "active_world_pressures", "development_threads", "rights_obligations"):
        for rid, rec in (before.get(kind) or {}).items():
            if isinstance(rec, dict):
                gone = [k for k in rec if k not in ((after.get(kind) or {}).get(rid) or {})]
                if gone:
                    out.append(f"{kind}.{rid} lost fields {gone}")
    for kind in ("npcs", "factions"):
        for rid, rec in (after.get(kind) or {}).items():
            if not isinstance(rec, dict):
                continue
            if "name" in rec and not str(rec["name"]).strip():
                out.append(f"{kind}.{rid}.name is empty")
            plan = rec.get("plan")
            if plan is not None:
                ok = isinstance(plan, dict) and isinstance(plan.get("dues"), list) and isinstance(plan.get("triggers"), list) \
                    and all(isinstance(d, dict) and {"day", "clock", "what"} <= set(d) for d in plan.get("dues", []))
                if not ok:
                    out.append(f"{kind}.{rid}.plan must keep its shape {{move, dues:[{{day, clock, what}}], triggers:[...]}}; use the plan op")
    out += player_faults(after)
    old_ids, new_ids = _ids(before), _ids(after)
    for kind in ("npcs", "factions"):
        for rid, rec in (after.get(kind) or {}).items():
            was = set(((before.get(kind) or {}).get(rid) or {}).get("relationships") or {})
            for other in (rec.get("relationships") or {}) if isinstance(rec, dict) else {}:
                if other not in was and other not in new_ids:
                    out.append(f"{kind}.{rid}.relationships.{other}: nobody here has that id")
    for qid, q in (after.get("quests") or {}).items():
        was = set(((before.get("quests") or {}).get(qid) or {}).get("participants") or [])
        for pid in (q.get("participants") or []) if isinstance(q, dict) else []:
            if pid not in was and pid not in new_ids:
                out.append(f"quests.{qid}.participants: {pid} is not a known person")
    return out


# ---------- authority: world fact > dice > AI ----------

def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def get_path(tree: dict, path: str):
    node = tree
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def check_cites(w: World, cites: list[str]) -> None:
    """A verdict rests on records that exist. Nothing is settled by something the records do not hold."""
    missing = [c for c in cites if get_path(w.tree, c) is None]
    if missing:
        raise M.RuleError(f"these cited records do not exist: {missing}. Cite paths that are in the records, or do not rely on them.")


def frozen(w: World, key: str) -> dict | None:
    for e in reversed(w.tree.get("resolved") or []):
        if e["key"] == key:
            return e
    return None


def record_result(w: World, key: str, kind: str, label: str, positive: bool, text: str, governs: list[str]) -> dict:
    """A resolved roll or answer becomes a fact of the campaign; later rounds respect it."""
    e = {"round": w.round + 1, "key": key, "kind": kind, "outcome": label, "positive": positive, "text": text, "governs": list(governs)}
    w.tree.setdefault("resolved", []).append(e)
    return e


def ledger_text(w: World, n: int = 12) -> str:
    rows = (w.tree.get("resolved") or [])[-n:]
    return "\n".join(f"R{e['round']} {e['kind']} '{e['key']}': {e['outcome']} — {e['text']}" for e in rows) or "none yet"


def past_governed(w: World) -> dict[str, dict]:
    out = {}
    for e in w.tree.get("resolved") or []:
        for g in e.get("governs") or []:
            out[g] = e
    return out


KNOWLEDGE_PATH = re.compile(r"^((npcs|factions)\.[^.]+\.knowledge|player\.knowledge)\b")


def op_faults(w: World, ops: list[dict], resolved: dict[str, dict], governs: dict[str, str]) -> list[str]:
    """Do the proposed changes agree with the results of this turn, and have they a cause and a channel?"""
    out, old = [], past_governed(w)
    for i, op in enumerate(ops, 1):
        path, req = op.get("path", ""), op.get("requires")
        if op.get("op") == "plan":
            path += ".plan"                  # a plan changes the actor's plan, not the rest of the actor
        tag = f"op {i} ({path})"
        hit = [k for g, k in governs.items() if path == g or path.startswith(g + ".") or g.startswith(path + ".")]
        if hit and not req:
            out.append(f"{tag}: this path is decided by the result of {hit[0]!r}; say which answer it depends on (requires)")
        if req:
            key = norm(req.get("on", ""))
            r = resolved.get(key)
            if r is None:
                out.append(f"{tag}: requires {req.get('on')!r}, but nothing with that name was resolved this turn: {sorted(resolved) or 'nothing'}")
            elif (req.get("answer") in ("YES", "SUCCESS")) != r["positive"]:
                out.append(f"{tag}: depends on {req.get('answer')} but the result was {r['label']}; that change cannot be recorded")
            elif req.get("band") and f", {req['band']}" not in r["label"]:
                out.append(f"{tag}: depends on a {req['band']} result but the result was {r['label']}")
        prior = next((e for g, e in old.items() if path == g or path.startswith(g + ".")), None)
        if prior and not req and not str(op.get("because", "")).strip():
            out.append(f"{tag}: this was decided by {prior['key']!r} in round {prior['round']} ({prior['outcome']}); changing it needs a new cause (because) or a new result (requires)")
        if op.get("op") != "remove" and KNOWLEDGE_PATH.match(path) and not str(op.get("channel", "")).strip():
            out.append(f"{tag}: someone learns something; say how (channel: witnessed, report, told by ...)")
    return out


HOSTILE_WORDS = ("hostile", "enemy", "fighting", "aggress", "threat", "hunting the player")


def temper_new(before: dict, after: dict, rng=None) -> tuple[list[str], list[str]]:
    """A new actor who is not from the BACKGROUND is rolled once for temper (V5 §13.1): 2d10 >= 17 (>= 15 on the
    opposing side) makes them a difficult character fitting their role. The roll is the program's; the result is kept."""
    lines, facts = [], []
    for nid, rec in (after.get("npcs") or {}).items():
        if nid in (before.get("npcs") or {}) or not isinstance(rec, dict) or "temper" in rec:
            continue
        text = json.dumps([rec.get("state"), rec.get("relationships")], ensure_ascii=False).lower()
        opposing = any(w in text for w in HOSTILE_WORDS)
        need = 15 if opposing else 17
        d = M.roll(2, 10, rng)
        hard = sum(d) >= need
        rec["temper"] = "difficult" if hard else "ordinary"
        lines.append(f"temper of {rec.get('name', nid)} 2d10: {d[0]}+{d[1]} = {sum(d)} (needs {need}) → {rec['temper']}")
        if hard:
            facts.append(f"{rec.get('name', nid)} is a difficult character, fitting their role (rude, greedy, petty, a bully…); keep it. "
                         "Never aim it at the player's secrets; their attitude still comes from the meeting.")
    return lines, facts
