# Map from NEW ENGINE v5.0 to the local engine

The local engine is `engine/steps.yaml` (the turn, in the form the program executes) plus `engine/rules/NN_*.md` (the judgement rules each step loads). Rule files have their own numbers (01–15). V5 numbers appear only in this file.
Every V5 section ends up in exactly one of: **AI** (kept as a rule file loaded by a step), **CODE** (the program does it, the AI never sees it), **DROP** (existed only because V5 was written for a web chat).

## A. Local section → V5 source

| Rule file | Title | Taken from V5 | Changed |
|---|---|---|---|
| 1 | Your job and the program's job | 1 (Directive), 2 (loop), 6 (ownership) | New. States the split: program rolls/sums/keeps; AI judges/tells. |
| 2 | Directive | 1 | Tightened. |
| 3 | Rules that always hold | 5 (Invariants) | I1–I12 labels kept; wording tightened; rules about formatting/records removed (code enforces them). |
| 4 | What is true | 4 (Authority), 3 (Vocabulary) | Only the terms the AI actually uses. |
| 5 | The player's side | 7 (Player agency) | Agency, fighting style, execution order, authority kept. Override setting is a program flag. |
| 6 | Sorting what the player does | 2.1 (which section to open) | Rewritten as sorting into FAST / LOOP / RETRIEVAL / CONTINUATION, decision gate, STUCK menu. V5 "open section X" is gone: the program decides what to load. |
| 7 | Is it possible? | 10.1, 10.2 | Kept; one-factor-one-place table kept. |
| 8 | Setting up a roll | 10.3 | Only the AI's part: capability bands, difficulty base/category, tool modifier. Dice, sums, outcome bands → CODE. |
| 9 | Stakes | 10.4 | Cost/reach, odds stop kept. |
| 10 | Fights | 12 | Plan, exchange, attack budget, morale kept. Damage/HP arithmetic → CODE. |
| 11 | People and factions | 13.1 | Plan/due, replan, work source, difficult new actor, open questions + likelihood bands, influence, identity, standing, attitude, romance, NPC growth, routines, familiarity, canon mode, companions. |
| 12 | The world moves | 13.3–13.9 | Time costs, what happens next, places, pressures/clocks, cases/hidden truth, witnesses, character/values, development threads. Calendar and due-date arithmetic → CODE. |
| 13 | Quests | 14.1, 14.2, 14.4 | Level, sources, shape roll request, accept/reject, close, arc end. Trackers (14.3) → CODE. |
| 14 | Endings | Module C | Optional. |
| 15 | Telling it | 9 (Narration), AI_RULES language and narration craft | Narration rules, craft, language. |

## B. V5 section → where it went

| V5 | Where |
|---|---|
| 1 Directive | AI (2) |
| 2 The loop | CODE: the program runs the loop |
| 2.1 Which section to open | CODE: the program loads what the turn needs |
| 2.2 What a turn emits | CODE: headers, roll lines, numbering |
| 2.3 The helper | CODE: `engine_math_v5_0.py` pieces are reused |
| 3 Vocabulary | AI (4), reduced |
| 4 Authority | AI (4) |
| 5 Invariants | AI (3); the checkable ones are also enforced by code |
| 6 Ownership | AI (1) as the split; the table of who owns which field → CODE schema |
| 7 Player agency | AI (5) |
| 8 Rounds | CODE: round counter, journal |
| 8.1 GM-Δ and capsule | CODE: built from the changes the AI reports; the AI never writes the chain |
| 9 Narration | AI (15) |
| 10.1, 10.2 | AI (7) |
| 10.3 The roll | AI (8) for the inputs; CODE for dice and outcome |
| 10.4 Stakes | AI (9) |
| 10.5 Vitals | CODE |
| 11 Skill growth | CODE: evidence, accrual, level-up; the AI only says what the player used |
| 12 Combat | AI (10) for decisions; CODE for the numbers |
| 13.1 Actors | AI (11) |
| 13.2 Time | CODE |
| 13.3–13.9 | AI (12) |
| 14.1, 14.2, 14.4 | AI (13) |
| 14.3 Trackers | CODE |
| 15 Consequences and resources | CODE: money, items, resources; the AI reports what was spent or gained |
| 16.1–16.5 Persistence, new game, checkpoints, projection, loading | CODE |
| 16.6 Revising Round-0 | CODE: edit a record, re-validate |
| 16.7 Repairing a GM error | **DROP**. Replaced by validation before a record is applied. |
| A Numeric level and XP | CODE |
| B Equipment tiers | CODE |
| C Endings | AI (14) |
| D Item entitlement | CODE |
| Versioning | DROP (the program has its own version) |

## B2. AI_RULES v5.0

The first derivation left AI_RULES out except for language and narration. It holds the lessons added after models went wrong in play,
including the dice rule ("decide the obvious; never roll to avoid being the one who said yes"). They are now `engine/rules/19_play_lessons.md`
(the lines about judging and playing; tool, save and language lines are the program's), loaded by the sort, question, reaction and fight steps.

## C. Why this split

Measured on the V5 engine text (token estimates, same method on every section):

- AI-owned sections ≈ 11k tokens. These are engine/rules/.
- CODE sections ≈ 11k tokens. They stop being prompt text and become program logic.
- DROP ≈ 1k tokens.

Measured on 120 real rounds of a played save: about 90% of all record changes were judgement records (people 59%), not arithmetic. That is why the AI side stays large and the arithmetic side moves out.

## D. Not yet checked

See `docs/STATUS.md` for the per-rule status; this map only says where a rule went, not that it is finished.


- The local engine text has not been run against any model yet.
- The CODE list above is a plan. Each item has to be built and tested before it is true.
