"""Everything numeric. Pure functions; no state, no AI. Rules come from LOCAL_ENGINE.md sections 8-12.

Every function that rolls takes `rng` (a random.Random) so tests are repeatable; the default is
the OS random source.
"""
from __future__ import annotations
import math, random

_SYS = random.SystemRandom()


class RuleError(ValueError):
    """The input breaks a fixed rule. The caller must fix the input; nothing is rolled."""


def roll(n: int, sides: int, rng=None) -> list[int]:
    if not (1 <= n <= 20 and 2 <= sides <= 1000):
        raise RuleError("dice must be 1..20 dice of 2..1000 sides")
    r = rng or _SYS
    return [r.randint(1, sides) for _ in range(n)]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------- checks (section 8) ----------

CONDITIONS = ("environment", "time", "sensory", "position", "simultaneous")
CAP_BANDS = (-4, -2, 0, 2, 4)


def capmod(actor: int, challenge: int) -> int:
    """Banded gap between an actor's level and a numeric Challenge."""
    if actor < 1 or challenge < 1:
        raise RuleError("level and challenge must be >= 1")
    d = actor - challenge
    return -4 if d <= -5 else -2 if d <= -2 else 0 if d <= 1 else 2 if d <= 4 else 4


def difficulty(base: int, conditions: dict | None = None) -> int:
    """Base 1..20 plus execution penalties (+ harder, - easier, each -1..+2, sum bounded to +-3)."""
    if not 1 <= base <= 20:
        raise RuleError("base difficulty must be 1..20")
    conditions = conditions or {}
    for k, v in conditions.items():
        if k not in CONDITIONS or v not in (-1, 0, 1, 2):
            raise RuleError(f"condition {k!r} must be one of {CONDITIONS} with value -1, 0, +1 or +2")
    return clamp(base + clamp(sum(conditions.values()), -3, 3), 1, 20)


def tool_mod(fit: int = 0, condition: int = 0) -> int:
    if fit not in range(-2, 3) or condition not in (0, -1, -2):
        raise RuleError("fit must be -2..+2 and tool condition 0, -1 or -2")
    return clamp(fit + condition, -2, 2)


def odds(cap: int, tool: int, diff: int) -> int:
    """Exact percent chance that 2d10 + cap + tool reaches diff."""
    need = diff - cap - tool
    return sum(1 for x in range(1, 11) for y in range(1, 11) if x + y >= need)


def check(cap: int, tool: int, diff: int, rng=None) -> dict:
    if cap not in CAP_BANDS:
        raise RuleError(f"capability modifier must be one of {CAP_BANDS}")
    dice = roll(2, 10, rng)
    total = sum(dice) + cap + tool
    return {"dice": dice, "cap": cap, "tool": tool, "total": total, "difficulty": diff,
            "success": total >= diff}


ASK_BANDS = ((16, "YES, AND"), (12, "YES"), (7, "NO, BUT"), (-99, "NO, AND"))


def ask(likelihood: int, rng=None) -> dict:
    """Open question (section 11): 2d10 + likelihood -> four degrees."""
    if not -3 <= likelihood <= 3:
        raise RuleError("likelihood is -3..+3")
    dice = roll(2, 10, rng)
    total = sum(dice) + likelihood
    return {"dice": dice, "likelihood": likelihood, "total": total,
            "band": next(n for floor, n in ASK_BANDS if total >= floor)}


# ---------- experience and growth (CODE only) ----------

XP_REQ = {1: 126, 2: 164, 3: 220, 4: 297, 5: 400, 6: 534, 7: 705, 8: 918, 9: 1181, 10: 1500,
          11: 1883, 12: 2339, 13: 2875, 14: 3500, 15: 4225, 16: 5059, 17: 6012, 18: 7096, 19: 8321,
          20: 9700, 21: 11245, 22: 12969, 23: 14885, 24: 17008, 25: 19350, 26: 21928, 27: 24755,
          28: 27849, 29: 31225, 30: 34900, 31: 38891, 32: 43216, 33: 47892, 34: 52939}
LEVEL_CAP = 35
SCOPE = {"routine": 0.0, "minor": 0.5, "meaningful": 1.0, "major": 1.25, "exceptional": 1.5}


def _half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def xp_award(challenge: int, level: int, scope: str) -> int:
    if challenge < 1 or scope not in SCOPE:
        raise RuleError(f"challenge >= 1 and scope one of {sorted(SCOPE)}")
    gap = challenge - level
    learn = 0.0 if gap <= -5 else 0.5 if gap <= -3 else 0.75 if gap <= -1 else 1.0
    return _half_up(_half_up((20 + 6 * challenge) * learn) * SCOPE[scope])


