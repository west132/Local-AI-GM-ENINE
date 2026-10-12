"""Does the whole world agree with itself? Checks that no single rule can make: run after a turn (or over a saved game) and it lists what contradicts what.
Each finding is a short sentence a person can act on. An empty list means the parts agree."""
from __future__ import annotations
import re

from . import clock, rules
from .state import World

OVERDUE_SLACK = 0      # minutes a due may be late before it counts as missed


def _now(w: World) -> tuple[int, int]:
    return w.time["day_index"], w.time["clock_minutes"]


def check(w: World) -> list[str]:
    t, out = w.tree, []
    here = t["world_state"]["location"]
    locs = t.get("locations") or {}
    if here not in locs:
        out.append(f"the player is at {here!r}, which is not a place in the records")
    # people: where they are, what they plan
    for kind in ("npcs", "factions"):
        for rid, r in (t.get(kind) or {}).items():
            if not isinstance(r, dict):
                continue
            st = r.get("state") or {}
            dead = any(k in str(st.get("status", "")).lower() for k in ("dead", "killed", "slain")) or str(st.get("down")) == "dead"
            plan = r.get("plan")
            if kind == "npcs" and not dead and isinstance(plan, dict) and not (plan.get("dues") or plan.get("triggers")):
                out.append(f"{kind}.{rid} has a plan but no due and no trigger, so it can never happen")
            for d in (plan or {}).get("dues", []) if isinstance(plan, dict) else []:
                if dead:
                    out.append(f"{kind}.{rid} is dead but still has a due: {d.get('what', '')[:60]}")
                elif (d["day"], d["clock"]) < _now(w) and not d.get("work"):
                    out.append(f"{kind}.{rid}: a due '{d.get('what', '')[:50]}' is in the past and was never fired")
    # companions travel with the player
    for rid, r in (t.get("npcs") or {}).items():
        if isinstance(r, dict) and (r.get("capability") or {}).get("tracked"):
            if not w.is_here((r.get("state") or {}).get("position")):
                out.append(f"npcs.{rid} travels with the player but is at {(r.get('state') or {}).get('position')!r}, not here")
    # clocks
    for pid, pr in (t.get("active_world_pressures") or {}).items():
        c = pr.get("clock") if isinstance(pr, dict) else None
        if isinstance(c, dict) and c.get("due_at") and c.get("filled", 0) < c.get("segments", 0):
            at = c["due_at"]
            if (at["day"], at["clock"]) < _now(w):
                out.append(f"pressure {pid}: its check was due and never ran")
        if isinstance(c, dict) and c.get("due") and not c.get("due_at") and c.get("filled", 0) < c.get("segments", 0):
            out.append(f"pressure {pid} has a first check written but no scheduled time")
    # the player
    p = w.player
    hp = (p.get("condition") or {}).get("hp")
    if isinstance(hp, int) and not 0 <= hp <= rules.hp_max(w):
        out.append(f"the player's HP {hp} is outside 0..{rules.hp_max(w)}")
    amount = w.cash()[0]
    if isinstance(amount, (int, float)) and amount < 0:
        out.append("the player's cash is below zero")
    for rid, res in (p.get("resources") or {}).items():
        if isinstance(res, dict) and isinstance(res.get("count"), int) and res["count"] < 0:
            out.append(f"resource {rid} is below zero")
    # quests
    mains = [q for q, r in (t.get("quests") or {}).items() if isinstance(r, dict) and r.get("role") == "MAIN" and r.get("status") == "active"]
    if len(mains) > 1:
        out.append(f"more than one MAIN quest is active: {mains}")
    for q, r in (t.get("quests") or {}).items():
        if not isinstance(r, dict):
            continue
        for who in r.get("participants") or []:
            if who not in (t.get("npcs") or {}) and who not in (t.get("factions") or {}) and who != "player" and not str(who).startswith("player"):
                out.append(f"quest {q}: participant {who!r} is not a record")
    # the ledger of resolved results points at records that still exist
    for e in t.get("resolved") or []:
        for g in e.get("governs") or []:
            if rules.get_path(t, g) is None and not g.startswith(("npcs.", "quests.", "rights_obligations.")):
                out.append(f"result {e['key'][:40]!r} governs {g}, which does not exist")
    return out


def check_step(before: World, after: World, events: list[dict] | None = None) -> list[str]:
    """Between two states: time only moves forward, the round advances by one, and a changed record has a cause on the journal."""
    out = []
    if _now(after) < _now(before):
        out.append("time went backwards")
    if after.round != before.round + 1:
        out.append(f"the round moved {before.round} -> {after.round}")
    if events is not None:
        changed = _changed_paths(before.tree, after.tree)
        logged = {re.sub(r"^(set|append|remove|plan|tracker)\s+", "", e.get("change", "")) for e in events}
        free = ("round", "world_state.time", "resolved", "journal", "pending", "ending_state")
        missing = sorted(p for p in changed if not any(p == l or p.startswith(l + ".") or l.startswith(p + ".") for l in logged)
                         and not p.startswith(free) and not _program_owned(p))
        if missing:
            out.append("changed with no cause on the journal: " + ", ".join(missing[:8]))
    return out


def _program_owned(path: str) -> bool:
    if path.startswith(("world_state.material_history",)) or path.endswith((".xp_awarded", ".clock.due_at", ".clock.filled")):
        return True            # written by the program: XP payouts and clock bookkeeping
    from .state import _OWNED
    return any(p.match(path) for p in _OWNED) or path.startswith(("player.condition", "player.growth_period", "player.skills", "player.item_points"))\
        or ".plan" in path or path.endswith((".temper", ".work_source"))


def _changed_paths(a, b, prefix: str = "", depth: int = 0) -> set[str]:
    if depth > 3:
        return {prefix} if a != b else set()
    out = set()
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            out |= _changed_paths(a.get(k), b.get(k), f"{prefix}.{k}" if prefix else k, depth + 1)
    elif a != b:
        out.add(prefix)
    return out
