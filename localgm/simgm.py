"""A practice GM with no AI: a small rule-based player of the engine's forms.

It reads the same prompts a model reads (the records, the results, the task) and answers the same forms, so it can only do what the prompt lets a reader do.
Used (1) as the "sim" backend, to try the whole app without a model, and (2) by tests that run whole games through the real loop. It is not clever:
it answers plainly and safely; its job is to prove the parts of the system work together."""
from __future__ import annotations
import copy, json, re

RISKY = re.compile(r"\b(climb|jump|leap|pick|force|break|sneak|chase|swim|lift|haggle|persuade|convince|bluff|lie)\b", re.I)
VIOLENT = re.compile(r"\b(attack|kill|hit|stab|shoot|fight|strike)\b", re.I)
WAIT = re.compile(r"^\s*(i\s+)?(wait|rest|sleep|continue|carry on|go on|keep going|stay)\b", re.I)
ASKQ = re.compile(r"^\s*(what|which|who|where|how much|how many|do i|am i|have i|what's)\b", re.I)


def _form(system: str) -> str:
    return system.split("REPLY with one JSON object only:")[1].lstrip() if "REPLY with one JSON object only:" in system else ""


def _second_pass(user: str) -> bool:
    return "ALREADY DONE AND RECORDED" in user


def _line(user: str, prefix: str) -> str:
    m = re.search(r"^" + re.escape(prefix) + r"(.*)$", user, re.M)
    return m.group(1).strip() if m else ""


