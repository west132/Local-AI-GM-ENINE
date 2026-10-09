"""Fight executor: the AI names the exchanges its orders cover; the program rolls and keeps HP."""
from __future__ import annotations
import re

from . import mechanics as M, rules
from .state import World

DAMAGE = {"unarmed": "1d3", "light": "1d6", "one-handed": "1d8", "two-handed": "2d6", "bow": "1d8",
          "small": "1d4", "man-sized": "1d6", "large": "2d6", "huge": "3d6",
          "hazard-light": "1d6", "hazard-serious": "2d6", "hazard-grave": "4d6",
          "T1": "1d8", "T2": "2d6", "T3": "3d6", "T4": "4d6"}


def damage_roll(source: str, rng=None) -> tuple[int, str]:
    spec = DAMAGE.get(source)
    if not spec:
        raise M.RuleError(f"unknown damage source {source!r}; use one of {sorted(DAMAGE)}")
    n, sides = map(int, spec.split("d"))
    dice = M.roll(n, sides, rng)
    return sum(dice), f"{spec} ({'+'.join(map(str, dice))})"


def add_foes(world: World, foes: list[dict]) -> None:
    npcs = world.tree.setdefault("npcs", {})
    for f in foes:
        npcs.setdefault(f["id"], {"name": f["name"], "v": f["v"], "size": f["size"],
                                  "state": {"position": world.tree["world_state"]["location"], "status": "fighting the player"}})


def run(world: World, out: dict, rng=None) -> tuple[list[str], list[str], int]:
    """Returns (printed lines, facts for the narrator, lasting injuries owed to the player)."""
    add_foes(world, out.get("foes", []))
    lines, facts, owed = [], [], 0
    lv0 = rules.level(world)
    downed = []
    down_before = {n for n in world.tree.get("npcs", {}) if world.state_of(n) != "standing"}
    for i, ex in enumerate(out["exchanges"], 1):
        if world.player_state() != "standing":
            facts.append(f"The player is {world.player_state()}; the remaining exchanges did not happen.")
            break
        foe = ex["foe"]
        if foe not in world.tree.get("npcs", {}):
            raise M.RuleError(f"exchange {i}: unknown foe {foe!r}")
        if world.state_of(foe) != "standing":
            if foe in down_before:                       # exchanges listed after the foe fell are skipped quietly
                facts.append(f"{foe} is already {world.state_of(foe)}.")
            continue
        r = ex["roll"]
        foe_rec = world.tree["npcs"][foe]
        cap, tool, diff, _ = rules.roll_inputs(world, r, foe_rec.get("v"))
        res = M.check(cap, tool, diff, rng)
        d1, d2 = res["dice"]
        win = res["success"]
        lines.append(f"Exchange {i} vs {foe} — 2d10: {d1}+{d2} | Capability: {cap:+d} | Tool: {tool:+d} | "
                     f"Total: {res['total']} | Difficulty: {diff} | {'Success' if win else 'Failure'}")
        if win:
            if ex["on_success"] == "partial":
                facts.append(f"Exchange {i}: a foothold against {foe}, no hit.")
            else:
                raw, how = damage_roll(ex["my_source"], rng)
                h = world.hurt([raw], 0, foe)
                lines.append(f"Damage to {foe}: {how} = {raw} | HP {h['before']} → {h['hp']}"
                             + (f" — {h['state']}" if h["state"] != "standing" else ""))
                facts.append(f"Exchange {i}: the player hits {foe} ({ex['on_success']}); {foe} is {h['state']}.")
                if h["state"] != "standing" and not foe_rec.get("xp_paid"):
                    downed.append(foe)
        else:
            atk = ex["attackers"]
            hits = {"setback": [], "loss": atk[:1], "severe": atk}[ex["on_failure"]]
            if ex["on_failure"] == "severe" and len(atk) == 1:
                hits = atk * 2
            if not hits:
                facts.append(f"Exchange {i}: the player loses position against {foe}; no wound.")
            for a in hits:
                raw, how = damage_roll(a["source"], rng)
                h = world.hurt([raw], ex.get("soak", 0), "player")
                lines.append(f"Damage to player from {a['who']}: {how} − soak {ex.get('soak', 0)} | "
                             f"HP {h['before']} → {h['hp']}" + (f" — {h['state']}" if h["state"] != "standing" else "")
                             + ("\nLasting injury" if h["lasting_injury"] else ""))
                owed += bool(h["lasting_injury"])
                facts.append(f"Exchange {i}: {a['who']} wounds the player; the player is {h['state']}."
                             + (" A lasting injury is owed." if h["lasting_injury"] else ""))
                if h["state"] != "standing":
                    break
    if out.get("kill"):                  # the player's order is to kill: a downed foe is helpless, so no roll
        for foe in [f for f in dict.fromkeys(ex["foe"] for ex in out["exchanges"]) if world.state_of(f) == "down"]:
            h = world.hurt([1], 0, foe)
            lines.append(f"{foe} was down and helpless; the player finishes it (no roll) — {h['state']}")
            facts.append(f"The player finished the downed {foe}; it is {h['state']}.")
    if out.get("stop"):
        facts.append(f"Orders stop here: {out['stop']}")
    if downed and lv0 is not None:      # combat XP: each foe overcome, against the level held at the start, one pass for everyone
        msgs = rules.xp_pass(world, [int(world.tree["npcs"][f].get("v", 1)) for f in downed], "meaningful")
        for f in downed:
            world.tree["npcs"][f]["xp_paid"] = True
        rules.add_history(world, f"Combat in round {world.round + 1}: {', '.join(downed)} overcome.")
        facts += msgs
    return lines, facts, owed
