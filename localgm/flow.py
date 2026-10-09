"""Runs a turn exactly as engine/steps.yaml says. The AI fills a form; the program executes it."""
from __future__ import annotations
import json, pathlib, re
import yaml

from . import combat, mechanics as M, schema
from .state import World, WriteRefused

ENGINE = pathlib.Path(__file__).resolve().parent.parent / "engine"


def load_steps() -> list[dict]:
    return yaml.safe_load((ENGINE / "steps.yaml").read_text(encoding="utf-8"))["turn"]


def rules_text(names: list[str]) -> str:
    return "\n\n".join((ENGINE / "rules" / f"{n}.md").read_text(encoding="utf-8") for n in names)


class Turn:
    """What the program knows during one turn; the AI sees only what each step's `input` lists."""
    def __init__(self, world: World, text: str):
        self.world, self.text = world, text
        self.sort: dict = {}
        self.facts: list[str] = []      # lines the program asserts; the narrator tells these
        self.lines: list[str] = []      # roll lines etc. printed verbatim by the program
        self.prose = ""
        self.ran: list[str] = []


def brief(world: World) -> str:
    """One line per record: enough for the AI to know what exists."""
    t = world.tree
    out = [f"PLACE {t['world_state']['location']} · {t['world_state']['time'].get('daypart')}"]
    for kind in ("npcs", "factions", "quests", "active_world_pressures"):
        for rid, rec in (t.get(kind) or {}).items():
            if isinstance(rec, dict):
                what = rec.get("job") or rec.get("objective") or rec.get("name") or ""
                out.append(f"{kind[:-1] if kind.endswith('s') else kind} {rid}: {rec.get('name', rid)} — {what}")
    return "\n".join(out)


def scene(world: World, secret: bool) -> str:
    """The place and who is in it. `secret` adds what only the simulator may know (drives, knowledge)."""
    t = world.tree
    loc = world.location()
    out = [f"PLACE: {loc.get('name', t['world_state']['location'])} — {json.dumps(loc.get('conditions', {}), ensure_ascii=False)}",
           f"WEATHER/ENVIRONMENT: {json.dumps(t['world_state'].get('environment', {}), ensure_ascii=False)}",
           f"TIME: {world.time.get('date', '')} {world.time['clock_minutes'] // 60:02d}:{world.time['clock_minutes'] % 60:02d}, {world.time['daypart']}"]
    for rid, r in world.actors_here().items():
        keys = ("name", "job", "gender", "character", "appearance") + (("drives", "relationships", "knowledge", "plan") if secret else ())
        shown = {k: r[k] for k in keys if k in r}
        shown["doing"] = (r.get("state") or {}).get("status")
        out.append(f"PERSON {rid}: {json.dumps(shown, ensure_ascii=False)}")
    others = [f"{rid}: {r.get('name')} ({(r.get('state') or {}).get('status', '')})" for rid, r in (t.get("npcs") or {}).items()
              if rid not in world.actors_here()]
    if others:
        out.append("ELSEWHERE (not present): " + "; ".join(others))
    return "\n".join(out)


def inputs(step: dict, turn: Turn) -> str:
    w, parts = turn.world, []
    for name in step["input"]:
        if name == "player_text":
            parts.append(f"PLAYER: {turn.text}")
        elif name in ("place", "actors_present"):
            parts.append(scene(w, secret=step["id"] != "tell"))
        elif name == "records_in_play":
            parts.append(brief(w))
        elif name == "player_state":
            p = w.player
            parts.append("YOU (the player character): " + json.dumps(
                {k: p.get(k) for k in ("identity", "skills", "condition", "equipment", "money", "fighting_style")},
                ensure_ascii=False))
        elif name == "active_quests":
            parts.append("QUESTS: " + json.dumps(w.tree.get("quests") or {}, ensure_ascii=False))
        elif name == "results_so_far":
            parts.append("RESULTS SO FAR:\n" + "\n".join(turn.facts))
        elif name == "facts_from_program":
            parts.append("FACTS (tell exactly these):\n" + "\n".join(turn.facts))
        elif name == "prose":
            parts.append("TEXT TO CHECK:\n" + turn.prose)
        elif name == "dues_fired":
            parts.append("DUE NOW: " + json.dumps([{"who": p_, **pl} for p_, pl in w.due()], ensure_ascii=False))
        elif name in ("time", "pressures", "plan", "morale_norms"):
            pass     # time is inside the scene; pressures and norms are added when those records exist
        else:
            raise KeyError(f"step {step['id']}: unknown input {name!r}")
    return "\n\n".join(parts)


def ask_ai(llm, step: dict, turn: Turn, extra: str = ""):
    sch = step["output"]
    system = rules_text(step["rules"])
    if sch.get("type") != "string":
        system += "\n\nREPLY with one JSON object only:\n" + schema.render(sch)
    reply = llm.ask(system, inputs(step, turn) + extra, None if sch.get("type") == "string" else sch)
    return reply


