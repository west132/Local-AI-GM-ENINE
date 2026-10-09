"""Make a BACKGROUND from a short idea. The AI fills six forms (engine/generate.yaml); the program checks each one,
sends the faults back for a fix, and writes the file itself. Nothing the AI says goes in unchecked."""
from __future__ import annotations
import datetime as dt, json, pathlib, re, yaml

from . import clock, rules as R, schema
from .state import World, background_tree, _ISO_DUE

ENGINE = pathlib.Path(__file__).resolve().parent.parent / "engine"
GENDER_BLANK = {"", "unknown", "none", "n/a", "tbd", "?"}
MODULES = ("numeric_level_xp", "equipment_power_tiers", "bounded_scenario_endings", "flexible_item_entitlement")
on_stage = None            # the web page shows which form is being filled


def stages() -> list[dict]:
    return yaml.safe_load((ENGINE / "generate.yaml").read_text(encoding="utf-8"))["stages"]


def slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")
    return s or "x"


def full_name(n: str) -> bool:
    n = str(n).strip()
    if re.search(r"[㐀-鿿]", n):
        return len(n.replace("·", "").replace(" ", "")) >= 2          # Chinese names: surname + given name
    parts = [p for p in re.split(r"[\s]+", n) if len(re.sub(r"\W", "", p)) >= 2]
    return len(parts) >= 2


def cal_of(premise: dict):
    """The world's calendar: its own table if the premise gave one, else YYYY-MM-DD."""
    return clock.Custom(premise["calendar"]) if premise.get("calendar") else clock.Gregorian()


def _when(text: str, cal):
    """(day ordinal, minutes) of 'DATE HH:MM ...' written in the calendar, else None; tuples compare in time order."""
    m = re.match(r"\s*" + cal.pattern + r"[ T,]+(?P<t>\d{1,2}):(?P<m>\d{2})", str(text), re.I)
    if not m:
        return None
    try:
        return cal.ordinal_of(m["y"], m["mo"], m["d"]), int(m["t"]) * 60 + int(m["m"])
    except ValueError:
        return None


def _example(cal, start: str) -> str:
    n = clock.date_ordinal(cal, start)
    return f"{cal.fmt(n + 1) if n else 'a date'} 18:30"


def _is_trigger(text: str) -> bool:
    return bool(re.match(r"^\s*(when|if|once|after|on the|as soon as|immediately)\b", text, re.I))


# ---------- the checks, one per form ----------

def check_premise(o: dict, ctx: dict) -> list[str]:
    out = []
    if o["mode"] == "canon" and not o["source_game"].strip():
        out.append("mode canon needs source_game (the game, book or show it is set in)")
    if o["mode"] == "canon" and not o.get("canon_scope", "").strip():
        out.append("mode canon needs canon_scope")
    try:
        cal = cal_of(o)
    except ValueError as e:
        return out + [f"calendar: {e}"]
    if clock.date_ordinal(cal, o["start"]["date"]) is None:
        out.append("start.date must be a real date in the world's calendar" + ("" if o.get("calendar") else " written YYYY-MM-DD")
                   + (f", e.g. {cal.fmt(1000)}" if o.get("calendar") else ""))
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", o["start"]["clock"]):
        out.append("start.clock must be HH:MM")
    for m in MODULES:
        mod = o["modules"][m]
        if not mod["on"] and m != "bounded_scenario_endings" and len(mod["why"].strip()) < 20:
            out.append(f"modules.{m} is off: give the real reason it does not fit, or turn it on")
    return out


_PRICE = re.compile(r"\d|no fixed price", re.I)


def check_economy(o: dict, ctx: dict) -> list[str]:
    out, seen, n = [], set(), 0
    for g in o["groups"]:
        for it in g["items"]:
            n += 1
            k = it["item"].strip().lower()
            if k in seen:
                out.append(f"{it['item']!r} is listed twice")
            seen.add(k)
            if not _PRICE.search(it["price"]):
                out.append(f"{it['item']}: price {it['price']!r} has no number (write the amount, or 'no fixed price: depends on …')")
    if n < 12:
        out.append(f"only {n} priced items; the list needs at least 12")
    if not {"living", "gear"} <= {g["group"] for g in o["groups"]}:
        out.append("the list needs both a living group and a gear group")
    return out


