# Where the project stands

Written after a full audit. Everything here is backed by a test, a recorded run, or is marked as not tested.

## 1. The goal
Turn the V5 text engine (written for web chat) into installable local software where **the program owns what must be exact**
(dice, state, time, calendar, saves, validation) and **a local AI model owns judgement and telling**. Standing rules: the order
**world fact > dice > AI**; dice only where an outcome could honestly go either way; the user changes settings and goes Home with buttons.

## 2. How it is built
- `engine/steps.yaml` is the only definition of a turn: sort → confirmed → judge → fight → wonder → react → offer → quest → injury → ending →
  checkpoint → tell → audit → epilogue (+ a start-up intake). `localgm/flow.py` walks it. Each step names its rule files, what the AI is shown,
  the form it must fill, and the program handler that validates and commits it. A refused reply goes back to the AI once with the reason.
- The program rolls every die, does every sum, keeps time (one calendar, or a world's own calendar table), money, supplies, XP, rest, healing,
  clocks, dues, saves; commits all-or-nothing on a copy; freezes resolved results in a ledger so they are not rerolled.
- Backends: LM Studio / Ollama (OpenAI-style), an in-process .gguf, and a Demo that needs no model. A Windows-style app (Home, Settings, Play,
  rewind, Export/Import save, Make a new world, Check this model) writes `settings.json` itself.
- 27 rule files, 144 tests, a browser check, an install check, a flow audit (`tools/audit_flows.py`).

## 3. What we went through
1. **Port** the V5 turn into an executable form; mechanics checked against V5's helper (`tools/compare_v5.py`).
2. **Authority and dice**: world fact > dice > AI enforced (ledger, `requires`/`governs`, hostile-model fuzz); the user pointed out dice were overused,
   so the AI's play lessons were restored, every question carries an `obvious` answer, and a roll can wait for its question (`verdict: ask`).
3. **Missing V5 rules completed**: growth boundary, rest, MP, survival, healing, supplies, quests, entitlement, endings, hidden truth, injuries, XP, companions,
   ten-round check, ending recap, work-source routine, temper.
4. **Runs on your Ashfall world** (same ten inputs, real dice, nothing edited): run A (Claude as the AI), run B (a 3B model), run A2 (Claude again on the fixed engine).
5. **Save import/export** (your real R10 save loads; export round-trips), **world generator** (six checked forms), **install check**.
6. **Your corrections**, each of which changed the code: the 3B misreading the background (dates, roles) showed that mechanical work must not depend on the
   model: the program now reads dates and calendars itself (and a world may define a calendar table), closes cut-off JSON, caps array lengths, tells the
   narrator who "you" is, refuses `confirm` with nothing pending.

## 4. What the runs showed
| | A (first engine) | A2 (fixed engine) | B (3B) |
|---|---|---|---|
| inputs completed | 10/10 | 10/10 | stopped at 7 (container restart); 4 accepted, 3 refused |
| open-question dice | 10 | 5 (+7 settled without dice) | – |
| quality | coherent | coherent | accepted rounds were wrong (roles confused, no background applied) |

Faults found by running, all fixed with tests: nine in A; in A2 the player was never moved, fight-overshoot noise; in B the sort step answered `confirm` with
nothing pending, the telling was never told who the player is, the start-up step got 13 of 22 dates wrong or lost, replies were cut off mid-JSON.

## 5. The audit (this pass)
Found and fixed:
- `02_directive.md` ("no outcome is protected", the priority order) was loaded by **no step**. Now loaded by sort, judge, wonder, react.
- The judge form's **decision gate** (`decision`) was never read. Now it stops the turn, shows the question and options, rolls nothing.
- The `requires.on` key was parsed by YAML as boolean `True` in two schemas, so a grammar-constrained model could not write `on`. Fixed; every
  schema key is a string.
- A name where an id belongs (`heal: Nadia Voss`) crashed a round with a raw `KeyError`. Now any such reply is sent back as a refusal.
- No test ran the fight, supply, clock-fill or chain paths through a whole turn. `tests/test_loops.py` runs **every step in a real turn** and fails if one never runs.
- `tools/audit_flows.py` checks that every step has a handler, every rule file is loaded, every form field is read by the program, and `sort`'s step list matches
  the steps that wait for it. Result: ALL WIRED.

## 6. Does the AI model work as designed?
- **The loop itself: yes**, shown by tests that run every step with scripted answers, by the fuzz, and by two full ten-round runs with a strong model (10/10 accepted, no crashes).
- **A strong model: yes** for judgement within the design (asks before rolls, obvious answers settled, consequences recorded, facts told).
- **The 3B coding model: not usable.** Model check today (Settings → Check this model): **5/7, "usable, with refusals"**; it cited records that do not
  exist and wrote a path the program rejects. In the play run it confused who was who. The program now stops the mechanical failures (dates, JSON, ids, identity)
  but cannot make it judge well.
- **A 14B: not tested.** I will not assume it passes. The mechanical failures that sank the 3B no longer depend on the model; judgement quality is the open question,
  and the model check plus one ten-round run on your machine will answer it.

## 7. Not done / not tested
- Any real 14B; `start.bat` on Windows (the install flow passes on Linux); the world generator on a real model; Tarnstead and Last Scion in their own calendars
  (the tables were never written); prompt size is about 23k tokens per round before any trimming.