def run_step(llm, step: dict, turn: Turn, extra: str = ""):
    """Ask; validate against the form; one retry that lists the faults."""
    for _ in range(2):
        try:
            out = ask_ai(llm, step, turn, extra)
        except ValueError as e:      # the reply was not JSON at all
            errs, extra = [f"not valid JSON ({e})"], extra + "\n\nYour last reply was not valid JSON. Reply with the JSON object only."
            continue
        if step["output"].get("type") == "string":
            return str(out).strip()
        errs = schema.validate(out, step["output"])
        if not errs:
            return out
        extra += "\n\nYour last reply was refused:\n- " + "\n- ".join(errs) + "\nReply again, fixed."
    raise ValueError(f"step {step['id']}: no valid reply ({errs})")


# ---------- executors: what the program does with a valid reply ----------

def do_roll(turn: Turn, out: dict) -> None:
    if out["verdict"] == "impossible":
        turn.facts.append(f"IMPOSSIBLE: {out.get('reason', '')}")
        return
    if out["verdict"] == "certain":
        return
    r = out["roll"]
    diff = M.difficulty(r["base"], r.get("conditions"))
    tool = M.tool_mod(**{k: v for k, v in (r.get("tool") or {}).items() if k in ("fit", "condition")})
    res = M.check(r["capability"], tool, diff)
    d1, d2 = res["dice"]
    win = res["success"]
    turn.lines.append(f"2d10: {d1}+{d2} | Capability: {r['capability']:+d} | Tool: {tool:+d} | Total: {res['total']}\n"
                      f"Difficulty: {diff} | Outcome: {'Success' if win else 'Failure'}")
    st = r["stakes"]
    turn.facts.append(f"ROLL {'SUCCESS' if win else 'FAILURE'}: {st['success'] if win else st['failure']}")
    if not win and st.get("harm", "none") != "none":
        turn.facts.append(f"HARM STAKE REACHED: {st['harm']} (the program applies damage when the source is known)")


def apply_ops(world: World, ops: list[dict]) -> list[str]:
    refused = []
    for op in ops:
        try:
            world.apply(op)
        except (WriteRefused, KeyError, TypeError) as e:
            refused.append(f"{op.get('path')}: {e}")
    return refused


def do_apply(turn: Turn, out: dict) -> list[str]:
    """Rolls the asks, applies the ops, moves the clock once. Returns what the program refused."""
    w = turn.world
    for a in out.get("asks", []):
        r = M.ask(a["likelihood"])
        d1, d2 = r["dice"]
        turn.lines.append(f"ask 2d10: {d1}+{d2} {r['likelihood']:+d} = {r['total']} → {r['band']} ({a['question']})")
        turn.facts.append(f"QUESTION '{a['question']}' → {r['band']}")
    refused = apply_ops(w, out["ops"])
    days = w.advance(int(out["minutes"]))
    if days:
        turn.facts.append(f"{days} midnight(s) passed")
    return refused


def clean(prose: str) -> str:
    return re.sub(r"^```\w*\s*|\s*```$", "", prose.strip()).strip()


def run_turn(world: World, llm, text: str) -> Turn:
    turn = Turn(world, text)
    steps = {s["id"]: s for s in load_steps()}
    turn.sort = run_step(llm, steps["sort"], turn)
    turn.ran.append("sort")
    todo = [s for s in ("judge", "fight", "react", "quest") if s in turn.sort["steps"]]   # fixed order, once each
    for sid in todo:
        out = run_step(llm, steps[sid], turn)
        turn.ran.append(sid)
        if sid == "fight":
            try:
                lines, facts = combat.run(world, out)
            except M.RuleError as e:
                out = run_step(llm, steps[sid], turn, f"\n\nThe program refused: {e}. Reply again, fixed.")
                lines, facts = combat.run(world, out)
            turn.lines += lines
            turn.facts += facts
        elif sid == "judge":
            do_roll(turn, out)
        else:
            bad = do_apply(turn, out)
            if bad:   # one chance to restate only what the program refused; the clock does not move again
                again = run_step(llm, steps[sid], turn, "\n\nThe program refused these ops:\n- " + "\n- ".join(bad)
                                 + "\nReply with ONLY corrected ops (minutes 0), or an empty list.")
                apply_ops(world, again["ops"])
    if turn.sort.get("note"):
        turn.facts.append(turn.sort["note"])
    turn.prose = clean(run_step(llm, steps["tell"], turn))
    verdict = run_step(llm, steps["audit"], turn)
    if not verdict["ok"]:
        turn.facts.append("FIX IN THE RETELLING: " + "; ".join(verdict.get("problems", [])))
        turn.prose = clean(run_step(llm, steps["tell"], turn))
    world.round += 1
    return turn
