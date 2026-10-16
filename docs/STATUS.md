# Where the project stands, and what is built

Written after a full audit. Everything here is backed by a test, a recorded run, or is marked as not tested.

## 1. The goal
Turn the V5 text engine (written for web chat) into installable local software where **the program owns what must be exact**
(dice, state, time, calendar, saves, validation) and **a local AI model owns judgement and telling**. Standing rules: the order
**world fact > dice > AI**; dice only where an outcome could honestly go either way; the user changes settings and goes Home with buttons.

## 2. How it is built
- A turn can be played in two ways (Settings → "How each action is played"): **one form** (default; one call, two with dice or a person's answer) or the older **step-by-step** turn; both are in `engine/steps.yaml` and share all the program-side checks. The one-form style is covered by tests with scripted replies and by whole games with the practice GM; it has **not been played by a real model larger than 3B yet**.
- `engine/steps.yaml` is the only definition of a turn (each step: its rule sections, inputs, task, form and handler): sort → confirmed → judge → fight → wonder → react → offer → quest → injury → ending →
  checkpoint → tell → audit → epilogue (+ a start-up intake). `localgm/flow.py` walks it. Each step names its rule files, what the AI is shown,
  the form it must fill, and the program handler that validates and commits it. A refused reply goes back to the AI once with the reason.
- The program rolls every die, does every sum, keeps time (one calendar, or a world's own calendar table), money, supplies, XP, rest, healing,
  clocks, dues, saves; commits all-or-nothing on a copy; freezes resolved results in a ledger so they are not rerolled.
- The app reads the PC (graphics card and memory, RAM, threads) and the model file's header and picks layers on the card, context, cache type and threads (`backend.scan/read_gguf/plan_load/best_fit`; Settings → Performance settings: auto). Tested with synthetic model headers and a mocked driver reading; **not yet run on a real GPU or on Windows**, and it needs the CUDA build of llama-cpp-python to use a card.
- Backends: LM Studio / Ollama (OpenAI-style), an in-process .gguf, and a Demo that needs no model. A Windows-style app (Home, Settings, Play,
  rewind, Export/Import save, Make a new world, Check this model) writes `settings.json` itself.
- one rules file (27 sections), 167 tests, a browser check, an install check, a flow audit (`tools/audit_flows.py`). Install and run steps: `README.md`, `docs/INSTALL.md`.

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


## 8. Since the audit
- The sorter's `note`, the judge's reason and the world step's `report` are handed to the telling; a retrieval gets the player's records; a continuation runs the world step.
- A turn that cannot be recorded is dropped whole (`TurnFailed`); only the self-check, the ten-round check and the recap may fail without dropping it.
- Three ways to run the AI with one engine: model file (explicit CPU-only, threads), local server, online API with a key. Two switches cut AI calls per turn.
- Home shows whether the chosen AI passed "Check this model". README and `docs/INSTALL.md` were rewritten for all of this.
- Not yet run on a real model: the `report` / `note` hand-offs and the merged asking mode.


---

# Rule by rule: what is built, what is not

Status of each V5 rule in the running program. A line here is true only if a test in `tests/` shows it.
`implemented` = the program does it and a test checks the effect on the saved world.
`partial` = some of it. `not yet` = the rule file tells the AI about it, but the program does nothing for it.

| V5 part | Status | Where / test |
|---|---|---|
| Authority order world fact > dice > AI (`docs/DESIGN.md`): cited records must exist; resolved rolls/answers are frozen in a ledger and not rerolled unless something material changed; a change to a path a result decides must declare and match that result; reversing it later needs a cause | implemented | `tests/test_authority.py` |
| Someone learning something needs a channel; every change is journaled with cause/channel/requires | implemented | `test_someone_learning_something…` |
| Established records cannot lose entries (relationships, knowledge, drives, history, fields); plan, injury, equipment, skill shapes are checked | implemented | `test_established_records_cannot…`; the hostile-model fuzz (60 rounds on each of the 5 worlds) checks it with an independent oracle, and fails if the check is switched off |
| Dice only where the outcome could honestly go either way: every question carries an `obvious` answer; if there is one it stands and nothing is rolled (settled answers are fixed in the ledger like rolls); the AI may ask again after seeing a result (no cap on questions, 4 ask-rounds per turn only to stop a loop) | implemented | `tests/test_dice_use.py`. Whether an answer is really obvious is the AI's judgement; the rule text (AI_RULES v4.2 lines) is in section 19 of `engine/rules.md` |
| Faults found in the Ashfall R1–R10 run A: narrator blind to what the player learned; narrator told offscreen lives; scene printed twice; free-text positions; fight without scene; kill orders; plan op refused falsely and timed before the action; NPC rest; NO,BUT vs NO | implemented | `tests/test_run_findings.py` |
| Model check (7 fixed situations, each step's form checked as the program will check it in play; verdict per model) | implemented | `tests/test_modelcheck.py`, Settings page button. Not yet run on a real model |
| Roll before the question it depends on (the roll step runs before the question step) | not yet | the AI can ask again in `react`, but a roll cannot wait for an answer |
| Dice, check, odds, ask, XP, growth, HP, damage, time | implemented | `mechanics.py`; identical to the V5 helper on ~10k compared cases: `python tools/compare_v5.py <path to engine_math_v5_0.py>` |
| Roll, then consequence (AI told the result before it writes outcomes) | implemented | step order in `steps.yaml`; `test_the_ai_sees_the_ask_result…` |
| One workflow definition (`steps.yaml` runs the turn; handlers are a registry) | implemented | `test_the_yaml_is_the_whole_workflow` |
| All-or-nothing commit; shape checks; no record replaced or deleted; crash leaves the save untouched | implemented | `test_owned_paths_and_bad_shapes…`, `test_the_real_world_is_untouched…` |
| Failed roll with harm → HP in code | implemented | `test_a_failed_roll_costs_hp…` |
| Odds stop (risky roll waits for the player) | implemented | `test_odds_stop_waits…` |
| Capability from level + skill tier + gear in numeric worlds (A, B); no ToolMod with gear | implemented | `test_capability_is_computed…` (player rolls and fights). Worlds without numeric levels: the AI's band stands |
| Skill evidence from a win, once per skill per period | implemented | `test_a_failed_roll_costs_hp…` |
| Skill tier and class growth at a boundary (sleep, training, aftermath); class needs a source; new period | implemented | `test_sleep_is_a_growth_boundary…`, `test_class_rises_only_with_a_valid_source`. Player only; companions are not tracked |
| XP: event, combat (once per foe, level at the start) and quest (once, stored) | implemented | `test_a_won_roll_with_a_challenge…`, `test_combat_xp…`, `test_completing_a_quest_pays_its_xp_once`. Event XP has no per-event id guard beyond the single roll |
| Rest and sleep recovery of HP; someone who is down needs treatment, not rest | implemented | `test_rest_heals…` |
| MP: maximum, cost of a cast (paid even if it fails, power tier ≤ skill tier), recovery by the setting's mode (fast / slow / rest_only) | implemented | `test_max_mp_and_the_cost…`, `test_a_cast_without…`, `test_mp_recovers…` |
| Down for an hour untreated → 2d10 survival roll; stabilising or healing prevents it | implemented | `test_down_for_an_hour…`, `test_a_failed_survival_roll…` |
| Healing items and powers (dice by source, capped at maximum) | implemented | `test_healing_a_standing_person…` |
| Lasting-injury healing: only after real treatment for its full time (3 days, 7 if deep), settled at a growth boundary | implemented | `test_a_lasting_injury_heals_only_after…` |
| Supplies: exact counts, usage die (low roll steps it down, empty is exhausted, resupply must raise it) | implemented | `test_usage_die_steps_down…` |
| Payoffs (`pending_payoffs`), fatigue, food and water, equipment condition, acquisition | AI judgement per the rule files | the AI writes the records; the program only protects cash, supplies and the other program-owned fields. Nothing checks a payoff is not paid twice |
| Lasting injuries: the AI names it (home must be one of the seven), the program records it | implemented | `test_a_heavy_hit_makes_the_ai_name_an_injury…`. Whether the effect is then counted once is the AI's judgement (I8) |
| Quests: required fields and enums, one open MAIN, closed stays closed, immutable level, child refs, level required for SHORT in numeric worlds | implemented | `test_quest_rules_are_enforced_on_commit` |
| New generated offer: the program rolls the shape; the quest must match | implemented | `test_a_new_offer_is_rolled…` |
| Quests: deriving the level, solvability, support, payoffs (`pending_payoffs`), segment XP edge cases | not yet / AI judgement | |
| Trackers | implemented | `test_quest_step…` |
| Money | implemented | `test_money_and_time…` |
| Time and actor dues, incl. dues that fall during an action | implemented | `test_a_due_that_falls…` |
| Pressure clocks (AI judges "operated", program fills and reschedules) | implemented | `test_a_due_clock…`; on-fill consequences are given to the AI to resolve |
| Item entitlement: price set by the program, reserve checked, item added, gains capped 1–4 with a named source | implemented | `test_item_points_buy_one_detail…`. Whether the reason is valid and the detail unestablished is the AI's judgement |
| Equipment tier boost | implemented | see capability row |
| Bounded endings: conditions fixed at start, met/closed tracked by the program, scenario ends, closed stays closed | implemented | `test_a_met_ending_ends…`, `test_closed_endings…`. Whether a condition is met is the AI's judgement |
| Hidden truth: hidden records and their changes are not given to the narrator; a story naming a name only hidden records hold is sent back, then cut | implemented for proper names | `test_secret_names_are_found…`, `test_records_of_hidden_things…`. A paraphrase of a secret without its name is caught only by the audit step |
| Sorting floor: naming a person who is here is never a fast action | implemented | `test_naming_a_person…` |
| Open-question rules (yes/no, likelihood needs a fact) | implemented | `test_wh_question…` |
| Fights (exchanges, damage, soak, down/dead) | partial | `combat.py`; morale and per-attacker budgets are the AI's judgement |
| Ten-round checkpoint: open quests, obligations and settled questions are listed for the AI to close or keep; commits by the program | implemented | `tests/test_checkpoint_companions.py`. Whether an item is really settled is the AI's judgement |
| Ending recap (epilogue step) when a scenario ends | implemented | `test_checkpoint_companions.py` |
| Companions: XP and growth tracked by the program, joined/left by typed changes | implemented | `test_checkpoint_companions.py` |
| Ask first, roll second: a judge verdict `ask` runs the question loop before any roll; no cap on the number of asks; obvious answers are settled without dice | implemented | `test_dice_use.py`, `test_authority.py` |
| Save import from a V5 chat save (Part A + capsule over the BACKGROUND), export back to a SAVE file, CRLF-safe | implemented | `tests/test_savefile.py` on the real R10 save; `tools/ui_check.py` imports it through the page. Round-trip is of the tree the program holds, not of every wording of a chat save |
| Work source routine (a fixer/guild/patron's weekly "did work come in?" check, owned by the program, survives a replan) | implemented | `test_work_source_check…`. The AI answers the question; the program schedules it |
| Temper of a new non-BACKGROUND actor: 2d10 ≥ 17 (≥ 15 opposing), rolled once, kept | implemented | `test_new_actor_temper…`. Combat foes created by the fight step are not rolled |
| World generator: six checked forms from a short idea (premise, price list, player, places, cast, story); full names, genders, prices, module choice, dues, starting abilities of the source game, references all checked; the program writes the BACKGROUND | implemented, tested with scripted answers | `tests/test_generate.py`, `tools/ui_check.py`. **Not tried on a real model.** Whether the AI knows a source game's real starting abilities is its own knowledge; the program only checks they are listed and held by a skill |
| Calendars: the default is `YYYY-MM-DD`; a world may define its own as a **table** in the BACKGROUND (`calendar:` era, months with days, optional leap rule, optional weekdays). The program converts every written date, moves the date through the table as time passes and shows it in the header; the AI never does date arithmetic. A bad table is refused with the reason. Plan notes and pressure first checks are read by the program (no AI call needed on the example worlds, except an actor with no plan at all); when the AI does read a note, each date in it must come back on the right day or the answer is refused | implemented | `tests/test_calendar.py`, `test_the_program_reads_dated_notes_itself`, `test_no_example_world_needs_the_ai_to_read_a_date`. Tarnstead and Last Scion are written in `YYYY-MM-DD` (their own month tables were never in the files, and I did not invent a world's calendar for it) |
| Mechanical output errors are the program's: cut-off JSON is closed and checked field by field, every array in a form has a length limit, a step named twice runs once, `confirm` with nothing pending and a telling that repeats the player are refused, the telling is told who the player character is | implemented | `test_a_reply_cut_off…`, `test_arrays_in_a_form…`, `test_confirm_with_nothing_pending…`, `test_the_telling_is_told_who…` |
| The sorter's decision is never dropped: `fast`, `retrieval` and `continuation` must carry a `note`; the program hands it to the telling as "the GM's decision"; a retrieval is also given the player character's records to answer from; a continuation always runs the world step (time passes, dues fall, people answer) | implemented | `test_the_sorters_decision_reaches_the_telling`, `test_a_quiet_kind_without_a_note_is_sent_back`, `test_a_retrieval_is_answered_from…`, `test_carrying_on_takes_time…` |
| Three ways to run the AI with one engine: a model file inside the app (`device: cpu` = never use a graphics card, `threads`), a local server (LM Studio / Ollama), an online API with a key (sent only as a header, hidden on the page, never in prompts, logs or error texts) | implemented, tested against a fake server and a fake library | `tests/test_backends.py`, `tools/ui_check.py`. **No real commercial API was called** |
| Fewer AI calls per turn on slow computers: `merge_questions` (the world step asks its open questions itself, no separate asking call) and `check_telling` (skip the self-check call) | implemented; the merged mode is **not yet tried on a real model** (run A and A2 used the separate asking call) | `test_fewer_calls_per_turn_when_asked`, `test_a_merged_world_step_can_ask_and_then_decide` |
| A turn that cannot be recorded is dropped whole: if a step the turn cannot do without (everything except the self-check, the ten-round check and the recap) fails twice, the program raises, keeps nothing and does not advance the round; the page says which step failed and to send the action again. No half-turn is narrated | implemented | `test_a_turn_whose_ops_are_refused_twice_is_dropped_whole`, `test_a_reply_that_is_never_a_usable_form_drops_the_turn_too`, the hostile-model fuzz |
| The world step hands the telling an account: every reaction carries a `report` (who did what and why, only what the player could perceive); it is refused if missing or if it names a hidden thing the player has not learned; the telling is built from it and the program's recorded results, with "add nothing that is not in the account" | implemented | `test_the_gms_account_reaches_the_telling…`, `test_a_reaction_without_an_account…`, `test_a_report_that_names_a_hidden_thing…` |
| Home shows whether the chosen AI passed "Check this model" (a result belongs to one model on one backend); starting a game on an unchecked or weak AI asks first | implemented | `test_home_knows_whether_this_ai_was_checked` |
| The same scripted game gives the same world, telling and account through the direct call, the OpenAI-style HTTP adapter and the model-file adapter | implemented against fake servers/libraries | `test_the_same_game_gives_the_same_world_through_every_adapter`. Not run with a real model on any adapter |
| Fewest AI calls per turn (with both call-saving choices on): quiet action 2, world reaction 3, with an open question 4, with a roll 4 | implemented, counted in a test | `test_how_many_ai_calls_a_turn_needs` |
| The whole system together: the practice GM (`localgm/simgm.py`, also the `demo` backend) plays whole games, reading the real prompts, through all five bundled worlds, a made world and an imported chat save, with rewind and export/import in the middle; after every turn `localgm/coherence.py` must find the world in agreement with itself (player somewhere real, no plan that can never happen, companions with the player, no missed due or clock, hp/cash in range, one MAIN quest, every change journaled) | implemented | `test_a_whole_game_keeps_the_world_in_agreement_with_itself` (x5), `test_a_game_can_be_rewound_exported_imported_and_carried_on`, `test_a_made_world_and_an_imported_save_play_too`. The practice GM is plain; it proves the parts connect, not that a model plays well. Warnings also show under each turn in the app |
| The test suite passes on Python 3.10 (the minimum) and 3.13 | verified | run in a 3.10 virtual environment |
| Install in a clean folder and fresh virtual environment, then start | tested on Linux | `tools/install_check.py`. **start.bat was not run on Windows**; it was reviewed and given CRLF line endings |
| Whether a consequence is sensible inside a result's bounds; whether a cited record really supports a verdict | AI judgement | visible in the journal |
| Real-model play over a long campaign | not tested | only a 3B coding model has been run, for a few turns |
