"""Runs a turn exactly as engine/steps.yaml says. The AI fills a form; the program validates it and commits it.

Nothing about the order or conditions of a turn lives here: run_turn walks the YAML. This file holds only
what each named `program` does, and how a step's prompt is built.
"""
from __future__ import annotations
import json, os, pathlib, re, sys, time
from types import SimpleNamespace
import yaml

from . import combat, mechanics as M, rules, schema
from .state import World, WriteRefused, at_minutes, dates_in

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
        self.rolled = 0                 # questions the dice settled this turn
        self.settled = 0                # questions the records settled (no dice)
        self.ask_rounds = 0             # times the reaction asked for more results before deciding
        self.ended_now = False          # an ending was reached in this turn: the last recap follows
        self.checkpoint_due = (world.round + 1) % 10 == 0     # this turn closes a tenth round
        self.injury_owed = 0            # lasting injuries the player must be given (named by the AI, recorded by the program)
        self.shape = None               # SHORT | LONG | CHAIN when a new offer's shape was rolled this turn
        self.hidden: list[str] = []     # records changed that the narrator must not be told about
        self.resolved: dict[str, dict] = {}   # results of this turn, by normalised key: {positive, label}
        self.governs: dict[str, str] = {}     # record path -> the result that decides it
        self.events: list[dict] = []          # what changed, why, and by what channel (goes to the journal)

    def module(self, name: str) -> bool:
        return rules.module(self.world, name)

    @property
    def pending(self):
        return self.world.tree.get("pending")


# ---------- what the AI is shown ----------

def brief(world: World) -> str:
    """Every record the AI may cite, with its exact path, so it never has to guess how a path is spelled."""
    t = world.tree
    out = [f"PLACE {t['world_state']['location']} · {t['world_state']['time'].get('daypart')}",
           "RECORDS YOU CAN CITE: write these exact paths in `cites` / `governs` (add .field to go deeper, e.g. npcs.<id>.state.status):"]
    for kind in ("npcs", "factions", "quests", "active_world_pressures", "rights_obligations"):
        for rid, rec in (t.get(kind) or {}).items():
            if isinstance(rec, dict):
                what = rec.get("job") or rec.get("objective") or rec.get("role") or (rec.get("state") or {}).get("status") or rec.get("name") or ""
                fields = ",".join(k for k, v in rec.items() if v not in (None, "", [], {}) and k not in ("name",))[:70]
                out.append(f"{kind}.{rid} — {rec.get('name', rid)}: {str(what)[:90]}  [{fields}]")
    if t.get("locations"):
        out.append("PLACES (ids for locations.<id> and for moved_to): " + ", ".join(t["locations"]))
    out.append("YOUR PLAYER'S OWN RECORD: player.skills, player.equipment, player.condition, player.money, player.knowledge")
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
    others = [f"{rid}: {r.get('name')}" + (f" ({(r.get('state') or {}).get('status')})" if (r.get("state") or {}).get("status") else "")
              for rid, r in (t.get("npcs") or {}).items() if rid not in world.actors_here()] if secret else []
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


def open_items(w: World) -> str:
    """Everything still open, for the ten-round check: quests, rights, payoffs, threads, trackers, clocks."""
    t, out = w.tree, []
    for q, r in (t.get("quests") or {}).items():
        if isinstance(r, dict) and r.get("status") not in rules.TERMINAL:
            out.append(f"quest {q} [{r.get('status')}]: {r.get('objective', '')[:160]}")
    for k, r in (t.get("rights_obligations") or {}).items():
        st = (r.get("state") or {}) if isinstance(r, dict) else {}
        if str(st.get("status", "")).startswith(("active", "open")) or not st.get("status"):
            out.append(f"right {k}: {json.dumps(r, ensure_ascii=False)[:260]}")
    for k in ("pending_payoffs", "unresolved_consequences", "active_commitments"):
        for item in t.get(k) or []:
            out.append(f"{k[:-1] if k.endswith('s') else k}: {json.dumps(item, ensure_ascii=False)[:200]}")
    for k, r in (t.get("development_threads") or {}).items():
        out.append(f"thread {k}: {json.dumps(r, ensure_ascii=False)[:200]}")
    for k, r in (t.get("trackers") or {}).items():
        out.append(f"tracker {k}: {r.get('name')} {r.get('current')}/{r.get('target')}")
    return "OPEN ITEMS:\n" + ("\n".join(out) or "none")