def check_player(o: dict, ctx: dict) -> list[str]:
    out, prem = [], ctx["premise"]
    if not full_name(o["name"]):
        out.append(f"name {o['name']!r} is not a full name (given + family)")
    if o["gender"].strip().lower() in GENDER_BLANK:
        out.append("gender must be a plain word such as man, woman, nonbinary")
    skills = {slug(s["id"]): s for s in o["skills"]}
    for s in o["skills"]:
        ceiling = {"NORMAL": "T2", "ELITE": "T3", "LEGENDARY": "T4"}[s["class"]]
        if int(s["tier"][1]) > int(ceiling[1]):
            out.append(f"skill {s['id']}: tier {s['tier']} is above the {s['class']} ceiling {ceiling}")
        if s["tier"] != "T1" and not s["class_source"].strip():
            out.append(f"skill {s['id']}: tier {s['tier']} needs class_source (what earned it)")
    if o["level"] >= 4 and not any(s["tier"] != "T1" for s in o["skills"]):
        out.append("level 4 or more needs at least one skill above T1")
    priced = {i["item"].strip().lower() for g in ctx["economy"]["groups"] for i in g["items"]}
    for e in o["equipment"]:
        if e["price_ref"].strip().lower() not in priced | {"personal"}:
            out.append(f"equipment {e['name']}: price_ref {e['price_ref']!r} is not in the price list (use an item name from it, or 'personal')")
        if prem["modules"]["equipment_power_tiers"]["on"] and not e.get("tier"):
            out.append(f"equipment {e['name']}: this world grades gear; give a tier T1–T4")
    if prem["mode"] == "canon":
        if not o["source_abilities"]:
            out.append(f"canon: list the starting abilities {prem['source_game']!r} gives this protagonist (source_abilities)")
        for a in o["source_abilities"]:
            held = skills.get(slug(a["skill"]))
            if not held:
                out.append(f"source ability {a['ability']!r}: skill {a['skill']!r} is not in skills")
            elif a["ability"].strip().lower() not in {x.strip().lower() for x in held["abilities"]}:
                out.append(f"source ability {a['ability']!r} must also be listed in skills.{a['skill']}.abilities")
    if prem["mp_powers"]["draws_mp"] and "mp" not in o:
        out.append("this world has MP-drawing powers; give the character's starting mp (0 if they have none)")
    if o["money"] <= 0 and not o["history"]:
        out.append("money is 0 with no history to explain it")
    return out


def check_places(o: dict, ctx: dict) -> list[str]:
    ids = [slug(x["id"]) for x in o["locations"]]
    out = [f"duplicate place id {i}" for i in set(ids) if ids.count(i) > 1]
    if slug(o["start_location"]) not in ids:
        out.append(f"start_location {o['start_location']!r} is not one of the places")
    out += [f"{x['id']}: band_min is above band_max" for x in o["locations"] if x["band_min"] > x["band_max"]]
    return out


def check_cast(o: dict, ctx: dict) -> list[str]:
    out, places = [], {slug(x["id"]) for x in ctx["places"]["locations"]}
    cal = cal_of(ctx["premise"])
    start = _when(ctx["premise"]["start"]["date"] + " " + ctx["premise"]["start"]["clock"], cal)
    ids = [slug(n["id"]) for n in o["npcs"]]
    out += [f"duplicate person id {i}" for i in set(ids) if ids.count(i) > 1]
    for n in o["npcs"]:
        who = n["id"]
        if not full_name(n["name"]):
            out.append(f"{who}: name {n['name']!r} is not a full name (given + family)")
        if n["gender"].strip().lower() in GENDER_BLANK:
            out.append(f"{who}: gender must be a plain word such as man, woman, nonbinary")
        if slug(n["position"]) not in places:
            out.append(f"{who}: position {n['position']!r} is not a place id ({sorted(places)})")
        w = _when(n["due"], cal)
        if w is None and not _is_trigger(n["due"]):
            out.append(f"{who}: due {n['due']!r} must read '{_example(cal, ctx['premise']['start']['date'])} what happens' (a real date in the calendar) or 'when <condition>'")
        elif w is not None and start and w < start:
            out.append(f"{who}: due {n['due']!r} is before the story starts")
    return out


