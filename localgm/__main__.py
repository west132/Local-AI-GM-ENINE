"""python -m localgm play <background.md> --game NAME [--url http://localhost:1234/v1 | --gguf FILE]"""
from __future__ import annotations
import argparse, pathlib, sys

from . import backend, clock, flow
from .store import Game


def header(w) -> str:
    t = w.time
    return f"R{w.round} · {t.get('date', '')} {clock.hhmm(t['clock_minutes'])} {t['daypart']} · {w.tree['world_state']['location']}"


def show(turn) -> str:
    w = turn.world
    return "\n".join([header(w), *turn.lines, "", turn.prose,
                      f"Cash: {' '.join(str(x) for x in w.cash() if x != '')}"])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="localgm")
    ap.add_argument("background")
    ap.add_argument("--game", default="game")
    ap.add_argument("--saves", default="saves")
    ap.add_argument("--url"); ap.add_argument("--model", default="")
    ap.add_argument("--gguf"); ap.add_argument("--ctx", type=int, default=8192)
    ap.add_argument("--script", help="file with one player line per turn (non-interactive)")
    a = ap.parse_args(argv)
    ai = backend.OpenAICompat(a.url, a.model) if a.url else backend.LlamaCpp(a.gguf, a.ctx)
    try:
        game = Game.open(a.saves, a.game)
    except FileNotFoundError:
        game = Game.new(a.saves, a.game, pathlib.Path(a.background).read_text(encoding="utf-8"))
        flow.intake(game.world, ai)
        game.save()
    lines = pathlib.Path(a.script).read_text(encoding="utf-8").splitlines() if a.script else None
    print(header(game.world))
    while True:
        try:
            text = (lines.pop(0) if lines else None) if lines is not None else input("> ")
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            break
        if text.strip().lower().startswith("/rewind"):
            game.rewind(int(text.split()[1])); print(header(game.world)); continue
        print(f"> {text}")
        turn = flow.run_turn(game.world, ai, text)
        game.log({"input": text, "sort": turn.sort, "lines": turn.lines, "facts": turn.facts, "events": turn.events, "prose": turn.prose})
        game.save()
        print(show(turn), "\n")


if __name__ == "__main__":
    sys.exit(main())