def inputs(step: dict, turn: Turn) -> str:
    w, parts, scene_done = turn.world, [], False
    for name in step["input"]:
        if name == "player_who":
            ident = (w.player.get("identity") or {})
            parts.append(f"THE PLAYER CHARACTER (\"you\" in the telling): {ident.get('name', 'the player')}, {w.player.get('job') or w.player.get('archetype') or ''}. "
                         f"{w.player.get('character', '')} Every other name is someone else; they are not \"you\".".replace("  ", " "))
        elif name == "player_text":
            parts.append(f"PLAYER: {turn.text}")
        elif name in ("place", "actors_present"):
            if not scene_done:               # the place and who is in it are shown once, however many names ask for them
                parts.append(scene(w, secret=step["id"] != "tell" and step["id"] != "audit"))
                scene_done = True
        elif name == "records_in_play":
            parts.append(brief(w))
        elif name == "pressures":
            parts.append(pressures(w))
        elif name == "pending":
            if turn.pending:
                parts.append("WAITING FOR THE PLAYER'S GO-AHEAD: " + turn.pending["ask"]
                             + "\n(kind=confirm if the player agrees to exactly this; anything else drops it)")
        elif name == "ending_conditions":
            st = w.tree.get("ending_state") or {"closed": []}
            parts.append("ENDING CONDITIONS (id: text) — closed: " + ", ".join(st["closed"]) + "\n"
                         + "\n".join(f"{i}: {t}" for i, t in rules.ending_list(w).items()))
        elif name == "player_brief":          # what the world step must know about the player to decide fairly
            p, cash = w.player, w.cash()
            hp = (p.get("condition") or {}).get("hp")
            lvl, mp = rules.level(w), rules.mp_max(w)
            parts.append("THE PLAYER CHARACTER NOW: " + json.dumps({
                "name": (p.get("identity") or {}).get("name"), "level": lvl, "hp": f"{hp}/{rules.hp_max(w)}",
                **({"mp": f"{rules.mp_now(w)}/{mp}"} if mp else {}), "cash": " ".join(str(x) for x in cash if x != ""),
                "carrying": [e.get("name") for e in p.get("equipment") or [] if isinstance(e, dict)],
                "skills": {k: f"{v.get('class')} {v.get('tier')}" for k, v in (p.get("skills") or {}).items() if isinstance(v, dict)},
                "injuries": [i.get("injury") for i in (p.get("condition") or {}).get("injuries") or [] if isinstance(i, dict)],
                "resources": {k: (v.get("count") if v.get("tracking") == "exact" else v.get("usage_die")) for k, v in (p.get("resources") or {}).items() if isinstance(v, dict)},
                "knows": list(((p.get("knowledge") or {}).get("facts") or {}))}, ensure_ascii=False))
        elif name == "player_state":
            p = w.player
            parts.append("YOU (the player character): " + json.dumps(
                {k: p.get(k) for k in ("identity", "skills", "condition", "equipment", "money", "fighting_style")},
                ensure_ascii=False))
        elif name == "active_quests":
            qs = [f"{q}: {r.get('objective', '')[:140]} [{r.get('status', '')}]" for q, r in (w.tree.get("quests") or {}).items()
                  if isinstance(r, dict)]
            parts.append("QUESTS:\n" + ("\n".join(qs) or "none"))
        elif name == "open_items":
            parts.append(open_items(w))
        elif name == "story_so_far":
            qs = [f"{q}: {r.get('objective', '')[:120]} [{r.get('status')}]" for q, r in (w.tree.get("quests") or {}).items() if isinstance(r, dict)]
            parts.append("HOW IT WENT:\n" + rules.ledger_text(w, 25) + "\n\nQUESTS:\n" + "\n".join(qs) + "\n\n" + brief(w))
        elif name == "resolved_facts":
            parts.append("ALREADY RESOLVED IN THIS CAMPAIGN (binding; not rolled again unless something material changed):\n" + rules.ledger_text(w))
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
    sch, errs = schema.cap_arrays(step["output"]), []
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
        if isinstance(out, dict) and out.get("asks") and "asks" in sch.get("properties", {}):      # asking first: nothing is decided yet, so nothing is required
            out.setdefault("minutes", 0)
            out.setdefault("ops", [])
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