def check_story(o: dict, ctx: dict) -> list[str]:
    out = []
    people = {slug(n["id"]) for n in ctx["cast"]["npcs"]} | {slug(f["id"]) for f in ctx["cast"]["factions"]} | {slug(ctx["player"]["name"])}
    cal = cal_of(ctx["premise"])
    start = _when(ctx["premise"]["start"]["date"] + " " + ctx["premise"]["start"]["clock"], cal)
    if not any(q["role"] == "MAIN" for q in o["quests"]):
        out.append("at least one quest must be MAIN")
    for q in o["quests"]:
        out += [f"quest {q['id']}: participant {p!r} is not in the cast" for p in q["participants"] if slug(p) not in people]
    for p in o["pressures"]:
        out += [f"pressure {p['id']}: actor {a!r} is not in the cast" for a in p["actors"] if slug(a) not in people]
        if not p["pace"].lower().startswith("every "):
            out.append(f"pressure {p['id']}: pace must read 'every <interval> while <condition>'")
        w = _when(p["first_check"], cal)
        if w is None or (start and w < start):
            out.append(f"pressure {p['id']}: first_check must read like '{_example(cal, ctx['premise']['start']['date'])}', a real date on or after the start")
    for r in o["rights"]:
        out += [f"right {r['id']}: party {x!r} is not in the cast" for x in r["parties"] if slug(x) not in people]
    if ctx["premise"]["modules"]["bounded_scenario_endings"]["on"] and not o["endings"]["core"]:
        out.append("bounded_scenario_endings is on: give at least one core ending condition")
    return out


CHECKS = {"premise": check_premise, "economy": check_economy, "player": check_player,
          "places": check_places, "cast": check_cast, "story": check_story}


# ---------- asking ----------

def _show(ctx: dict, names: list[str]) -> str:
    return "\n\n".join(f"{n.upper()} (already decided):\n{json.dumps(ctx[n], ensure_ascii=False)}" for n in names)


def fill(llm, stage: dict, idea: str, ctx: dict, tries: int = 3) -> dict:
    sch = stage["output"]
    system = "\n\n".join((ENGINE / "rules" / f"{r}.md").read_text(encoding="utf-8") for r in stage["rules"])
    system += "\n\nREPLY with one JSON object only:\n" + schema.render(sch)
    user = f"IDEA FROM THE PERSON:\n{idea.strip()}\n\n" + (_show(ctx, stage.get("input", [])) if stage.get("input") else "")
    faults: list[str] = []
    for _ in range(tries):
        try:
            out = llm.ask(system, user + (("\n\nYour last answer had these faults. Fix them and answer again in full:\n- " + "\n- ".join(faults)) if faults else ""),
                          sch, max_tokens=stage.get("max_tokens"))
        except ValueError as e:
            faults = [f"not valid JSON ({e})"]
            continue
        faults = schema.validate(out, sch, stage["id"]) if isinstance(out, dict) else ["reply must be one JSON object"]
        if not faults:
            faults = CHECKS[stage["id"]](out, ctx)
        if not faults:
            return out
    raise ValueError(f"The AI could not fill the {stage['id']} form correctly after {tries} tries: " + "; ".join(faults[:6]))


# ---------- assembling ----------

def _vitality(level: int) -> str:
    return "ordinary" if level <= 2 else "seasoned" if level <= 5 else "veteran" if level <= 9 else "exceptional" if level <= 13 else "heroic" if level <= 17 else "legendary"


def _minutes(clock: str) -> int:
    h, m = clock.split(":")
    return int(h) * 60 + int(m)


