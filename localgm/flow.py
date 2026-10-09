"""Runs a turn exactly as engine/steps.yaml says. The AI fills a form; the program validates it and commits it.

Nothing about the order or conditions of a turn lives here: run_turn walks the YAML. This file holds only
what each named `program` does, and how a step's prompt is built.
"""
from __future__ import annotations
import json, os, pathlib, re, sys, time
from types import SimpleNamespace
import yaml

from . import combat, mechanics as M, schema
from .state import World, WriteRefused

ENGINE = pathlib.Path(__file__).resolve().parent.parent / "engine"
on_step = None      # the app sets this to show which step is running
MAX_WORDS = 350
_FILE = None


def _yaml() -> dict:
    global _FILE
    if _FILE is None:
        _FILE = yaml.safe_load((ENGINE / "steps.yaml").read_text(encoding="utf-8"))
    return _FILE


def load_steps() -> list[dict]:
    return _yaml()["turn"]


def load_intake() -> dict:
    return _yaml()["intake"]


def rules_text(names: list[str]) -> str:
    return "\n\n".join((ENGINE / "rules" / f"{n}.md").read_text(encoding="utf-8") for n in names)


class Turn:
    """What the program knows during one turn; the AI sees only what each step's `input` lists."""
    def __init__(self, world: World, text: str):
        self.world, self.text = world, text
        self.sort: dict = {}
        self.facts: list[str] = []      # lines the program asserts; the narrator tells these
        self.results: list[str] = []    # rolls and asks already resolved, shown to later steps
        self.lines: list[str] = []      # roll lines etc. printed verbatim by the program
        self.prose = ""
        self.ran: list[str] = []
        self.halt = False               # the turn ends before the telling (odds stop)
        self.dues: list = []            # dues shown to the AI in the current step
        self.fills: list[str] = []      # clocks that just filled; resolved in the same turn
        self.dues_pass = 1
        self.in_fight = False
        self.final = False              # the handler is running on the AI's last allowed attempt

    @property
    def pending(self):
        return self.world.tree.get("pending")


# ---------- what the AI is shown ----------

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


def pressures(world: World) -> str:
    out = []
    for pid, p in (world.tree.get("active_world_pressures") or {}).items():
        if not isinstance(p, dict):
            continue
        c = p.get("clock") or {}
        clock_ = f" · clock '{c.get('name')}' {c.get('filled', 0)}/{c.get('segments')} — pace: {c.get('pace', '')}" if c else ""
        out.append(f"PRESSURE {pid}: {p.get('name')} — now: {(p.get('state') or {}).get('current', '')} — heading: {p.get('trajectory', '')}{clock_}")
    return "\n".join(out) or "PRESSURES: none"


def inputs(step: dict, turn: Turn) -> str:
    w, parts = turn.world, []
    for name in step["input"]:
        if name == "player_text":
            parts.append(f"PLAYER: {turn.text}")
        elif name in ("place", "actors_present"):
            parts.append(scene(w, secret=step["id"] != "tell" and step["id"] != "audit"))
        elif name == "records_in_play":
            parts.append(brief(w))
        elif name == "pressures":
            parts.append(pressures(w))
        elif name == "pending":
            if turn.pending:
                parts.append("WAITING FOR THE PLAYER'S GO-AHEAD: " + turn.pending["ask"]
                             + "\n(kind=confirm if the player agrees to exactly this; anything else drops it)")
        elif name == "player_state":
            p = w.player
            parts.append("YOU (the player character): " + json.dumps(
                {k: p.get(k) for k in ("identity", "skills", "condition", "equipment", "money", "fighting_style")},
                ensure_ascii=False))
        elif name == "active_quests":
            qs = [f"{q}: {r.get('objective', '')[:140]} [{r.get('status', '')}]" for q, r in (w.tree.get("quests") or {}).items()
                  if isinstance(r, dict)]
            parts.append("QUESTS:\n" + ("\n".join(qs) or "none"))
        elif name == "results_so_far":
            parts.append("RESULTS (decided by the program; what you record must agree with them):\n" + ("\n".join(turn.results + turn.facts) or "none"))
        elif name == "facts_from_program":
            parts.append("FACTS (tell exactly these):\n" + "\n".join(turn.results + turn.facts))
        elif name == "prose":
            parts.append("TEXT TO CHECK:\n" + turn.prose)
        elif name == "dues_fired":
            shown = [{"who": p_, "what": d["what"]} for p_, d in turn.dues] + [{"clock_full": f} for f in turn.fills]
            parts.append("DUE NOW (their time has come; each resolves wherever the player is): " + json.dumps(shown, ensure_ascii=False))
        elif name in ("time", "plan", "morale_norms"):
            pass
        else:
            raise KeyError(f"step {step['id']}: unknown input {name!r}")
    return "\n\n".join(parts)