def addressed(world: World, text: str) -> list[str]:
    """Present people the player's words name (any word of their name, 3+ letters)."""
    low = text.lower()
    return [rid for rid, r in world.actors_here().items()
            if any(len(w) >= 3 and re.search(r"\b" + re.escape(w) + r"\b", low) for w in str(r.get("name", "")).lower().split())]


def player_sheet(world: World) -> str:
    """What the player's character has, knows and is working on: the records a retrieval answers from."""
    p = world.player
    mine = {k: p.get(k) for k in ("identity", "skills", "condition", "equipment", "money", "item_points", "resources", "knowledge", "fighting_style", "routines") if k in p}
    quests = "\n".join(f"{q}: {r.get('objective', '')[:160]} [{r.get('status')}]" for q, r in (world.tree.get("quests") or {}).items()
                       if isinstance(r, dict) and r.get("status") in ("available", "active", "completed", "failed", "abandoned", "blocked"))
    return "THE PLAYER CHARACTER'S RECORDS (answer only from these and from what the scene shows):\n" + json.dumps(mine, ensure_ascii=False) + "\nQUESTS:\n" + (quests or "none")


QUIET = ("fast", "retrieval", "continuation")


def h_route(turn: Turn, out: dict):
    if out["kind"] == "confirm" and not turn.pending:     # nothing was offered: a "confirm" would skip every step and the world would not be told
        raise M.RuleError("nothing is waiting for the player's confirmation, so kind 'confirm' is wrong. Sort what the player does: "
                          "fast, loop, retrieval or continuation (name the steps whose trigger fired)")
    note = str(out.get("note") or "").strip()
    if out["kind"] in QUIET and not note:                 # the sorter's decision is carried to the telling, so it must be written down
        raise M.RuleError(f"kind '{out['kind']}' needs `note`: " + {"fast": "what simply happens", "retrieval": "the answer, from the records",
                                                                      "continuation": "what carries on and for how long"}[out["kind"]])
    steps = list(dict.fromkeys(out.get("steps", [])))      # a step named twice runs once
    # Someone else is affected (section 6) whenever the player names a person who is here: that is never a fast action.
    if addressed(turn.world, turn.text) and out["kind"] in QUIET:
        out = {**out, "kind": "loop"}
        if "react" not in steps:
            steps.append("react")
    # Carrying on takes time and the world keeps moving: the world step runs (minutes, dues, who answers) whatever the sorter wrote.
    if out["kind"] == "continuation" and "react" not in steps:
        steps.append("react")
    out = {**out, "steps": steps}
    turn.sort = out
    if note and out["kind"] in QUIET:
        turn.facts.append(f"THE GM'S DECISION (from sorting; tell it, add nothing that changes the world): {note}")
    if out["kind"] == "retrieval":
        turn.facts.append(player_sheet(turn.world))
    if turn.pending and out["kind"] != "confirm":
        turn.world.tree.pop("pending", None)          # the player changed their mind: dropped at no cost
        turn.facts.append("The earlier risky action was dropped; nothing was rolled.")


def _bind(turn: Turn, key: str, e: dict, governs: list[str]) -> None:
    turn.resolved[key] = {"positive": e["positive"], "label": e["outcome"]}
    for g in governs or e.get("governs") or []:
        turn.governs[rules.canon_path(g)] = key