def _people(user: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(r"^PERSON (\w+): (\{.*\})$", user, re.M):
        try:
            out[m.group(1)] = json.loads(m.group(2)).get("name", m.group(1))
        except json.JSONDecodeError:
            out[m.group(1)] = m.group(1)
    return out


def _places(user: str) -> dict[str, str]:
    """id -> name, from the line 'PLACES (...): id = Name; id = Name'."""
    m = re.search(r"^PLACES \([^)]*\): (.*)$", user, re.M)
    out = {}
    for part in (m.group(1).split("; ") if m else []):
        pid, _, name = part.partition(" = ")
        out[pid.strip()] = name.strip() or pid.strip()
    return out


def _here(user: str) -> str:
    m = re.search(r"^PLACE (\w+) ·", user, re.M)
    return m.group(1) if m else ""


def _addressed(text: str, people: dict[str, str]) -> list[str]:
    low = text.lower()
    return [i for i, n in people.items() if any(len(w) >= 3 and re.search(r"\b" + re.escape(w) + r"\b", low) for w in n.lower().split())]


def _named_place(text: str, places: dict[str, str], here: str) -> str | None:
    """The place whose name the player's words match best (most of its name's words), if at least two words match."""
    low = text.lower()
    words = set(re.findall(r"[a-z]{4,}", low))
    best, score = None, 0.0
    for pid, name in places.items():
        if pid == here:
            continue
        nw = set(re.findall(r"[a-z]{4,}", name.lower()))
        hit = len(nw & words)
        sc = 9 if pid.replace("_", " ") in low else (hit / len(nw) if hit >= 2 else 0)
        if sc > score:
            best, score = pid, sc
    return best


def _results(user: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(r"RESULT question '(.*?)' → (YES|NO)(?:, (AND|BUT))?", user):
        out.append((m.group(1), m.group(2), m.group(3) or ""))
    return out


def _skill(user: str) -> str | None:
    m = re.search(r'"skills": \{"(\w+)"', user)
    return m.group(1) if m else None


class SimGM:
    def __init__(self):
        self.calls = []

    def ask(self, system, user, schema=None, max_tokens=None):
        props = (schema or {}).get("properties", {})
        for field, key in (("title", "premise"), ("groups", "economy"), ("source_abilities", "player"),     # the world-making forms
                           ("start_location", "places"), ("npcs", "cast"), ("quests", "story")):
            if field in props and field in (schema.get("required") or []) and key in GOOD:
                return copy.deepcopy(GOOD[key])
        form = _form(system)
        if not form:
            kind = "epilogue" if "## 21" in system else "tell"
        else:
            kind = next((n for k, n in (("mode:", "gm"), ("kind:", "sort"), ("verdict:", "judge"), ("foes?:", "fight"), ("new_offer:", "offer"), ("injury:", "injury"),
                                         ("met:", "ending"), ("ok:", "audit"), ("actors:", "intake")) if form.startswith(k)), None)
            if kind is None:
                kind = "wonder" if form.startswith("asks:") else "react" if ("minutes:" in form or form.startswith("asks?:")) else \
                       "checkpoint" if "notes?:" in form else "quest"
        self.calls.append(kind)
        return getattr(self, "do_" + kind)(user)

    # ---- the one-form turn: the same plain judgement, asked as one form ----
    def do_gm(self, user):
        text = _line(user, "PLAYER: ")
        results = user.split("RESULTS (decided by the program", 1)[-1].split("\n\n", 1)[0] if "RESULTS (decided by the program" in user else ""
        have = bool(re.search(r"^(RESULT|SETTLED|IMPOSSIBLE)", results, re.M)) or _second_pass(user)
        people, places = _people(user), _places(user)
        if "WAITING FOR THE PLAYER'S GO-AHEAD" in user and re.match(r"\s*(yes|ok|go|do it)", text.lower()):
            return {"mode": "confirm"}
        if not have:
            if VIOLENT.search(text):
                return {"mode": "fight", **self.do_fight(user)}
            if RISKY.search(text):
                j = self.do_judge(user)
                return {"mode": "roll", "cites": j["cites"], "roll": j["roll"]}
            who = _addressed(text, people)[:1]
            if who and not WAIT.match(text):
                return {"mode": "ask", **self.do_wonder(user)}
        self._asked = True                                  # the questions are asked by mode ask, not inside the world reply
        try:
            r = self.do_react(user)
        finally:
            self._asked = False
        r.pop("asks", None)
        scene = self.do_tell(f"WHAT HAPPENED: {r['report']}\n" + user)
        return {"mode": "done", "cites": ["player"], **r, "scene": scene}

    # ---- the steps ----
    def do_sort(self, user):
        text = _line(user, "PLAYER: ")
        people, places = _people(user), _places(user)
        low = text.lower()
        if "WAITING FOR THE PLAYER'S GO-AHEAD" in user and re.match(r"\s*(yes|ok|go|do it)", low):
            return {"kind": "confirm", "steps": []}
        if WAIT.match(text):
            return {"kind": "continuation", "steps": [], "note": "Time passes quietly."}
        steps = []
        if VIOLENT.search(text):
            steps += ["fight", "react"]
        else:
            if RISKY.search(text):
                steps.append("judge")
            if _addressed(text, people) or _named_place(text, places, _here(user) or "") or RISKY.search(text):
                steps.append("react")
        if steps:
            return {"kind": "loop", "steps": steps, "note": "Something is at stake."}
        if ASKQ.match(text):
            return {"kind": "retrieval", "steps": [], "note": "You check what you have and what you know."}
        return {"kind": "fast", "steps": [], "note": "You do it, and nothing gets in the way."}

    def do_judge(self, user):
        text = _line(user, "PLAYER: ")
        skill = _skill(user)
        if RISKY.search(text):
            return {"verdict": "roll", "cites": ["player"], "uncertain": "whether it works",
                    "roll": {"subject": re.sub(r"\W+", "_", text.lower())[:40], "capability": 0, "base": 8, **({"skill": skill} if skill else {}), "committed": True,
                             "stakes": {"success": "it works", "failure": "it does not work and costs a little time", "harm": "none"}}}
        return {"verdict": "certain", "cites": ["player"], "reason": "an ordinary action"}

    def do_fight(self, user):
        skill = _skill(user)
        roll = {"capability": 0, "base": 8, **({"skill": skill} if skill else {})}
        return {"foes": [{"id": "sim_foe", "name": "the creature", "v": 1, "size": "small"}], "kill": True, "stop": "the foe is down",
                "exchanges": [{"foe": "sim_foe", "roll": roll, "on_success": "full", "my_source": "unarmed", "on_failure": "setback", "attackers": []}] * 4}

    def do_wonder(self, user):
        text = _line(user, "PLAYER: ")
        people = _people(user)
        for pid in _addressed(text, people)[:1]:
            return {"asks": [{"question": f"Does {people[pid]} help the player?", "obvious": "none", "likelihood": 0, "cites": [f"npcs.{pid}"],
                              "governs": [f"npcs.{pid}.state.status"]}]}
        return {"asks": []}

    def do_react(self, user):
        second = _second_pass(user)
        text = "" if second else _line(user, "PLAYER: ")             # on the second pass the action is done; only the dues are left
        people, places, here = _people(user), _places(user), _here(user)
        res = _results(user)
        addressed = _addressed(text, people)
        out = {"asks": [], "ops": [], "minutes": 1440 if re.search(r"\bday\b", text, re.I) else 480 if re.search(r"sleep|night", text, re.I)
               else 60 if re.search(r"hour|wait|rest", text, re.I) else 10}
        ops, who = [], addressed[:1]
        merged = "RESULTS" in user and not res and who and "dues" not in user.lower()[:0]
        if who and not res and not self._asked:
            self._asked = True                       # merged mode: the world step asks its own question first
            return {"asks": [{"question": f"Does {people[who[0]]} help the player?", "obvious": "none", "likelihood": 0, "cites": [f"npcs.{who[0]}"],
                              "governs": [f"npcs.{who[0]}.state.status"]}]}
        self._asked = False
        for q, ans, band in res:
            m = re.match(r"Does (.+?) help the player\?", q)
            if m:
                pid = next((i for i, n in people.items() if n == m.group(1)), None)
                if pid:
                    ops.append({"op": "set", "path": f"npcs.{pid}.state.status", "value": f"{'helps' if ans == 'YES' else 'declines to help'} the player",
                                "requires": {"on": q, "answer": ans, **({"band": band} if band else {})}, "because": "the answer to the question"})
        dest = _named_place(text, places, here)
        if dest:
            out["moved_to"] = dest
            out["minutes"] = max(out["minutes"], 20)
        if re.search(r"sleep|rest", text, re.I):
            out["rest"] = "sleep" if "sleep" in text.lower() else "rest"
        for m in re.finditer(r"DUE NOW[^\n]*?: (\[.*\])", user):
            try:
                dues = json.loads(m.group(1))
            except json.JSONDecodeError:
                dues = []
            for d in dues:
                who_ = d.get("who", "")
                if who_.startswith("active_world_pressures."):
                    out.setdefault("clocks", []).append({"pressure": who_, "operated": False})
                elif who_:
                    ops.append({"op": "plan", "path": who_, "value": "carries on with the day", "due_in_minutes": 600, "because": "the due fell and the move resolved"})
        names = ", ".join(people[i] for i in addressed) or "the room"
        out["report"] = (f"{people[who[0]]} answers the player." if who else "Time passes and nothing much changes.") + \
                        (f" The player reaches {dest}." if dest else "")
        out["ops"] = ops
        return out

    _asked = False

    def do_offer(self, user):
        return {"new_offer": False}

    def do_quest(self, user):
        return {"ops": []}

    def do_injury(self, user):
        return {"injury": "a bruised rib", "home": "capability", "effect": "heavy lifting is harder until it heals"}

    def do_ending(self, user):
        return {"met": [], "closed": []}

    def do_checkpoint(self, user):
        return {"ops": [], "notes": ["everything listed is still live"]}

    def do_audit(self, user):
        return {"ok": True, "problems": []}

    def do_tell(self, user):
        acc = " ".join(re.findall(r"(?:WHAT HAPPENED|THE GM'S DECISION): (.*)", user))
        lines = re.findall(r"RESULT (?:roll )?([A-Za-z ]+)", user)
        place = re.search(r"^PLACE: ([^—\n]+)", user, re.M)
        where = place.group(1).strip() if place else "the room"
        return (f"The air in {where} is still and a little damp, and the sounds of the street come through the walls in pieces. "
                f"{acc or 'Nothing around you has changed.'} You wait a breath to see what comes next.")

    def do_epilogue(self, user):
        return "Years later the places remember it differently, the way places do, and the people carry on with what is left."

    def do_intake(self, user):
        acts = []
        for m in re.finditer(r"^((?:npcs|factions|active_world_pressures)\.\w+):(.*)$", user, re.M):
            acts.append({"id": m.group(1), "dues": [{"day_offset": 1, "at": "09:00", "what": "carries on"}], "triggers": [],
                         **({"interval_minutes": 1440} if m.group(1).startswith("active") else {})})
        return {"actors": acts}


# ---- canned answers to the world-making forms (the sim backend uses them; tests use them as a known-good world) ----

PREMISE = {
    "title": "Ember Road", "background_id": "ember road v1", "source_game": "Ember Road", "world": "A road-and-ruin fantasy where toll roads cross old burnt kingdoms.",
    "era": "late medieval", "starting_region": "Cinder Vale", "mode": "canon", "canon_scope": "Cinder Vale's history before the start is fixed",
    "allowed_deviations": "Any outcome may change through play.",
    "anchors": {"peoples_or_species": ["humans", "ash-kin"], "powers_or_supernatural_rules": ["ember magic costs MP"], "technology": ["swords", "carts"],
                "institutions": ["toll wardens"], "economics_or_trade": ["silver coin"], "law_and_social_structure": ["wardens keep the roads"], "creatures_or_threats": ["ash wolves"]},
    "norms": {"law_and_outlaws": ["wardens protect toll payers"], "morale": [{"kind": "bandit", "breaks": "at the first death"}]},
    "mp_powers": {"draws_mp": ["ember_touch"], "recovery": "rest_only", "notes": "rest restores"},
    "depicts": ["travel", "fights"], "excludes": [], "tone": "grim and wry", "style": "plain",
    "start": {"date": "2026-04-10", "clock": "08:00", "daypart": "morning", "season": "spring", "weather": "grey and dry"},
    "modules": {"numeric_level_xp": {"on": True, "why": "levels are in the source"}, "equipment_power_tiers": {"on": True, "why": "relics have grades"},
                "bounded_scenario_endings": {"on": False, "why": "open road"}, "flexible_item_entitlement": {"on": True, "why": "merchants sell kit"}},
}
ITEMS = [("work_rates", "escort day rate", "5 silver"), ("work_rates", "courier run", "2 silver"), ("living", "inn bed", "3 copper"),
         ("living", "meal", "1 copper"), ("living", "stable night", "2 copper"), ("living", "road toll", "1 copper"),
         ("gear", "short sword", "40 silver"), ("gear", "waterskin", "5 copper"), ("gear", "healing salve", "8 silver"),
         ("gear", "torch", "1 copper"), ("services", "healer visit", "10 silver"), ("services", "scribe letter", "3 silver")]
ECONOMY = {"currency": "silver and copper, Cinder Vale", "groups": [
    {"group": g, "items": [{"item": i, "price": p} for gg, i, p in ITEMS if gg == g]} for g in ("work_rates", "living", "gear", "services")]}
PLAYER = {"name": "Kell Ardane", "age": 26, "origin": "Cinder Vale", "history": ["Guard of the toll road for six years."], "appearance": "lean", "archetype": "road warden",
          "job": "warden", "belongs": ["Toll Wardens"], "gender": "man", "character": "Steady, dry-humoured, hates debt.", "status": "well", "starting_activity": "Standing at the toll gate at dawn.",
          "skills": [{"id": "swordwork", "class": "ELITE", "tier": "T2", "class_source": "six years of road fights", "abilities": ["Parry Strike"]},
                     {"id": "ember_touch", "class": "NORMAL", "tier": "T1", "class_source": "awakened last year", "abilities": []}],
          "traits": ["stubborn"], "established": ["road fighting"], "limitations": ["no letters"], "level": 4,
          "equipment": [{"item_id": "short_sword", "name": "short sword", "type": "sword", "capability_domain": "melee", "condition": "worn", "tier": "T1", "price_ref": "short sword"},
                        {"item_id": "badge", "name": "warden badge", "type": "badge", "capability_domain": "authority", "condition": "serviceable", "tier": "T1", "price_ref": "personal"}],
          "money": 14, "item_points": 2, "item_points_basis": "ordinary professional", "knowledge": [{"key": "gate", "fact": "The east gate sticks."}],
          "source_abilities": [{"ability": "Parry Strike", "skill": "swordwork"}]}
PLACES = {"start_location": "toll_gate", "locations": [
    {"id": "toll_gate", "name": "East Toll Gate", "surface": "stone arch over the road", "band_min": 1, "band_max": 6, "band_basis": "busy road"},
    {"id": "inn", "name": "The Hollow Cask", "surface": "low timber inn", "band_min": 1, "band_max": 4, "band_basis": "village inn"},
    {"id": "ash_pit", "name": "The Ash Pit", "surface": "burnt quarry", "band_min": 4, "band_max": 10, "band_basis": "wolves nest here"}]}
CAST = {"npcs": [
    {"id": "mara_voss", "name": "Mara Voss", "gender": "woman", "job": "innkeeper", "belongs": [], "character": "Warm and shrewd with coin.", "status": "wiping tables",
     "position": "inn", "plan": "open the inn and wait for the carters", "due": "2026-04-10 09:00 opens the taproom", "wants": ["trade"], "fears": ["raids"], "values": ["fair dealing"],
     "tie": "local acquaintance", "attitude": "neutral"},
    {"id": "dorn_pell", "name": "Dorn Pell", "gender": "man", "job": "carter", "belongs": [], "character": "Loud, cheerful, owes money.", "status": "greasing a wheel",
     "position": "toll_gate", "plan": "wait for the gate to open", "due": "when the gate opens", "wants": ["pass the gate"], "fears": ["the wardens"], "values": ["his cart"],
     "tie": "stranger", "attitude": "neutral"},
    {"id": "ysolt_hale", "name": "Ysolt Hale", "gender": "woman", "job": "hunter", "belongs": [], "character": "Quiet, watchful.", "status": "watching the quarry",
     "position": "ash_pit", "plan": "track the wolves", "due": "2026-04-11 06:00 sets traps", "wants": ["safe roads"], "fears": ["a bad winter"], "values": ["patience"],
     "tie": "stranger", "attitude": "neutral", "level": 5}],
    "factions": [{"id": "toll_wardens", "name": "Toll Wardens", "role": "road law", "wants": ["tolls"], "fears": ["bandits"]}]}
STORY = {"quests": [{"id": "clear_the_pit", "role": "MAIN", "type": "SHORT", "level": 3, "objective": "Find what is driving the wolves out of the Ash Pit.", "status": "active", "participants": ["ysolt_hale"]}],
         "pressures": [{"id": "wolf_spread", "name": "Wolves spread", "origin": "the pit", "actors": ["ysolt_hale"], "trajectory": "toward the road", "clock_name": "wolf raids",
                        "segments": 6, "pace": "every 3 days while the pit is unhunted", "first_check": "2026-04-13 06:00", "on_fill": "wolves raid the inn"}],
         "hidden": [{"id": "pit_cause", "cause": "A buried ember relic is waking.", "evidence": ["scorched stones"], "routes": ["follow the wolves", "ask the carters"]}],
         "rights": [{"id": "warden_oath", "type": "duty", "parties": ["kell_ardane", "toll_wardens"], "status": "on duty"}],
         "endings": {"core": [], "hidden": []}}
GOOD = {"premise": PREMISE, "economy": ECONOMY, "player": PLAYER, "places": PLACES, "cast": CAST, "story": STORY}
