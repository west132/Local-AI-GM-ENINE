"""Turn a run folder (tools/run10.py output) into one readable Markdown file. Nothing is edited; every line is copied."""
import json, pathlib, sys

out = pathlib.Path(sys.argv[1])
title = sys.argv[2] if len(sys.argv) > 2 else out.name
rows = [json.loads(l) for l in (out / "rounds.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
calls = sorted((out / "calls").glob("*.json"))
md = [f"# {title}", "", f"Raw data: `{out.name}/calls/*.json` holds every request and reply, in order ({len(calls)} calls); `systems/` holds the rule text each call carried.", ""]
tot = {"secs": 0, "n": len(calls), "errors": 0}
for c in calls:
    d = json.loads(c.read_text(encoding="utf-8"))
    tot["secs"] += d["secs"]
    tot["errors"] += bool(d["error"])
md.append(f"AI time in calls: {tot['secs']:.0f}s over {tot['n']} calls; calls that returned unusable output: {tot['errors']}.\n")
first = rows[0]
md += [f"## Start of game (intake)", f"{first.get('intake')} · {first.get('calls')} AI calls · {first.get('secs')}s", ""]
for d in rows[1:]:
    md += [f"## Round {d['round_attempt']}", f"**Player:** {d['input']}", "",
           f"`{d.get('header_before')}` → `{d.get('header_after', '(round did not complete)')}`", ""]
    if not d["ok"]:
        md += [f"**ROUND FAILED:** `{d['error']}`", "", "```", d.get("trace", ""), "```", ""]
        continue
    md += [f"Sorted as: `{json.dumps(d['sort'], ensure_ascii=False)}`", f"Steps that ran: {', '.join(d['ran'])} · AI calls this round: {d['ai_calls']} · {d['secs']}s" + (f" · questions rolled: {d['dice_asks']}, settled by the records: {d['settled_asks']}" if 'dice_asks' in d else ""), ""]
    if d["lines"]:
        md += ["**Printed by the program (dice and arithmetic):**", "```"] + d["lines"] + ["```", ""]
    if d.get("halt"):
        md += ["*(the turn stopped at an odds check)*", ""]
    md += ["**Story:**", "", d["prose"], ""]
    if d["events"]:
        md += ["<details><summary>Journal events (cause / channel)</summary>", "", "```"] + [json.dumps(e, ensure_ascii=False) for e in d["events"]] + ["```", "</details>", ""]
md.append("")
state = out / "saves" / "run" / "state.json"
if state.exists():
    s = json.loads(state.read_text(encoding="utf-8")); t = s["tree"]
    md += ["## End state", f"- round {s['round']} · {t['world_state']['time'].get('date')} {t['world_state']['time']['clock_minutes'] // 60:02d}:{t['world_state']['time']['clock_minutes'] % 60:02d} · at `{t['world_state']['location']}`",
           f"- cash: {t['player']['money']}", f"- progression: {t['player'].get('progression')}", f"- HP/MP: {t['player'].get('condition')}",
           f"- quests: { {k: v['status'] for k, v in t['quests'].items()} }",
           "- results the dice fixed (the ledger):"] + [f"  - R{e['round']} {e['kind']}: **{e['outcome']}** — {e['text']}" for e in t.get("resolved", [])]
(out / "TRANSCRIPT.md").write_text("\n".join(md), encoding="utf-8")
print(out / "TRANSCRIPT.md", len("\n".join(md)))