def h_roll(turn: Turn, out: dict):
    dec = out.get("decision")
    if dec and str(dec.get("question", "")).strip():      # the decision gate: the player decides, nothing is rolled or recorded
        turn.halt = True
        turn.prose = (dec["question"].strip() + "\n" + "\n".join(f"{i}. {o}" for i, o in enumerate(dec["options"], 1))
                      + "\n(Nothing has happened yet. Say what you do; you are not limited to these.)")
        turn.world.tree.pop("pending", None)
        return
    if out["verdict"] == "ask":              # the setup depends on answers the AI does not have yet
        if not out.get("asks"):
            raise M.RuleError("verdict 'ask' needs the questions in 'asks'")
        if turn.ask_rounds >= 4:
            raise M.RuleError("no more questions this turn: give a verdict with the results you have")
        turn.ask_rounds += 1
        do_asks(turn, out["asks"])
        return "ask_again"
    rules.check_cites(turn.world, out.get("cites", []))
    if out["verdict"] in ("impossible", "certain") and not out.get("cites"):
        raise M.RuleError("an impossible or certain verdict must cite the records that settle it (cites)")
    if out["verdict"] == "impossible":
        turn.facts.append(f"IMPOSSIBLE: {out.get('reason', '')}")
        return
    if out["verdict"] == "certain":
        if str(out.get("reason") or "").strip():        # the judge's reason is part of what the next call must know
            turn.results.append(f"SETTLED (no roll): {out['reason'].strip()}")
        return
    r = out.get("roll")
    if not r:
        raise M.RuleError("verdict 'roll' needs a roll form")
    st = r["stakes"]
    key = rules.norm(r["subject"])
    prev = rules.frozen(turn.world, key)
    if prev and not str(r.get("changed", "")).strip():
        # an unchanged repeat is not rolled again (I10): the earlier result stands
        _bind(turn, key, prev, r.get("governs"))
        turn.results.append(f"RESULT {prev['outcome']} (already resolved in round {prev['round']}; nothing was rolled again): {prev['text']}")
        return
    if st.get("harm", "none") in ("loss", "severe") and st.get("source") not in combat.DAMAGE:
        raise M.RuleError(f"harm '{st.get('harm')}' needs stakes.source from {sorted(combat.DAMAGE)}")
    if r.get("cast"):
        rules.can_cast(turn.world, r["cast"])        # RuleError sends the AI back: it cannot cast that now
    cap, tool, diff, _ = rules.roll_inputs(turn.world, r)
    pct = M.odds(cap, tool, diff)
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
    cap, tool, diff, notes = rules.roll_inputs(w, r)
    if r.get("cast"):
        cost = rules.cast(w, r["cast"])
        notes.append(f"{r['cast']} costs {cost} MP ({rules.mp_now(w)} left)")
    res = M.check(cap, tool, diff)
    _roll_lines(turn, res, cap, tool, diff)
    if notes:
        turn.lines.append("Gear: " + "; ".join(notes))
    win = res["success"]
    text = st["success"] if win else st["failure"]
    turn.results.append(f"RESULT roll {'SUCCESS' if win else 'FAILURE'}: {text}")
    key = rules.norm(r["subject"])
    _bind(turn, key, rules.record_result(w, key, "roll", "SUCCESS" if win else "FAILURE", win, text, r.get("governs", [])), r.get("governs"))
    skill = r.get("skill")
    if skill and skill in (w.player.get("skills") or {}):
        gain = w.credit_skill(skill, win, diff, r.get("challenge"))
        if gain:
            turn.facts.append(f"The player's {skill} gained experience.")
    if win and r.get("challenge") and r.get("scope"):
        msg = rules.award_xp(w, r["challenge"], r["scope"])
        if msg:
            rules.add_history(w, f"Event in round {w.round + 1} paid XP (scope {r['scope']}).")
            turn.facts.append(msg)
    harm = st.get("harm", "none")
    if not win and harm in ("loss", "severe"):
        raw = []
        for _ in range(2 if harm == "severe" else 1):
            n, how = combat.damage_roll(st["source"])
            raw.append(n)
            turn.lines.append(f"Damage: {how} − soak {st.get('soak', 0)}")
        h = w.hurt(raw, st.get("soak", 0), "player")
        turn.lines.append(f"HP {h['before']} → {h['hp']}" + (f" — {h['state']}" if h["state"] != "standing" else ""))
        turn.injury_owed += bool(h["lasting_injury"])
        turn.results.append(f"RESULT harm: the player is {h['state']}, HP {h['hp']}." + (" A lasting injury follows." if h["lasting_injury"] else ""))
    elif not win and harm == "setback":
        turn.results.append("RESULT: position worsens; no HP lost.")


def h_combat(turn: Turn, out: dict):
    turn.in_fight = True
    lines, facts, owed = combat.run(turn.world, out)
    turn.injury_owed += owed
    turn.lines += lines
    turn.results += ["RESULT " + f for f in facts]


_WH = re.compile(r"^\s*(what|who|whom|whose|where|when|why|how|which)\b", re.I)
_OBV = re.compile(r"^\s*(YES|NO)\b[\s:\-–—]*(.*)$", re.I | re.S)


def ask_problem(a: dict) -> str | None:
    """An open question is yes/no; a rolled one has every likelihood point resting on a stated fact (section 11)."""
    if _WH.match(a["question"]) or not a["question"].strip().endswith("?"):
        return f"question {a['question']!r} must be a yes/no question ending in '?'; what the records already say is not rolled"
    obv = str(a.get("obvious", "none")).strip()
    if obv.lower() != "none" and not _OBV.match(obv):
        return f"question {a['question']!r}: 'obvious' is 'none' or 'YES - why' / 'NO - why'"
    if obv.lower() == "none" and a["likelihood"] and not (a.get("for") or a.get("against")):
        return f"question {a['question']!r}: a likelihood of {a['likelihood']:+d} needs the fact behind it in 'for' or 'against'"
    return None


