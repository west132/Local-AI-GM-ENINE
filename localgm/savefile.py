"""Read and write SAVE_TEMPLATE files, so a game made in a chat can continue here and the other way round.
A save = Part A (readable state) + Part B (capsule: only what differs from the BACKGROUND, one `path :: value` line each)."""
from __future__ import annotations
import copy, json, re

import yaml

from . import rules
from .state import World, background_tree, plain

STATUS_WORD = re.compile(r"^\s*(available|active|completed|failed|abandoned|blocked)\b[\s:;—–-]*(.*)$", re.S)


def _blocks(text: str) -> list[dict]:
    out = []
    for b in re.findall(r"```ya?ml\n(.*?)```", text, re.S):
        try:
            d = yaml.safe_load(b)
        except yaml.YAMLError:
            continue
        if isinstance(d, dict):
            out.append(plain(d))
    return out


def _value(text: str):
    """A capsule value: a JSON/flow structure, a number, a bool, or plain text (never guessed from a colon)."""
    t = text.strip()
    if t[:1] in "[{\"'":
        try:
            return plain(yaml.safe_load(t))
        except yaml.YAMLError:
            return t
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if t in ("true", "false"):
        return t == "true"
    return t


def _set(tree: dict, path: str, value) -> None:
    keys, cur = path.split("."), tree
    for k in keys[:-1]:
        if not isinstance(cur.get(k), dict):
            if isinstance(cur.get(k), list):          # BACKGROUND has a list where the save keys its entries (material_history)
                cur[k] = {f"bg{i}": v for i, v in enumerate(cur[k])}
            else:
                cur[k] = {}
        cur = cur[k]
    last = keys[-1]
    if isinstance(value, dict) and isinstance(cur.get(last), dict):
        cur[last] = _merge(cur[last], value)
    else:
        cur[last] = value


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _delete(tree: dict, path: str) -> None:
    keys, cur = path.split("."), tree
    for k in keys[:-1]:
        cur = cur.get(k) if isinstance(cur, dict) else None
        if cur is None:
            return
    if isinstance(cur, dict):
        cur.pop(keys[-1], None)


def capsule_lines(text: str) -> tuple[list[tuple[int, str, str]], list[tuple[str, str]]]:
    """(round, path, value text) in file order, and the retired (path, reason) pairs."""
    part = text.split("# PART B", 1)[-1]
    records, retired, mode = [], [], "records"
    for line in part.splitlines():
        if re.match(r"^\s{2}retired:\s*$", line):
            mode = "retired"
            continue
        if re.match(r"^\s{2}records:\s*$", line):
            mode = "records"
            continue
        m = re.match(r"^\s{4}(\S+) :: (.*)$", line)
        if not m:
            continue
        path, val = m.groups()
        if mode == "retired":
            retired.append((path, val))
            continue
        r = re.match(r"^R(\d+):\s?(.*)$", val, re.S)
        records.append((int(r.group(1)) if r else -1, path, r.group(2) if r else val))
    return records, retired


