"""Run N rounds of a world with a real AI (a model file, a server, or a person at the relay) and keep EVERYTHING.
Nothing is edited between rounds: a refused or failed round stays as it happened.
  python tools/run10.py examples/ashfall_hunter/background.md runs/ashfall_r10_inputs.txt OUT --gguf FILE.gguf
  python tools/run10.py ... OUT --relay        (a person answers each question through tools/relay.py)
"""
import argparse, hashlib, json, os, pathlib, sys, time, traceback
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from localgm import backend, flow
from localgm.__main__ import header
from localgm.store import Game


class Recorder:
    """Wraps any AI: logs every request and reply in full, in order."""
    def __init__(self, inner, out: pathlib.Path):
        self.inner, self.out, self.n = inner, out, 0
        (out / "calls").mkdir(parents=True, exist_ok=True)
        self.systems = {}

    def ask(self, system, user, schema=None, max_tokens=None):
        self.n += 1
        sid = hashlib.sha1(system.encode()).hexdigest()[:8]
        self.systems.setdefault(sid, system)
        t0 = time.time()
        err = None
        try:
            reply = self.inner.ask(system, user, schema, max_tokens=max_tokens)
        except Exception as e:                 # the AI failed to produce usable output: keep that fact
            reply, err = None, f"{type(e).__name__}: {e}"
        rec = {"n": self.n, "system_id": sid, "user": user, "reply": reply, "error": err, "secs": round(time.time() - t0, 1),
               "max_tokens": max_tokens, "wants": "json" if schema is not None else "text"}
        (self.out / "calls" / f"{self.n:04d}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        (self.out / "systems").mkdir(exist_ok=True)
        (self.out / "systems" / f"{sid}.txt").write_text(system, encoding="utf-8")
        if err:
            raise ValueError(err)
        return reply


class Relay:
    """A person answers: each request becomes a file; the run waits for the matching reply file."""
    def __init__(self, folder: pathlib.Path):
        self.f = folder / "relay"
        self.f.mkdir(parents=True, exist_ok=True)
        self.n = 0

    def ask(self, system, user, schema=None, max_tokens=None):
        self.n += 1
        form = system.split("REPLY with one JSON object only:")[1] if "REPLY with one JSON object only:" in system else ""
        req = {"n": self.n, "system": system, "form": form, "user": user, "wants": "json" if schema is not None else "text", "max_tokens": max_tokens}
        (self.f / f"req_{self.n:04d}.json").write_text(json.dumps(req, ensure_ascii=False), encoding="utf-8")
        rep = self.f / f"rep_{self.n:04d}.json"
        while not rep.exists():
            time.sleep(0.5)
        time.sleep(0.2)
        return json.loads(rep.read_text(encoding="utf-8"))["reply"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("background"); ap.add_argument("inputs"); ap.add_argument("out")
    ap.add_argument("--gguf"); ap.add_argument("--ctx", type=int, default=16384); ap.add_argument("--relay", action="store_true")
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    inner = Relay(out) if a.relay else backend.LlamaCpp(a.gguf, a.ctx, temperature=0.3, max_tokens=1500)
    ai = Recorder(inner, out)
    game = Game.new(out / "saves", "run", pathlib.Path(a.background).read_text(encoding="utf-8"))
    inputs = [l for l in pathlib.Path(a.inputs).read_text(encoding="utf-8").splitlines() if l.strip()]
    log = open(out / "rounds.jsonl", "w", encoding="utf-8")
    t0 = time.time()
    try:
        flow.intake(game.world, ai)
        game.save()
        intake_note = "intake done"
    except Exception as e:
        intake_note = f"intake FAILED: {type(e).__name__}: {e}"
    log.write(json.dumps({"intake": intake_note, "calls": ai.n, "secs": round(time.time() - t0)}) + "\n"); log.flush()
    for i, text in enumerate(inputs, 1):
        before_round, c0, t1 = game.world.round, ai.n, time.time()
        rec = {"round_attempt": i, "input": text, "header_before": header(game.world)}
        try:
            turn = flow.run_turn(game.world, ai, text)
            game.log({"input": text, "sort": turn.sort, "lines": turn.lines, "facts": turn.facts, "events": turn.events, "prose": turn.prose})
            game.save()
            rec |= {"ok": True, "sort": turn.sort, "ran": turn.ran, "lines": turn.lines, "facts": turn.facts, "events": turn.events,
                    "prose": turn.prose, "header_after": header(game.world), "halt": turn.halt}
        except BaseException as e:
            rec |= {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(limit=3)}
        rec |= {"ai_calls": ai.n - c0, "secs": round(time.time() - t1)}
        log.write(json.dumps(rec, ensure_ascii=False) + "\n"); log.flush()
    log.close()
    (out / "DONE").write_text("done")


if __name__ == "__main__":
    main()
