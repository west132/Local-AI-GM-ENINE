## 8. Setting up a roll

You supply the facts; the program does the sums and rolls. Freeze them before the dice; they do not
change afterwards. If the action materially changes before the roll, set it up again.

```text
ACTOR AND ACTION · Challenge and its source (when numeric) · where the capability comes from ·
skills exercised · support or opposition in use · the difficulty profile · CapabilityMod ·
a nonzero ToolMod and its source · the stakes (section 9)
```

```text
CapabilityMod, with numeric progression and a valid Challenge: the program takes the gap between
  actor capability and Challenge.
CapabilityMod, otherwise: the actor's ABSOLUTE capability in this domain, never against the task (I8)
  severely deficient but feasible −4 | limited/basic −2 | trained/competent 0
  | advanced/master +2 | exceptional/setting-top +4
  tiers, traits, expertise, setting limits are evidence for the band, not 1:1
  a missing binary capability → knowledge gate, not −4
  overall level never grants capability in an unrelated domain
```

```text
Difficulty counts execution conditions only (task or opponent power is in Challenge).
base  10 with a valid numeric Challenge; otherwise the task's own difficulty:
  5 forgiving · 8 easy · 10 ordinary · 13 awkward · 15 demanding · 17 severe · 20 extreme
  (one adverse condition on ordinary work = 11)
categories: environment/access · time/interruptions · sensory/evidence · position/control ·
  simultaneous constraints
each category: +1 adverse · +2 severely adverse (rare) · −1 favourable · 0 neutral, mixed, ambiguous
the program clamps the total; with a numeric Challenge the final Difficulty stays in 7–13
a category keeps its value until its fact changes; no creep across a scene (I8)
each category counts once; a nonzero one needs a concrete state fact that independently changes
  execution and is counted nowhere else; name each one in the profile
THREAT  the threat that sets the cost (attacker, hazard, pursuer) is stakes; its pressure,
  attention, urgency are never a penalty; physical conditions it creates (smoke, rubble) still count
NEVER  raised to enable skill growth
```

```text
ToolMod: fit — seriously unsuitable −2 | poor/makeshift −1 | normal 0 | good +1 | exceptional +2
  condition — serviceable 0 | worn/damaged −1 | critical but usable −2   (the program clamps to −2..+2)
  an unusable item → feasibility fails, not −2 · bodily condition is never ToolMod
  equipment-tier power is never also ToolMod
RESULT  genuine randomness only (I10): no fudging, hidden reroll, or convenience success;
  there is no critical-success tier; the Challenge value may stay hidden
```
