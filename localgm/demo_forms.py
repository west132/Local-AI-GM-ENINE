"""Canned, valid answers to the world-making forms: the Demo AI uses them so the whole flow runs with no model."""

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
          "traits": ["stubborn"], "established": ["road fighting"], "limitations": ["no letters"], "level": 4, "hp": 40, "mp": 12,
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
STORY = {"quests": [{"id": "clear_the_pit", "role": "MAIN", "type": "SHORT", "objective": "Find what is driving the wolves out of the Ash Pit.", "status": "active", "participants": ["ysolt_hale"]}],
         "pressures": [{"id": "wolf_spread", "name": "Wolves spread", "origin": "the pit", "actors": ["ysolt_hale"], "trajectory": "toward the road", "clock_name": "wolf raids",
                        "segments": 6, "pace": "every 3 days while the pit is unhunted", "first_check": "2026-04-13 06:00", "on_fill": "wolves raid the inn"}],
         "hidden": [{"id": "pit_cause", "cause": "A buried ember relic is waking.", "evidence": ["scorched stones"], "routes": ["follow the wolves", "ask the carters"]}],
         "rights": [{"id": "warden_oath", "type": "duty", "parties": ["kell_ardane", "toll_wardens"], "status": "on duty"}],
         "endings": {"core": [], "hidden": []}}
GOOD = {"premise": PREMISE, "economy": ECONOMY, "player": PLAYER, "places": PLACES, "cast": CAST, "story": STORY}