# ---------- asking ----------

def run_step(llm, step: dict, turn: Turn, extra: str = ""):
    """Ask; validate against the form; one retry that lists the faults."""
    t0 = time.time()
    if on_step:
        on_step(step["id"])
    try:
        return _run_step(llm, step, turn, extra)
    finally:
        if os.environ.get("LGM_TRACE"):
            print(f"  [{step['id']} {time.time() - t0:.0f}s]", file=sys.stderr, flush=True)


def _run_step(llm, step: dict, turn: Turn, extra: str = ""):
    sch, errs = step["output"], []
    system = rules_text(step["rules"])
    if sch.get("type") != "string":
        system += "\n\nREPLY with one JSON object only:\n" + schema.render(sch)
    for _ in range(2):
        try:
            out = llm.ask(system, inputs(step, turn) + extra, None if sch.get("type") == "string" else sch,
                          max_tokens=step.get("max_tokens"))
        except ValueError as e:      # the reply was not JSON at all
            errs, extra = [f"not valid JSON ({e})"], extra + "\n\nYour last reply was not valid JSON. Reply with the JSON object only."
            continue
        if sch.get("type") == "string":
            return str(out).strip()
        errs = schema.validate(out, sch)
        if not errs:
            return out
        extra += "\n\nYour last reply was refused:\n- " + "\n- ".join(errs) + "\nReply again, fixed."
    raise ValueError(f"step {step['id']}: no valid reply ({errs})")


# ---------- handlers: what the program does with a valid reply ----------
# A handler raises M.RuleError(message) to send the AI back once with that message.

def _roll_lines(turn: Turn, res: dict, cap: int, tool: int, diff: int, label: str = "") -> None:
    d1, d2 = res["dice"]
    turn.lines.append(f"{label}2d10: {d1}+{d2} | Capability: {cap:+d} | Tool: {tool:+d} | Total: {res['total']}\n"
                      f"Difficulty: {diff} | Outcome: {'Success' if res['success'] else 'Failure'}")


def h_route(turn: Turn, out: dict):
    turn.sort = out
    if turn.pending and out["kind"] != "confirm":
        turn.world.tree.pop("pending", None)          # the player changed their mind: dropped at no cost
        turn.facts.append("The earlier risky action was dropped; nothing was rolled.")


def h_roll(turn: Turn, out: dict):
    if out["verdict"] == "impossible":
        turn.facts.append(f"IMPOSSIBLE: {out.get('reason', '')}")
        return
    if out["verdict"] == "certain":
        return
    r = out.get("roll")
    if not r:
        raise M.RuleError("verdict 'roll' needs a roll form")
    st = r["stakes"]
    if st.get("harm", "none") in ("loss", "severe") and st.get("source") not in combat.DAMAGE:
        raise M.RuleError(f"harm '{st.get('harm')}' needs stakes.source from {sorted(combat.DAMAGE)}")
    diff = M.difficulty(r["base"], r.get("conditions"))
    tool = M.tool_mod(**{k: v for k, v in (r.get("tool") or {}).items() if k in ("fit", "condition")})
    pct = M.odds(r["capability"], tool, diff)
    severe = st.get("harm") == "severe"
    if not turn.in_fight and not r.get("committed") and (severe or pct < 25):
        # ODDS STOP: show the chance and the cost, roll nothing, wait for the player
        ask = f"about {pct}% · on failure: {st['failure']}"
        turn.world.tree["pending"] = {"roll": r, "ask": ask, "action": turn.text}
        turn.lines.append(f"{ask}\nConfirm to roll unchanged, or say something else.")
        turn.prose = f"This is risky: {ask}. Do you go ahead?"
        turn.halt = True
        return
    _resolve(turn, r)