def do_asks(turn: Turn, asks: list[dict]) -> None:
    """Settle what has an obvious answer; roll only what could honestly go either way."""
    w = turn.world
    bad = [p for p in map(ask_problem, asks) if p]
    for a in asks:
        try:
            rules.check_cites(w, a.get("cites", []))
        except M.RuleError as e:
            bad.append(str(e))
    if bad and not turn.final:
        raise M.RuleError("\n- " + "\n- ".join(bad))
    for a in asks:
        if ask_problem(a):
            continue                          # refused twice: not rolled, not recorded
        try:
            rules.check_cites(w, a.get("cites", []))
        except M.RuleError:
            continue
        key = rules.norm(a["question"])
        prev = rules.frozen(w, key)
        if prev and not str(a.get("changed", "")).strip():
            _bind(turn, key, prev, a.get("governs"))
            turn.results.append(f"RESULT question '{a['question']}' → {prev['outcome']} (already answered in round {prev['round']}; not asked again)")
            continue
        obv = _OBV.match(str(a.get("obvious", "none")).strip())
        if obv:                               # the obvious answer stands; no dice
            yes = obv.group(1).upper() == "YES"
            label = f"{'YES' if yes else 'NO'} (settled)"
            turn.settled += 1
            turn.results.append(f"RESULT question '{a['question']}' → {label}: {obv.group(2).strip()}")
            _bind(turn, key, rules.record_result(w, key, "settled", label, yes, a["question"], a.get("governs", [])), a.get("governs"))
            continue
        r = M.ask(a["likelihood"])
        turn.rolled += 1
        d1, d2 = r["dice"]
        turn.lines.append(f"ask 2d10: {d1}+{d2} {r['likelihood']:+d} = {r['total']} → {r['band']} ({a['question']})")
        turn.results.append(f"RESULT question '{a['question']}' → {r['band']}")
        _bind(turn, key, rules.record_result(w, key, "ask", r["band"], r["band"].startswith("YES"), a["question"], a.get("governs", [])), a.get("governs"))


def h_ask_roll(turn: Turn, out: dict):
    do_asks(turn, out["asks"])


def _typed_changes(trial: World, turn: Turn, out: dict, new_fills: list[str], facts: list[str], lines: list[str]) -> list[str]:
    """Money, clocks, rest, growth, item points: the AI states what happened, the program does the rest."""
    faults = []
    if out.get("moved_to"):                  # where the player stands when the action ends; the place must be in the records
        dest = str(out["moved_to"]).strip()
        if dest not in (trial.tree.get("locations") or {}):
            faults.append(f"moved_to {dest!r} is not a place in the records ({sorted(trial.tree.get('locations') or {})}); "
                          "a place first entered gets a locations record with its challenge band, written in ops")
        else:
            trial.tree["world_state"]["location"] = dest
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
    try:
        for c in out.get("companion_join", []):
            facts.append(rules.set_companion(trial, c["id"], c["level"], True))
        for cid in out.get("companion_leave", []):
            facts.append(rules.set_companion(trial, cid, None, False))
        for h in out.get("heal", []):
            line, fact = rules.heal_target(trial, h["who"], h["source"])
            lines.append(line); facts.append(fact)
        for t in out.get("treat", []):
            facts.append(rules.treat_injury(trial, t["action"], t["injury"], t.get("deep", False)))
        for d in out.get("draw", []):
            lines.append(rules.draw(trial, d["resource"], d.get("amount", 1)))
        for r_ in out.get("resupply", []):
            facts.append(rules.resupply(trial, r_["resource"], r_.get("die"), r_.get("count")))
        if out.get("entitlement"):
            facts.append(rules.spend_entitlement(trial, out["entitlement"]))
        if out.get("item_points_gain"):
            facts.append(rules.gain_entitlement(trial, out["item_points_gain"]))
    except M.RuleError as e:
        faults.append(f"item points: {e}")
    return faults


_ACTOR = re.compile(r"^(npcs|factions)\.([^.]+)")


