"""The person's side of --relay.  python tools/relay.py OUT wait            show the next unanswered request
                                   python tools/relay.py OUT answer < reply.json    answer it, then show the next"""
import json, pathlib, sys, time

out = pathlib.Path(sys.argv[1]) / "relay"
seen = out / "shown_systems.txt"


def pending():
    for r in sorted(out.glob("req_*.json")):
        if not (out / r.name.replace("req_", "rep_")).exists():
            return r
    return None


if sys.argv[2] == "answer":
    r = pending()
    reply = json.load(sys.stdin)
    (out / r.name.replace("req_", "rep_")).write_text(json.dumps({"reply": reply}, ensure_ascii=False), encoding="utf-8")
    time.sleep(1.0)
t0 = time.time()
while True:
    r = pending()
    if r:
        break
    if (out.parent / "DONE").exists():
        print("RUN FINISHED"); sys.exit(0)
    if time.time() - t0 > 500:
        print("(still waiting)"); sys.exit(0)
    time.sleep(0.5)
q = json.loads(r.read_text(encoding="utf-8"))
shown = set(seen.read_text().split()) if seen.exists() else set()
import hashlib
sid = hashlib.sha1(q["system"].encode()).hexdigest()[:8]
print(f"=== REQUEST {q['n']}  wants={q['wants']}  max_tokens={q['max_tokens']}  system={sid} ===")
if sid not in shown:
    print("--- SYSTEM (first time) ---\n" + q["system"])
    seen.write_text("\n".join(shown | {sid}))
else:
    print("--- SYSTEM: same rules as before (" + sid + "); the reply form is: ---" + q["form"])
seen_p, parts = set(), []
for para in q["user"].split("\n\n"):
    if para in seen_p:
        parts.append("(same paragraph as above, shown twice in the real prompt)")
    else:
        seen_p.add(para); parts.append(para)
print("--- USER ---\n" + "\n\n".join(parts))