def h_roll_pending(turn: Turn, out):
    r = turn.world.tree.pop("pending")["roll"]
    _resolve(turn, r)


def _resolve(turn: Turn, r: dict) -> None:
    """Roll the bound stakes and apply every consequence the rules attach to the result."""
    w, st = turn.world, r["stakes"]
    diff = M.difficulty(r["base"], r.get("conditions"))
    tool = M.tool_mod(**{k: v for k, v in (r.get("tool") or {}).items() if k in ("fit", "condition")})
    res = M.check(r["capability"], tool, diff)
    _roll_lines(turn, res, r["capability"], tool, diff)
    win = res["success"]
    turn.results.append(f"RESULT roll {'SUCCESS' if win else 'FAILURE'}: {st['success'] if win else st['failure']}")
    skill = r.get("skill")
    if skill and skill in (w.player.get("skills") or {}):
        gain = w.credit_skill(skill, win, diff, r.get("challenge"))
        if gain:
            turn.facts.append(f"The player's {skill} gained experience.")
    if win and w.player.get("progression") and r.get("challenge") and r.get("scope"):
        lv = w.player["progression"]["state"]
        amount = M.xp_award(r["challenge"], lv["level"], r["scope"])
        lv["level"], lv["xp"], ups = M.add_xp(lv["level"], lv["xp"], amount)
        turn.facts.append(f"The player earned {amount} XP." + (f" Level up to {ups[-1]}." if ups else ""))
    harm = st.get("harm", "none")
    if not win and harm in ("loss", "severe"):
        raw = []
        for _ in range(2 if harm == "severe" else 1):
            n, how = combat.damage_roll(st["source"])
            raw.append(n)
            turn.lines.append(f"Damage: {how} − soak {st.get('soak', 0)}")
        h = w.hurt(raw, st.get("soak", 0), "player")
        turn.lines.append(f"HP {h['before']} → {h['hp']}" + (f" — {h['state']}" if h["state"] != "standing" else ""))
        turn.results.append(f"RESULT harm: the player is {h['state']}, HP {h['hp']}." + (" A lasting injury is owed (record it)." if h["lasting_injury"] else ""))
    elif not win and harm == "setback":
        turn.results.append("RESULT: position worsens; no HP lost.")


def h_combat(turn: Turn, out: dict):
    turn.in_fight = True
    lines, facts = combat.run(turn.world, out)
    turn.lines += lines
    turn.results += ["RESULT " + f for f in facts]


_WH = re.compile(r"^\s*(what|who|whom|whose|where|when|why|how|which)\b", re.I)


def ask_problem(a: dict) -> str | None:
    """An open question is yes/no and every likelihood point rests on a stated fact (section 11)."""
    if _WH.match(a["question"]) or not a["question"].strip().endswith("?"):
        return f"question {a['question']!r} must be a yes/no question ending in '?'; what the records already say is not rolled"
    if a["likelihood"] and not (a.get("for") or a.get("against")):
        return f"question {a['question']!r}: a likelihood of {a['likelihood']:+d} needs the fact behind it in 'for' or 'against'"
    return None


def h_ask_roll(turn: Turn, out: dict):
    bad = [p for p in map(ask_problem, out["asks"]) if p]
    if bad and not turn.final:
        raise M.RuleError("\n- " + "\n- ".join(bad))
    for a in out["asks"]:
        if ask_problem(a):
            continue                          # refused twice: not rolled, not recorded
        r = M.ask(a["likelihood"])
        d1, d2 = r["dice"]
        turn.lines.append(f"ask 2d10: {d1}+{d2} {r['likelihood']:+d} = {r['total']} → {r['band']} ({a['question']})")
        turn.results.append(f"RESULT question '{a['question']}' → {r['band']}")