def _hidden_from_narrator(turn: Turn, path: str) -> bool:
    """What the player has learned (discovered information, their own record) the narrator may tell.
    What happens to people who are not here, and what is hidden, it may not (I5, I9)."""
    if ".discovered_information" in path or path.startswith("player."):
        return False
    if rules.HIDDEN_PATH.search(path):
        return True
    m = _ACTOR.match(path)
    if not m:
        return False
    return m.group(1) == "factions" or m.group(2) not in turn.world.actors_here()


def _record_lines(turn: Turn, ops: list[dict]) -> None:
    """What the narrator may be told was recorded. Hidden records are kept from it (I5, I9)."""
    for op in ops:
        v = json.dumps(op.get("value"), ensure_ascii=False) if "value" in op else ""
        line = f"RECORDED {op['op']} {op['path']} {v[:160]}"
        (turn.hidden if _hidden_from_narrator(turn, op["path"]) else turn.facts).append(line)


def _spell_paths(ops: list[dict]) -> None:
    """'npc.hobb_marren.state' and 'person/hobb_marren/drives' are spellings of npcs.hobb_marren…; the program writes them its way."""
    for o in ops:
        if isinstance(o, dict) and isinstance(o.get("path"), str):
            o["path"] = rules.canon_path(o["path"])


def h_commit(turn: Turn, out: dict):
    """D: validate everything on a copy; commit all of it or none of it."""
    _spell_paths(out.get("ops") or [])
    if out.get("asks"):                      # the AI wants more results before it decides: ask, answer, ask again
        if turn.ask_rounds >= 4:
            raise M.RuleError("no more questions this turn: decide with the results you have (asks must be empty)")
        turn.ask_rounds += 1
        do_asks(turn, out["asks"])
        return "ask_again"
    w, new_fills, facts, lines = turn.world, [], [], []
    report = str(out.get("report") or "").strip()
    if len(report) < 5:
        raise M.RuleError("`report` is missing: say in plain sentences what happened in the world during this action, who did what and why, "
                          "limited to what the player could see, hear or learn. The telling is built from it.")
    bad = rules.leaks(report, rules.secret_terms(w, turn.text + " " + " ".join(turn.results + turn.facts)))
    if bad:
        raise M.RuleError(f"your report names {bad}, which the player has not learned. Leave them out of the report (record them in ops).")
    trial = w.clone()
    faults = rules.op_faults(w, out["ops"], turn.resolved, turn.governs)
    now_ops = [o for o in out["ops"] if o["op"] != "plan"]
    plan_ops = [o for o in out["ops"] if o["op"] == "plan"]      # a plan's "in N minutes" counts from the end of the action
    faults += trial.commit(now_ops)
    faults += _typed_changes(trial, turn, out, new_fills, facts, lines)
    minutes = int(out["minutes"]) if turn.dues_pass == 1 else 0
    if not faults:
        facts += rules.rest(trial, out.get("rest", "none"), minutes)
        trial.advance(minutes)
        faults += trial.commit(plan_ops)
        for e in trial.down_checks():            # down and untreated for an hour
            d1, d2 = e["dice"]
            lines.append(f"{e['who']} down for an hour — 2d10: {d1}+{d2} → {'wakes at 1 HP' if e['woke'] else 'dies'}")
            facts.append(f"{e['who']} {'came round at 1 HP' if e['woke'] else 'died of the untreated wound'}.")
        if out.get("rest") == "sleep" or out.get("boundary", "none") != "none":
            facts += rules.growth_boundary(trial, out.get("class_sources") or {})
        facts += rules.quest_xp(trial, w.tree)
    if faults:
        raise M.RuleError("nothing was recorded. Fix:\n- " + "\n- ".join(faults))
    tl, tf = rules.temper_new(w.tree, trial.tree)
    lines += tl
    facts += tf
    days = trial.time["day_index"] - w.time["day_index"]
    w.tree = trial.tree
    turn.fills = new_fills
    for p, d in turn.dues:
        w.clear_due(p, d)
    _record_lines(turn, out["ops"])
    _events(turn, out["ops"])
    turn.facts.append("WHAT HAPPENED (the GM's account of the accepted events; tell it, add nothing that changes the world): " + report)
    turn.facts += facts
    turn.lines += lines
    if out.get("money"):
        turn.facts.append(f"RECORDED cash {out['money']:+d}")
    if days:
        turn.facts.append(f"{days} midnight(s) passed")
    if turn.dues_pass == 1 and (w.due() or turn.fills):      # something fell due during this action
        turn.dues_pass = 2
        return "again"