def assemble(ctx: dict) -> str:
    pr, ec, pl, pg, cs, st = (ctx[k] for k in ("premise", "economy", "player", "places", "cast", "story"))
    mods = {m: bool(pr["modules"][m]["on"]) for m in MODULES}
    if mods["bounded_scenario_endings"] and not st["endings"]["core"]:
        mods["bounded_scenario_endings"] = False
    pid = slug(pl["name"])
    anchors = {k: v for k, v in pr["anchors"].items() if v}
    anchors["norms"] = {"law_and_outlaws": pr["norms"]["law_and_outlaws"], "morale": {slug(m["kind"]): m["breaks"] for m in pr["norms"]["morale"]}}
    anchors["mp_powers"] = pr["mp_powers"]
    prices: dict = {"currency": ec["currency"]}
    for g in ec["groups"]:
        prices.setdefault(g["group"], {}).update({slug(i["item"]): i["price"] for i in g["items"]})
    anchors["prices"] = prices
    player = {
        "identity": {"name": pl["name"], "age": pl["age"], "origin": pl["origin"], "history": pl["history"]},
        "appearance": pl["appearance"], "archetype": pl["archetype"], "job": pl["job"], "belongs": [slug(b) for b in pl["belongs"]],
        "gender": pl["gender"], "character": pl["character"], "status": pl["status"], "starting_activity": pl["starting_activity"],
        "skills": {slug(s["id"]): {"class": s["class"], "tier": s["tier"], "growth_evidence": 0, "ceiling_evidence": 0,
                                   "class_source": s["class_source"], "abilities": s["abilities"]} for s in pl["skills"]},
        "traits": pl["traits"], "expertise": {"established": pl["established"], "limitations": pl["limitations"]},
        "growth_period": {"opened": 0, "credited": []},
    }
    if mods["numeric_level_xp"]:
        player["progression"] = {"system": "numeric_level_xp", "state": {"level": pl["level"], "xp": 0}}
    else:
        player["vitality"] = _vitality(pl["level"])
    if mods["flexible_item_entitlement"]:
        player["starting_item_points"] = {"points": pl["item_points"], "basis": pl["item_points_basis"]}
    player["condition"] = {"hp": pl["hp"], **({"mp": pl["mp"]} if "mp" in pl else {}), "injuries": [], "fatigue": "none", "last_rest": "recently"}
    player["equipment"] = [{"item_id": slug(e["item_id"] or e["name"]), "name": e["name"], "type": e["type"], "capability_domain": e["capability_domain"],
                            "condition": e["condition"], **({"tier": e["tier"]} if mods["equipment_power_tiers"] and e.get("tier") else {}),
                            "special_properties": e.get("special_properties", []), "abilities": e.get("abilities", [])} for e in pl["equipment"]]
    player.update(money=int(pl["money"]) if float(pl["money"]).is_integer() else pl["money"], resources={}, routines={}, fighting_style=[],
                  knowledge={"facts": {slug(k["key"]): k["fact"] for k in pl["knowledge"]}, "channels": ["what they see and hear", "people they talk to"]})
    npcs = {}
    for n in cs["npcs"]:
        rec = {"name": n["name"], "job": n["job"], "belongs": [slug(b) for b in n["belongs"]], "gender": n["gender"], "character": n["character"],
               "state": {"status": n["status"], "position": slug(n["position"]), "plan": n["plan"], "due": n["due"],
                         **({"work_source": n["work_source"]} if n.get("work_source", "").strip() else {})},
               "drives": {"wants": n["wants"], "fears": n["fears"], "values": n["values"]},
               "relationships": {pid: {"tie": n["tie"], "attitude": n["attitude"], "credit": [], "grievance": [], "believes_identity": "unknown"}},
               "knowledge": {"facts": {slug(k["key"]): k["fact"] for k in n.get("knows", [])}, "channels": ["what they see and hear"]},
               "capability": {"overall_level": n["level"]} if n.get("level") and mods["numeric_level_xp"] else {},
               "discovered_information": {}}
        npcs[slug(n["id"])] = rec
    factions = {slug(f["id"]): {"name": f["name"], "role": f["role"], "state": {}, "drives": {"wants": f["wants"], "fears": f["fears"]},
                                "relationships": {}, "knowledge": {"facts": {}, "channels": []}, "capability": {}, "discovered_information": {}}
                for f in cs["factions"]}
    quests = {slug(q["id"]): {"role": q["role"], "type": q["type"], "objective": q["objective"], "status": q["status"],
                              "participants": [slug(p) for p in q["participants"]], "support_refs": []} for q in st["quests"]}
    pressures = {slug(p["id"]): {"name": p["name"], "origin": p["origin"], "state": {}, "actors": [slug(a) for a in p["actors"]],
                                 "trajectory": p["trajectory"],
                                 "clock": {"name": p["clock_name"], "segments": p["segments"], "filled": 0, "pace": p["pace"],
                                           "due": p["first_check"], "on_fill": p["on_fill"]},
                                 "discovered_information": {}} for p in st["pressures"]}
    cases = {slug(h["id"]): {"cause": h["cause"], "prior_events": h.get("prior_events", []), "state": {},
                             "evidence": {"clues": h["evidence"], "routes": h["routes"]}, "trajectory": "", "discovered_information": {}}
             for h in st["hidden"]}
    rights = {slug(r["id"]): {"type": r["type"], "parties": [slug(x) for x in r["parties"]], "state": {"status": r["status"]}} for r in st["rights"]}
    s = pr["start"]
    tree = {
        "background_id": slug(pr["background_id"]), "provenance": "generated", "requested": [],
        "setting": {k: v for k, v in {"world": pr["world"], "era": pr["era"], "starting_region": pr["starting_region"], "mode": pr["mode"],
                                       "canon_scope": pr.get("canon_scope") or None, "allowed_deviations": pr["allowed_deviations"]}.items() if v},
        "setting_anchors": anchors, "player": player,
        "content_bounds": {"depicts": pr["depicts"], "excludes": pr["excludes"], "notes": ""},
        "enabled_modules": mods,
        "locations": {slug(x["id"]): {"name": x["name"], "conditions": {"surface": x["surface"], **({"features": x["feature"]} if x.get("feature") else {})},
                                      "challenge_band": {"min": x["band_min"], "max": x["band_max"], "basis": x["band_basis"]}} for x in pg["locations"]},
        "rights_obligations": rights, "active_commitments": [k for k in rights if pid in rights[k]["parties"]],
        "npcs": npcs, "factions": factions, "quests": quests, "development_threads": {}, "trackers": {},
        "active_world_pressures": pressures, "locked_case_truths": cases, "open_suspicions": {},
        "world_state": {"location": slug(pg["start_location"]),
                        "time": {"season": s["season"], "day_index": 0, "date": s["date"], "clock_minutes": _minutes(s["clock"]),
                                 "daypart": s["daypart"], "precision": "exact"},
                        "environment": {"weather": s["weather"]}, "material_history": [], "unowned_facts": {"visible": [], "hidden": []}},
        "narrative_theme": {"initial": {"tone": pr["tone"], "style": pr["style"]}, "current": {"tone": pr["tone"], "style": pr["style"]}},
    }
    if pr.get("calendar"):
        tree["calendar"] = {k: v for k, v in pr["calendar"].items() if v not in (None, "", [])}
    if mods["bounded_scenario_endings"]:
        tree["ending_conditions"] = {"core_conditions": st["endings"]["core"], "hidden_conditions": st["endings"]["hidden"], "closed": []}
    if pr["source_game"]:
        tree["requested"] = [f"set in {pr['source_game']}"]
    tree["requested"] = tree["requested"] or [ctx["idea"].strip()[:300]]
    head = f"# BACKGROUND — {pr['title']} v5.0\n\nGenerated from this idea: {ctx['idea'].strip()}\n\nFor `NEW ENGINE v5.0`. Round-0 truth. Provisional until play relies on it. GM-only.\n\n"
    return head + "```yaml\n" + yaml.safe_dump(tree, sort_keys=False, allow_unicode=True, width=110) + "```\n"