def _typed_changes(trial: World, turn: Turn, out: dict, new_fills: list[str]) -> list[str]:
    """Money and clocks: the AI states what happened, the program does the arithmetic."""
    faults = []
    if out.get("money"):
        try:
            trial.pay(int(out["money"]))
        except M.RuleError as e:
            faults.append(f"money {out['money']:+d}: {e}")
    shown = {p.split(".", 1)[1]: e for p, e in turn.dues if e.get("is_clock")}
    answered = set()
    for c in out.get("clocks", []):
        pid = c["pressure"].split(".")[-1]
        if pid not in shown:
            faults.append(f"clock {c['pressure']} was not due")
            continue
        answered.add(pid)
        res = trial.tick_clock("active_world_pressures." + pid, c["operated"], c.get("extra", False))
        if res["full"]:
            new_fills.append(f"{pid} FULL — {res['on_fill']}")
    faults += [f"clock {pid} was shown as due; answer it in 'clocks'" for pid in shown if pid not in answered]
    return faults


def h_commit(turn: Turn, out: dict):
    """D: validate everything on a copy; commit all of it or none of it."""
    w, new_fills = turn.world, []
    trial = w.clone()
    faults = trial.commit(out["ops"])
    faults += _typed_changes(trial, turn, out, new_fills)
    if faults:
        raise M.RuleError("nothing was recorded. Fix:\n- " + "\n- ".join(faults))
    w.tree = trial.tree
    turn.fills = new_fills
    for p, d in turn.dues:
        w.clear_due(p, d)
    for op in out["ops"]:
        v = json.dumps(op.get("value"), ensure_ascii=False) if "value" in op else ""
        turn.facts.append(f"RECORDED {op['op']} {op['path']} {v[:160]}")
    if out.get("money"):
        turn.facts.append(f"RECORDED cash {out['money']:+d}")
    minutes = int(out["minutes"]) if turn.dues_pass == 1 else 0
    days = w.advance(minutes)
    if days:
        turn.facts.append(f"{days} midnight(s) passed")
    if turn.dues_pass == 1 and (w.due() or turn.fills):      # something fell due during this action
        turn.dues_pass = 2
        return "again"


def h_commit_ops(turn: Turn, out: dict):
    faults = turn.world.commit(out["ops"])
    if faults:
        raise M.RuleError("nothing was recorded. Fix:\n- " + "\n- ".join(faults))
    for op in out["ops"]:
        turn.facts.append(f"RECORDED {op['op']} {op['path']} {json.dumps(op.get('value'), ensure_ascii=False)[:160] if 'value' in op else ''}")


def clean(prose: str) -> str:
    """Strip code fences, drop any sentence already said, and cap the length at a sentence end.
    A model that starts to loop is cut off by the program rather than shown to the player."""
    prose = re.sub(r"^```\w*\s*|\s*```$", "", prose.strip()).strip()
    seen, out, words = set(), [], 0
    for para in prose.split("\n\n"):
        kept = []
        for sent in re.findall(r"[^.!?。！？]+[.!?。！？]*[\"”')]*\s*", para):
            key = re.sub(r"\W+", " ", sent.lower()).strip()
            if key in seen or not key:
                continue
            seen.add(key)
            if words + len(sent.split()) > MAX_WORDS:
                break
            kept.append(sent.strip())
            words += len(sent.split())
        if kept:
            out.append(" ".join(kept))
        if words >= MAX_WORDS:
            break
    return "\n\n".join(out)


def h_show(turn: Turn, out: str):
    turn.prose = clean(out)


def h_audit(turn: Turn, out: dict):
    if not out["ok"]:
        turn.facts.append("FIX IN THE RETELLING: " + "; ".join(out.get("problems", [])))
        return "retell"