def h_shape_roll(turn: Turn, out: dict):
    """A new generated offer: the program rolls its shape (1d10: 1-7 SHORT, 8-9 LONG, 10 CHAIN)."""
    if not out["new_offer"]:
        return
    n = M.roll(1, 10)[0]
    turn.shape = "SHORT" if n <= 7 else "LONG" if n <= 9 else "CHAIN"
    line = f"offer shape 1d10: {n} → {turn.shape}"
    if turn.shape == "CHAIN":
        m = M.roll(1, 4)[0]
        line += f" · first child 1d4: {m} → {'SHORT' if m <= 3 else 'LONG'}"
    turn.lines.append(line)
    turn.results.append("RESULT " + line + ". Write the new quest with exactly this shape.")


def _events(turn: Turn, ops: list[dict]) -> None:
    for op in ops:
        e = {"round": turn.world.round + 1, "change": f"{op['op']} {op['path']}", "because": op.get("because", ""),
             "requires": op.get("requires"), "channel": op.get("channel", ""), "action": turn.text}
        turn.events.append({k: v for k, v in e.items() if v})


def h_commit_ops(turn: Turn, out: dict):
    _spell_paths(out.get("ops") or [])
    w = turn.world
    trial = w.clone()
    faults = rules.op_faults(w, out["ops"], turn.resolved, turn.governs)
    faults += trial.commit(out["ops"])
    if not faults and turn.shape:
        new = [q for q in (trial.tree.get("quests") or {}) if q not in (w.tree.get("quests") or {})]
        if not new:
            faults.append(f"a new {turn.shape} offer was rolled; write it")
        elif trial.tree["quests"][new[0]].get("type") != turn.shape:
            faults.append(f"the rolled shape is {turn.shape}; the new quest's type must be exactly that")
    if faults:
        raise M.RuleError("nothing was recorded. Fix:\n- " + "\n- ".join(faults))
    xp = rules.quest_xp(trial, w.tree)
    tl, tf = rules.temper_new(w.tree, trial.tree)
    w.tree = trial.tree
    _record_lines(turn, out["ops"])
    _events(turn, out["ops"])
    turn.facts += xp + tf
    turn.lines += tl


def h_record_injury(turn: Turn, out: dict):
    if out["home"] not in rules.HOMES or len(out["effect"].strip()) < 8:
        raise M.RuleError(f"home must be one of {rules.HOMES} and effect must say exactly what changes")
    inj = turn.world.player.setdefault("condition", {}).setdefault("injuries", [])
    for _ in range(turn.injury_owed):
        inj.append({"injury": out["injury"], "home": out["home"], "effect": out["effect"]})
        break
    turn.injury_owed = 0
    turn.facts.append(f"The player now has a lasting injury: {out['injury']} ({out['effect'].strip()}).")


def h_ending(turn: Turn, out: dict):
    trial = turn.world.clone()
    facts = rules.ending_update(trial, out["met"], out["closed"])
    turn.world.tree = trial.tree
    turn.facts += facts
    turn.ended_now = bool((turn.world.tree.get("ending_state") or {}).get("met"))


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
    prose = clean(out)
    echo = re.sub(r"\W+", " ", turn.text).strip().lower()
    if len(echo) >= 25 and echo in re.sub(r"\W+", " ", prose).lower():
        raise M.RuleError("your text repeats the player's own words. Tell what happens as a result: what the world and the people in it do")
    known = turn.text + " " + " ".join(turn.results + turn.facts)
    terms = rules.secret_terms(turn.world, known)
    bad = rules.leaks(prose, terms)
    if bad and not turn.final:
        raise M.RuleError(f"your text names {bad}, which the player has not learned. Tell it without them.")
    turn.prose = rules.redact(prose, terms) if bad else prose


def h_epilogue(turn: Turn, out: str):
    turn.prose = (turn.prose + "\n\n" + clean(out)).strip()


def h_audit(turn: Turn, out: dict):
    if not out["ok"]:
        turn.facts.append("FIX IN THE RETELLING: " + "; ".join(out.get("problems", [])))
        return "retell"


HANDLERS = {"route": h_route, "roll": h_roll, "roll_pending": h_roll_pending, "combat": h_combat, "ask_roll": h_ask_roll,
            "commit": h_commit, "shape_roll": h_shape_roll, "commit_ops": h_commit_ops, "record_injury": h_record_injury,
            "ending": h_ending, "epilogue": h_epilogue, "show": h_show, "audit": h_audit}