def import_save(save_text: str, background_text: str) -> tuple[World, list[str]]:
    """Background + capsule + readable part -> a world that can be played, and what had to be repaired."""
    notes = []
    save_text = save_text.replace("\r\n", "\n").replace("\r", "\n")     # browsers and Windows editors send CRLF
    background_text = background_text.replace("\r\n", "\n").replace("\r", "\n")
    base = World(background_tree(background_text)).tree          # plans normalised once, here
    tree = copy.deepcopy(base)
    blocks = _blocks(save_text.split("# PART B", 1)[0])
    merged = {}
    for b in blocks:
        merged.update(b)
    records, retired = capsule_lines(save_text)
    for _, path, val in sorted(records, key=lambda x: x[0]):      # later rounds win; unstamped is oldest (stable order)
        if val.startswith("no longer holds"):
            _delete(tree, path)
        else:
            _set(tree, path, _value(val))
    for path, _ in retired:
        _delete(tree, path)
    # Part A is the authority for the state it carries
    for key in ("player", "enabled_modules", "narrative_theme"):
        if key in merged:
            tree[key] = merged[key]
    ws = merged.get("world_state") or {}
    for key in ("location", "time", "environment"):
        if key in ws:
            tree["world_state"][key] = ws[key]
    rnd = int(((merged.get("round") or {}).get("last_completed_round")) or 0)
    for qid, q in (tree.get("quests") or {}).items():            # the chat wrote "completed 2026-10-06 — note"; the program wants the word
        if isinstance(q, dict) and isinstance(q.get("status"), str):
            m = STATUS_WORD.match(q["status"])
            if m and q["status"] != m.group(1):
                q["status"], q["status_note"] = m.group(1), m.group(2).strip()
                notes.append(f"quest {qid}: status word kept, the rest moved to status_note")
    for kind in ("npcs", "factions"):                            # "12 — full night's rest" -> 12
        for rid, r in (tree.get(kind) or {}).items():
            st = r.get("state") if isinstance(r, dict) else None
            if isinstance(st, dict):
                for k in ("hp", "mp"):
                    if isinstance(st.get(k), str):
                        m = re.match(r"\s*(\d+)", st[k])
                        if m:
                            st[k] = int(m.group(1))
                        else:
                            st.pop(k)
                            notes.append(f"{kind}.{rid}.state.{k}: not a number, dropped")
    world = World(tree, rnd)
    todo = world.needs_intake()
    if todo:
        notes.append(f"{len(todo)} plan note(s) still need to be split into dues (the first turn does it)")
    notes += [f"check: {f}" for f in rules.quest_faults(base, world.tree, rules.module(world, "numeric_level_xp"))[:5]]
    notes += [f"check: {f}" for f in rules.player_faults(world.tree)[:5]]
    return world, notes


def _diff(base, now, path, out: list[tuple[str, object]]) -> None:
    if isinstance(base, dict) and isinstance(now, dict):
        for k, v in now.items():
            if k not in base:
                out.append((f"{path}.{k}" if path else k, v))
            else:
                _diff(base[k], v, f"{path}.{k}" if path else k, out)
    elif base != now:
        out.append((path, now))


def export_save(world: World, background_text: str, name: str = "game") -> str:
    t = world.tree
    base = World(background_tree(background_text)).tree
    changes: list[tuple[str, object]] = []
    for k, v in t.items():
        if k in ("player", "enabled_modules", "narrative_theme"):
            continue
        if k == "world_state":
            for kk, vv in v.items():
                if kk not in ("location", "time", "environment"):
                    _diff(base.get("world_state", {}).get(kk), vv, f"world_state.{kk}", changes)
            continue
        _diff(base.get(k), v, k, changes)
    retired = []

    def gone(b, n, path):
        if isinstance(b, dict) and isinstance(n, dict):
            for k in b:
                if k not in n:
                    retired.append(f"{path}.{k}" if path else k)
                else:
                    gone(b[k], n[k], f"{path}.{k}" if path else k)
    for k in base:
        if k in t:
            gone(base[k], t[k], k)
    fmt = lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else (str(v) if not isinstance(v, str) else v)
    ws = t["world_state"]
    part_a = {"background_ref": {"id": t.get("background_id")}, "round": {"last_completed_round": world.round, "saved_completed_round": world.round},
              "world_state": {k: ws[k] for k in ("location", "time", "environment") if k in ws}}
    dump = lambda d: yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=110)
    lines = [f"# SAVE — {name} — R{world.round}", "", "For `NEW ENGINE v5.0` · written by Local AI GM", "", "# PART A — READABLE", "",
             "## 1. Current state", "", "```yaml", dump(part_a).rstrip(), "```", "", "## 2. Player", "", "```yaml",
             dump({"player": t["player"]}).rstrip(), "```", "", "## 3. Modules and theme", "", "```yaml",
             dump({"enabled_modules": t.get("enabled_modules"), "narrative_theme": t.get("narrative_theme")}).rstrip(), "```", "",
             "---", "", "# PART B — CAPSULE", "", "```yaml", "capsule:", f"  save_round: {world.round}", "  encoding: plain",
             f"  supersedes_deltas_through: {world.round}", "  records:"]
    for path, v in changes:
        lines.append(f"    {path} :: R{world.round}: {fmt(v)}")
    lines.append("  retired:")
    for path in retired:
        lines.append(f"    {path} :: removed in play")
    lines += ["```", ""]
    return "\n".join(lines)
