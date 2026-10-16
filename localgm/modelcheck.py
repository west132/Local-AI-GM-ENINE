"""Can this model run the engine? Seven small, fixed situations on a tiny world; the one-form reply is checked the way the
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


def _gm(ai, text: str, results: tuple = (), want: tuple = ("done",)):
    """Ask the one-form step and give the reply to the same handler a turn uses. Returns (turn, reply, problem or None)."""
    t = _turn(text)
    t.results += results
    out = flow.run_step(ai, flow.single_step(), t)
    if out["mode"] not in want:
        return t, out, f"answered mode {out['mode']} (expected {' or '.join(want)})"
    try:
        flow.h_gm(t, out)
    except (M.RuleError, KeyError, IndexError, TypeError, AttributeError, ValueError) as e:
        return t, out, f"the program would refuse it: {str(e)[:160]}"
    return t, out, None


def c_quiet(ai):
    t, out, bad = _gm(ai, "I sit down by the window and rest my feet.")
    return not bad, bad or f"settled in one reply: {out['minutes']} min, {len(out.get('ops') or [])} change(s)"


def c_risky(ai):
    t, out, bad = _gm(ai, "I try to pick the lock on the cellar door.", want=("roll", "ask", "done"))
    return not bad, bad or f"mode {out['mode']}"


def c_person(ai):
    t, out, bad = _gm(ai, "I ask Hobb whether he has a room for tonight.", want=("ask", "done"))
    return not bad, bad or f"mode {out['mode']}"


def c_result(ai):
    t, out, bad = _gm(ai, "I ask Hobb for a room.", results=("RESULT question 'Does Hobb have a room?' → NO, BUT",))
    if bad:
        return False, bad
    yes = any(re.search(r"\b(agrees?|gives?|shows? (you|the player) to)\b", str(o.get("value")), re.I) for o in out.get("ops") or [] if isinstance(o, dict))
    return not yes, "the changes agree with the result it was given" if not yes else "it recorded a yes although the result was NO"


def c_tell(ai):
    t, out, bad = _gm(ai, "I ask Hobb for a room.", results=("RESULT question 'Does Hobb have a room?' → NO, BUT",))
    if bad:
        return False, bad
    text = flow.clean(str(out.get("scene") or ""))
    words = len(text.split())
    echoed = rules.norm(t.text) in rules.norm(text) or "WHAT IS TRUE" in text or "WHAT HAPPENED" in text or "RECORDED" in text or "{" in text
    ok = 12 <= words <= flow.MAX_WORDS and not echoed
    return ok, f"{words} words" + (" (it repeated the instructions or the player's line instead of telling the scene)" if echoed else "")


def c_fight(ai):
    t, out, bad = _gm(ai, "I attack the rat that runs out of the cellar.", want=("fight",))
    return not bad, bad or f"{len(out.get('exchanges') or [])} exchange(s)"


def c_audit(ai):
    t = _turn("I ask Hobb for a room.")
    t.prose = "Hobb looks up from his accounts and says the attic room is free, for a higher price."
    t.results.append("RESULT question 'Does Hobb have a room?' → NO, BUT")
    out = flow.run_step(ai, _step("audit"), t)
    return isinstance(out["ok"], bool), f"ok={out['ok']}"


CASES = [("Settles an ordinary action in one reply", c_quiet), ("Judges a risky action", c_risky), ("Handles an action that involves a person", c_person),
         ("Follows a result it is given", c_result), ("Tells the scene", c_tell), ("Starts a fight the program accepts", c_fight), ("Checks its own telling", c_audit)]


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
    ap.add_argument("--url"); ap.add_argument("--model", default=""); ap.add_argument("--gguf"); ap.add_argument("--ctx", type=int, default=32768)
    a = ap.parse_args(argv)
    ai = backend.OpenAICompat(a.url, a.model) if a.url else backend.LlamaCpp(a.gguf, a.ctx)
    res = run(ai, lambda i, n: print(f"[{i + 1}/{len(CASES)}] {n} ...", flush=True))
    for r in res["rows"]:
        print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['name']:42s} {r['secs']:6.1f}s  {r['note']}")
    print(f"\n{res['passed']}/{res['total']} — {res['verdict']}  ({res['calls']} calls, {res['secs']}s)")


if __name__ == "__main__":
    main()