def verify(text: str) -> list[str]:
    """The finished file must load as a world and pass the same whole-world checks every commit passes."""
    try:
        w = World(background_tree(text))
    except Exception as e:
        return [f"does not load: {type(e).__name__}: {e}"]
    out = R.player_faults(w.tree)
    out += [f"{k}.{i}: position {r['state'].get('position')!r} is not a place" for k in ("npcs",) for i, r in w.tree[k].items()
            if r["state"].get("position") not in w.tree["locations"]]
    if w.tree["world_state"]["location"] not in w.tree["locations"]:
        out.append("world_state.location is not a place")
    return out


def generate(llm, idea: str) -> tuple[str, dict]:
    ctx: dict = {"idea": idea}
    for st in stages():
        if on_stage:
            on_stage(st["id"])
        ctx[st["id"]] = fill(llm, st, idea, ctx)
    text = assemble(ctx)
    faults = verify(text)
    if faults:
        raise ValueError("The finished world has faults: " + "; ".join(faults[:6]))
    return text, ctx


def save_world(root, text: str) -> str:
    wid = base = background_tree(text)["background_id"]
    n = 1
    while (pathlib.Path(root) / "worlds" / wid).exists():          # never overwrite an earlier world
        n += 1
        wid = f"{base}_{n}"
    d = pathlib.Path(root) / "worlds" / wid
    d.mkdir(parents=True, exist_ok=True)
    (d / "background.md").write_text(text, encoding="utf-8")
    return wid
