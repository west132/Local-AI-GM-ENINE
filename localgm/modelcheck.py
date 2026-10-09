"""Can this model run the engine? Seven small, fixed situations on a tiny world; each step's form is checked the way the
program will check it in play. Nothing here changes a save. python -m localgm.modelcheck --url http://localhost:1234/v1"""
from __future__ import annotations
import argparse, json, pathlib, re, time

from . import backend, flow, mechanics as M, rules, settings
from .state import World, background_tree

WORLD = pathlib.Path(__file__).resolve().parent.parent / "examples" / "harbour_guesthouse" / "background.md"


class Counting:
    def __init__(self, inner):
        self.inner, self.n, self.secs = inner, 0, 0.0

    def ask(self, system, user, schema=None, max_tokens=None):
        self.n += 1
        t0 = time.time()
        try:
            return self.inner.ask(system, user, schema, max_tokens=max_tokens)
        finally:
            self.secs += time.time() - t0


def _turn(text: str):
    return flow.Turn(World(background_tree(WORLD.read_text(encoding="utf-8"))), text)


def _step(sid: str) -> dict:
    return next(s for s in flow.load_steps() if s["id"] == sid)


def c_sort_quiet(ai):
    t = _turn("I sit down by the window and rest my feet.")
    out = flow.run_step(ai, _step("sort"), t)
    ok = out["kind"] in ("fast", "retrieval", "continuation")
    if ok:
        try:
            flow.h_route(t, out)           # the same checks the turn applies (a note is required)
        except M.RuleError as e:
            return False, f"the program would refuse it: {e}"
    return ok, f"sorted as {out['kind']}" + ("" if ok else " (nothing is pending and nobody is affected: expected fast)")


def c_sort_person(ai):
    t = _turn("I ask Hobb whether he has a room for tonight.")
    out = flow.run_step(ai, _step("sort"), t)
    try:
        flow.h_route(t, out)
    except M.RuleError as e:
        return False, f"the program would refuse it: {e}"
    return "react" in t.sort["steps"], f"sorted as {out['kind']}, steps {out['steps']} → the program ran {t.sort['steps']}" + ("" if "react" in t.sort["steps"] else " (a person is affected: the world must answer)")


def c_judge(ai):
    t = _turn("I try to pick the lock on the cellar door.")
    out = flow.run_step(ai, _step("judge"), t)
    try:
        rules.check_cites(t.world, out.get("cites", []))
        if out["verdict"] == "roll":
            r = out["roll"]
            rules.roll_inputs(t.world, r)
        elif not out.get("cites"):
            return False, "a verdict with no cited record"
    except (M.RuleError, KeyError) as e:
        return False, f"the program would refuse it: {e}"
    return True, f"verdict {out['verdict']}"


def c_wonder(ai):
    t = _turn("I ask Hobb for a room for the night.")
    out = flow.run_step(ai, _step("wonder"), t)
    bad = [p for p in map(flow.ask_problem, out["asks"]) if p]
    try:
        for a in out["asks"]:
            rules.check_cites(t.world, a.get("cites", []))
    except M.RuleError as e:
        bad.append(str(e))
    return not bad, (f"{len(out['asks'])} question(s)" if not bad else bad[0][:120])


def c_react(ai):
    t = _turn("I pay Hobb for a cup of tea and sit at the front desk for twenty minutes.")
    t.results.append("RESULT question 'Does Hobb serve tea?' → YES (settled): he runs a guesthouse")
    out = flow.run_step(ai, _step("react"), t)
    if out.get("asks"):
        return False, "it asked a question although the answer was already given in RESULTS"
    if len(str(out.get("report") or "").strip()) < 5:
        return False, "no `report` (the plain account of what happened, which the telling is built from)"
    faults = rules.op_faults(t.world, out["ops"], t.resolved, t.governs) + t.world.clone().commit([o for o in out["ops"] if o["op"] != "plan"])
    return not faults, (f"{len(out['ops'])} change(s), {out['minutes']} min" if not faults else faults[0][:140])


def c_tell(ai):
    t = _turn("I ask Hobb for a room.")
    t.results.append("RESULT question 'Does Hobb have a room?' → NO, BUT")
    t.facts.append('RECORDED set npcs.hobb_marren.state.status "offers the attic room only, for a higher price"')
    text = flow.clean(flow.run_step(ai, _step("tell"), t))
    words = len(text.split())
    echoed = rules.norm(t.text) in rules.norm(text) or "FACTS" in text or "RECORDED" in text or "{" in text
    ok = 12 <= words <= flow.MAX_WORDS and not echoed
    return ok, f"{words} words" + (" (it repeated the instructions or the player's line instead of telling the scene)" if echoed else "")


def c_audit(ai):
    t = _turn("I ask Hobb for a room.")
    t.prose = "Hobb looks up from his accounts and says the attic room is free, for a higher price."
    t.results.append("RESULT question 'Does Hobb have a room?' → NO, BUT")
    out = flow.run_step(ai, _step("audit"), t)
    return isinstance(out["ok"], bool), f"ok={out['ok']}"


CASES = [("Sorts a quiet action", c_sort_quiet), ("Sorts an action that involves a person", c_sort_person),
         ("Judges whether an action is possible", c_judge), ("Asks only valid questions", c_wonder),
         ("Writes changes the program accepts", c_react), ("Tells the scene", c_tell), ("Checks its own telling", c_audit)]


def run(ai, progress=None) -> dict:
    ai = Counting(ai)
    rows = []
    for i, (name, fn) in enumerate(CASES):
        if progress:
            progress(i, name)
        n0, s0 = ai.n, ai.secs
        try:
            ok, note = fn(ai)
        except Exception as e:       # no usable reply at all
            ok, note = False, f"no usable reply: {str(e)[:140]}"
        rows.append({"name": name, "ok": bool(ok), "note": note, "calls": ai.n - n0, "secs": round(ai.secs - s0, 1),
                     "retried": ai.n - n0 > 1})
    passed = sum(r["ok"] for r in rows)
    verdict = ("Good: this model should run the engine." if passed == len(rows) else
               "Usable, with refusals: expect some turns to be retried." if passed >= 5 else
               "Weak: it will often fail steps. Try a larger model." if passed >= 3 else
               "Not capable: it cannot fill the engine's forms.")
    return {"rows": rows, "passed": passed, "total": len(rows), "verdict": verdict, "secs": round(ai.secs), "calls": ai.n}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url"); ap.add_argument("--model", default=""); ap.add_argument("--gguf"); ap.add_argument("--ctx", type=int, default=16384)
    a = ap.parse_args(argv)
    ai = backend.OpenAICompat(a.url, a.model) if a.url else backend.LlamaCpp(a.gguf, a.ctx)
    res = run(ai, lambda i, n: print(f"[{i + 1}/{len(CASES)}] {n} ...", flush=True))
    for r in res["rows"]:
        print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['name']:42s} {r['secs']:6.1f}s  {r['note']}")
    print(f"\n{res['passed']}/{res['total']} — {res['verdict']}  ({res['calls']} calls, {res['secs']}s)")


if __name__ == "__main__":
    main()