HANDLERS = {"route": h_route, "roll": h_roll, "roll_pending": h_roll_pending, "combat": h_combat, "ask_roll": h_ask_roll,
            "commit": h_commit, "commit_ops": h_commit_ops, "show": h_show, "audit": h_audit}


# ---------- the loop ----------

def _when(expr: str, turn: Turn) -> bool:
    if expr == "always":
        return True
    env = {"sort": SimpleNamespace(**{"kind": "", "steps": [], **turn.sort}), "turn": turn}
    return bool(eval(expr, {"__builtins__": {}}, env))


def execute(llm, step: dict, turn: Turn):
    """One step: show, ask, hand to its handler; a refusal sends the AI back once with the reason."""
    if "dues_fired" in step.get("input", []):
        turn.dues = turn.world.due()
    if step.get("ai") is False:
        return HANDLERS[step["program"]](turn, None)
    extra = ""
    for attempt in range(2):
        turn.final = attempt == 1
        out = run_step(llm, step, turn, extra)
        try:
            return HANDLERS[step["program"]](turn, out)
        except M.RuleError as e:
            extra = f"\n\nThe program refused your reply: {e}\nReply again, fixed."
    turn.facts.append(f"(Step {step['id']} could not be recorded; narrate none of its changes.)")


def intake(world: World, llm, batch: int = 4) -> None:
    """Once per new game: the AI splits each plan note into dues and triggers; the program stores them."""
    step = load_intake()
    t = world.time
    for i in range(0, len(todo := world.needs_intake()), batch):
        paths = todo[i:i + batch]
        def note(p: str) -> str:
            if p.startswith("active_world_pressures."):
                return (f"{p}: clock '{world.get(p + '.clock.name')}' | pace={world.get(p + '.clock.pace')!r} | "
                        f"first check={world.get(p + '.clock.due')!r}")
            return f"{p}: move={world.get(p + '.plan.move')!r} | note={world.get(p + '.plan.text') or '(none given)'!r}"
        notes = "\n".join(note(p) for p in paths)
        extra = f"TODAY: {t.get('date')} at {t['clock_minutes'] // 60:02d}:{t['clock_minutes'] % 60:02d} (day_offset 0)\n\n{notes}"
        problems = ""
        for _ in range(3):
            out = run_step(llm, {**step, "input": []}, Turn(world, ""), "\n\n" + extra + problems)
            problems = ""
            for a in out["actors"]:
                if a["id"] not in paths:
                    continue
                try:
                    if a["id"].startswith("active_world_pressures."):
                        world.set_clock(a["id"], a["dues"][0], a.get("interval_minutes"))
                    else:
                        world.set_dues(a["id"], a["dues"], a["triggers"])
                except (ValueError, KeyError, IndexError, WriteRefused) as e:
                    problems += f"\n- {a['id']}: {e}"
            left = [p for p in paths if p in world.needs_intake()]
            if not left:
                break
            problems = "\nFix these and answer for ONLY the items still listed:\n" + "\n".join(f"- {p}" for p in left) + problems
        else:
            for p in left:      # keep the note as a trigger rather than lose it
                if p.startswith("active_world_pressures."):
                    world.get(p + ".clock").pop("due", None)
                else:
                    plan = world.get(p + ".plan")
                    plan["triggers"].append(plan.pop("text", None) or "re-plan at once")


def run_turn(world: World, llm, text: str) -> Turn:
    """Runs on a copy of the world; the real one changes only if the whole turn completes."""
    work = world.clone()
    turn = Turn(work, text)
    steps = load_steps()
    byid = {s["id"]: s for s in steps}
    for step in steps:
        if not _when(step["when"], turn):
            continue
        again = None
        for _ in range(3):              # a handler may ask for one more pass (a due that fell during the action, a retelling)
            again = execute(llm, step, turn)
            turn.ran.append(step["id"])
            if again == "again":
                continue
            if again == "retell":
                execute(llm, byid["tell"], turn)
            break
    work.round += 1
    world.tree, world.round = work.tree, work.round
    return turn