def add_xp(level: int, xp: int, amount: int) -> tuple[int, int, list[int]]:
    if not 1 <= level <= LEVEL_CAP or xp < 0 or amount < 0:
        raise RuleError("bad level/xp/amount")
    if level == LEVEL_CAP:
        return level, 0, []
    xp += amount
    ups = []
    while level < LEVEL_CAP and xp >= XP_REQ[level]:
        xp -= XP_REQ[level]
        level += 1
        ups.append(level)
    return level, (0 if level == LEVEL_CAP else xp), ups


CEILING = {"NORMAL": "T2", "ELITE": "T3", "LEGENDARY": "T4"}
TIERS = ["T1", "T2", "T3", "T4"]
GROWTH_AT = {"T1": 10, "T2": 20, "T3": 40}
CLASS_AT = {"NORMAL": 20, "ELITE": 40}
NEXT_CLASS = {"NORMAL": "ELITE", "ELITE": "LEGENDARY"}


def evidence(success: bool, difficulty_: int, challenge: int | None = None, skill_level: int | None = None) -> int:
    """Evidence one roll gives a skill. Failures give none."""
    if not success:
        return 0
    num = 0
    if challenge is not None and skill_level is not None and challenge >= skill_level - 1:
        gap = challenge - skill_level
        num = 1 if gap <= 1 else 2 if gap <= 4 else 3
    cond = 2 if difficulty_ >= 19 else 1 if difficulty_ >= 15 else 0
    return max(num, cond)


def grow(cls: str, tier: str, ev: int, ceiling_ev: int, class_source: bool) -> dict:
    """Settle stored evidence at a growth boundary: tier raises, then a class raise if earned."""
    if cls not in CEILING or tier not in TIERS or TIERS.index(tier) > TIERS.index(CEILING[cls]):
        raise RuleError("invalid class/tier")
    raised = []
    while tier != CEILING[cls] and ev >= GROWTH_AT[tier]:
        ev -= GROWTH_AT[tier]
        tier = TIERS[TIERS.index(tier) + 1]
        raised.append(tier)
    if tier == CEILING[cls] and ev:
        ceiling_ev, ev = ceiling_ev + ev, 0
    class_raised = None
    if tier == CEILING[cls] and cls in CLASS_AT and ceiling_ev >= CLASS_AT[cls] and class_source:
        cls, class_raised, ceiling_ev = NEXT_CLASS[cls], NEXT_CLASS[cls], 0
    return {"class": cls, "tier": tier, "growth_evidence": ev, "ceiling_evidence": ceiling_ev,
            "tiers_raised": raised, "class_raised": class_raised}


# ---------- body (CODE only) ----------

SIZE_MULT = {"small": 0.5, "normal": 1, "large": 2, "huge": 4}
TIER_BONUS = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}


def max_hp(v: int, size: str = "normal") -> int:
    if v < 1 or size not in SIZE_MULT:
        raise RuleError("V >= 1 and size small/normal/large/huge")
    return math.ceil((8 + 2 * v) * SIZE_MULT[size])


def max_mp(v: int, tier: str) -> int:
    return 2 * v + 4 * TIER_BONUS[tier]


def harm(hp: int, hp_max: int, damage: list[int], soak: int = 0) -> dict:
    """Apply hits in order. Down at 0; any damage while down is death. Lasting injury on a
    hit that is half the maximum or more, or that drops the target to 0."""
    if hp_max < 1 or not 0 <= hp <= hp_max or soak < 0:
        raise RuleError("need 0 <= hp <= max, soak >= 0")
    state = "standing" if hp > 0 else "down"
    lasting, lost = False, []
    for raw in damage:
        d = max(0, raw - soak)
        before = hp
        if d and state == "down":
            state = "dead"
        hp = max(0, hp - d)
        if d and (d * 2 >= hp_max or (before > 0 and hp == 0)):
            lasting = True
        if hp == 0 and state == "standing":
            state = "down"
        lost.append(d)
        if state == "dead":
            break
    return {"hp": hp, "state": state, "lasting_injury": lasting, "damage": lost}


def heal(current: int, hp_max: int, amount: int) -> int:
    if hp_max < 1 or not 0 <= current <= hp_max or amount < 0:
        raise RuleError("bad heal input")
    return min(hp_max, current + amount)


def cast_cost(tier: str) -> int:
    return 3 * TIER_BONUS[tier]
