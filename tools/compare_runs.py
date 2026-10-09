"""Put two run folders side by side: dice, settled answers, calls, prompt size, refusals.
python tools/compare_runs.py docs/runs/ashfall_r10_claude runs/out_A2"""
import json, pathlib, re, sys


def stats(folder):
    f = pathlib.Path(folder)
    rounds = [json.loads(l) for l in (f / "rounds.jsonl").read_text(encoding="utf-8").splitlines()][1:]
    calls = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((f / "calls").glob("*.json"))]
    systems = {p.stem: p.read_text(encoding="utf-8") for p in (f / "systems").glob("*.txt")}
    lines = [l for r in rounds for l in r.get("lines", [])]
    chars = sum(len(c["user"]) + len(systems.get(c["system_id"], "")) for c in calls)
    settled = sum(len(re.findall(r"\(settled\)", c["user"].split("RESULTS", 1)[-1].split("ALREADY", 1)[0])) for c in calls) if False else None
    return {
        "rounds ok": f"{sum(1 for r in rounds if r['ok'])}/{len(rounds)}",
        "AI calls": len(calls),
        "dice lines printed": sum(1 for l in lines if re.search(r"2d10|1d10|1d4|d12|roll", l)),
        "  of which open questions": sum(1 for l in lines if l.startswith("ask ")),
        "  of which skill/fight rolls": sum(1 for l in lines if not l.startswith("ask ") and re.search(r"Total:|Exchange|2d10", l)),
        "questions settled without dice": sum(r.get("settled_asks", 0) for r in rounds) if any("settled_asks" in r for r in rounds) else "n/a (not recorded)",
        "prompt chars sent (≈ tokens × 4)": chars,
        "refused / failed AI answers": sum(1 for c in calls if c.get("error")),
    }


a, b = stats(sys.argv[1]), stats(sys.argv[2])
w = max(map(len, a))
print(f"{'':{w}}  {'A (first engine)':>22}  {'A2 (fixed engine)':>22}")
for k in a:
    print(f"{k:{w}}  {str(a[k]):>22}  {str(b[k]):>22}")