# ---------- the loop ----------

def _when(expr: str, turn: Turn) -> bool:
    if expr == "always":
        return True
    env = {"sort": SimpleNamespace(**{"kind": "", "steps": [], **turn.sort}), "turn": turn}
    return bool(eval(expr, {"__builtins__": {}}, env))


class TurnFailed(Exception):
    """A step the turn cannot do without could not be recorded. Nothing of the turn is kept and the round does not advance."""


def execute(llm, step: dict, turn: Turn):
    """One step: show, ask, hand to its handler; a refusal sends the AI back once with the reason."""
    if "dues_fired" in step.get("input", []):
        turn.dues = turn.world.due()
    if step.get("ai") is False:
        return HANDLERS[step["program"]](turn, None)
    extra = ""
    for attempt in range(2):
        turn.final = attempt == 1
        try:
            out = run_step(llm, step, turn, extra)
        except ValueError as e:                  # two replies in a row that were not a usable form
            if step.get("optional"):
                turn.facts.append(f"(Step {step['id']} could not be recorded; narrate none of its changes.)")
                return
            raise TurnFailed(f"The AI could not give a usable answer for the '{step['id']}' step after two tries ({str(e)[:240]}). "
                             "Nothing was recorded and the round did not advance; send the action again.") from None
        try:
            return HANDLERS[step["program"]](turn, out)
        except M.RuleError as e:
            extra = f"\n\nThe program refused your reply: {e}\nReply again, fixed."
        except (KeyError, IndexError, TypeError, AttributeError, ValueError) as e:      # an id or shape in the answer that the records do not have
            extra = (f"\n\nThe program could not use your reply: {type(e).__name__}: {e}. Something it names does not exist or has the wrong shape. "
                     "Use the ids shown in the records (npc ids like nadia_voss, 'player', place ids), not names or descriptions.\nReply again, fixed.")
    if step.get("optional"):                 # a check or a recap: the turn stands without it
        turn.facts.append(f"(Step {step['id']} could not be recorded; narrate none of its changes.)")
        return
    raise TurnFailed(f"The AI could not give a usable answer for the '{step['id']}' step after two tries ({extra.strip().splitlines()[0][:200]}). "
                     "Nothing was recorded and the round did not advance; send the action again.")


def _check_dates(world: World, a: dict) -> None:
    """Every date the note writes must come back as a due on that day (and time, when written). The program reads the calendar."""
    note = world.get(a["id"] + ".plan.text") or ""
    base = world.time["day_index"]
    got = []
    for d in a["dues"]:
        try:
            got.append((base + int(d["day_offset"]), at_minutes(d["at"])))
        except (ValueError, KeyError):
            pass
    for day, clock_ in dates_in(note, world.time, world.cal):
        if not any(g[0] == day and (clock_ is None or g[1] == clock_) for g in got):
            when = f"day_offset {day - base}" + (f" at {clock_ // 60:02d}:{clock_ % 60:02d}" if clock_ is not None else "")
            raise ValueError(f"the note gives a date that is {when}; no due of yours is on it")


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
                        _check_dates(world, a)
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


class ScenarioEnded(Exception):
    pass


def run_turn(world: World, llm, text: str, merge_questions: bool = False, check_telling: bool = True) -> Turn:
    """Runs on a copy of the world; the real one changes only if the whole turn completes.
    merge_questions: the world step asks its open questions itself instead of a separate call first (one call fewer per turn).
    check_telling: the audit call after the telling (off = one call fewer per turn)."""
    if (world.tree.get("ending_state") or {}).get("met"):
        raise ScenarioEnded("The scenario has ended.")
    work = world.clone()
    turn = Turn(work, text)
    steps = load_steps()
    byid = {s["id"]: s for s in steps}
    skip = ({"wonder"} if merge_questions else set()) | (set() if check_telling else {"audit"})
    for step in steps:
        if step["id"] in skip or not _when(step["when"], turn):
            continue
        again = None
        for _ in range(8):              # a handler may ask for another pass: more results, a due that fell, a retelling
            again = execute(llm, step, turn)
            turn.ran.append(step["id"])
            if again in ("again", "ask_again"):
                continue
            if again == "retell":
                execute(llm, byid["tell"], turn)
            break
    work.round += 1
    world.tree, world.round = work.tree, work.round
    return turn
