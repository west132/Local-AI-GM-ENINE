"""Is every part of the design wired into the loop? Static checks on engine/ against localgm/. Exit 1 on any finding.
python tools/audit_flows.py"""
import pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from localgm import flow, schema as S
from localgm.state import World, background_tree

ROOT = pathlib.Path(__file__).resolve().parent.parent
E = ROOT / "engine"
steps = flow.load_steps()
intake = flow.load_intake()
src = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "localgm").glob("*.py")}
code = "\n".join(v for k, v in src.items() if k not in ("generate.py", "demo_forms.py"))
findings = []

def bad(msg): findings.append(msg); print("FINDING:", msg)

# 1. each step: handler, rules, inputs, when
w = World(background_tree((ROOT / "examples/ashfall_hunter/background.md").read_text(encoding="utf-8")))
t = flow.Turn(w, "x")
for s in steps + [intake]:
    if s["program"] not in flow.HANDLERS and s["program"] != "set_dues":
        bad(f"step {s['id']}: handler {s['program']!r} does not exist")
    for r in s.get("rules", []):
        if not (E / "rules" / f"{r}.md").exists():
            bad(f"step {s['id']}: rule file {r} is missing")
    if s["id"] != "intake":
        flow._when(s["when"], t)
    if s.get("ai") is not False and s["id"] != "intake":
        try:
            flow.inputs(s, t)
        except Exception as e:
            bad(f"step {s['id']}: inputs fail: {e}")

# 2. handlers all used; rule files all used
used_h = {s["program"] for s in steps}
for h in flow.HANDLERS:
    if h not in used_h: bad(f"handler {h} is not used by any step")
import yaml
gen = yaml.safe_load((E / "generate.yaml").read_text(encoding="utf-8"))["stages"]
used_r = {r for s in steps + [intake] + gen for r in s.get("rules", [])}
for p in sorted((E / "rules").glob("*.md")):
    if p.stem not in used_r: bad(f"rule file {p.name} is loaded by no step")

# 3. sort.steps enum = the steps that wait for the sorter's word
gated = set(re.findall(r"'(\w+)' in sort\.steps", " ".join(s["when"] for s in steps)))
enum = set(steps[0]["output"]["properties"]["steps"]["items"].get("enum", []))
if gated != enum: bad(f"sort can name {sorted(enum)} but the steps gated on it are {sorted(gated)}")
for sid in enum:
    if sid not in {s['id'] for s in steps}: bad(f"sort can name step {sid}, which does not exist")

# 4. every field an AI form offers is read by code
def fields(sch, prefix=""):
    if sch.get("type") == "object":
        for k, v in sch.get("properties", {}).items():
            yield k
            yield from fields(v)
    elif sch.get("type") == "array":
        yield from fields(sch.get("items", {}))
SKIP = {"uncertain", "for", "against", "note", "reason", "because", "channel", "notes", "problems", "ok", "description", "value", "path", "op"}
for s in steps + [intake]:
    if s.get("ai") is False or s["output"].get("type") == "string":
        continue
    for f in sorted(set(fields(s["output"])) - SKIP):
        if not re.search(r"""["']%s["']|\.%s\b""" % (f, f), code):
            bad(f"step {s['id']}: field {f!r} is never read by the program")

print(f"\n{len(steps)} turn steps + intake, {len(list((E/'rules').glob('*.md')))} rule files, {len(flow.HANDLERS)} handlers checked: "
      + ("ALL WIRED" if not findings else f"{len(findings)} FINDINGS"))
sys.exit(1 if findings else 0)
