# What is built, what is not

Status of each V5 rule in the running program. A line here is true only if a test in `tests/` shows it.
`implemented` = the program does it and a test checks the effect on the saved world.
`partial` = some of it. `not yet` = the rule file tells the AI about it, but the program does nothing for it.

| V5 part | Status | Where / test |
|---|---|---|
| Authority order world fact > dice > AI (`docs/DESIGN.md`): cited records must exist; resolved rolls/answers are frozen in a ledger and not rerolled unless something material changed; a change to a path a result decides must declare and match that result; reversing it later needs a cause | implemented | `tests/test_authority.py` |
| Someone learning something needs a channel; every change is journaled with cause/channel/requires | implemented | `test_someone_learning_something…` |
| Established records cannot lose entries (relationships, knowledge, drives, history, fields); plan, injury, equipment, skill shapes are checked | implemented | `test_established_records_cannot…`; the hostile-model fuzz (60 rounds on each of the 5 worlds) checks it with an independent oracle, and fails if the check is switched off |
| Dice only where the outcome could honestly go either way: every question carries an `obvious` answer; if there is one it stands and nothing is rolled (settled answers are fixed in the ledger like rolls); the AI may ask again after seeing a result (no cap on questions, 4 ask-rounds per turn only to stop a loop) | implemented | `tests/test_dice_use.py`. Whether an answer is really obvious is the AI's judgement; the rule text (AI_RULES v4.2 lines) is in `engine/rules/19_play_lessons.md` |
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
| One calendar: a BACKGROUND writes every date as `YYYY-MM-DD [HH:MM / dawn / noon …]`; the program turns plan notes and pressure first checks into dues, triggers and clocks itself (no AI call needed on the example worlds, except an actor with no plan at all); when the AI does read a note, each date in it must come back on the right day or the answer is refused | implemented | `test_the_program_reads_dated_notes_itself`, `test_no_example_world_needs_the_ai_to_read_a_date`, `test_the_ai_cannot_move_a_date…`. Tarnstead and Last Scion were converted from their own calendars (`Year 318, Floodmonth 6` is now `0318-01-06`) |
| Mechanical output errors are the program's: cut-off JSON is closed and checked field by field, every array in a form has a length limit, a step named twice runs once, `confirm` with nothing pending and a telling that repeats the player are refused, the telling is told who the player character is | implemented | `test_a_reply_cut_off…`, `test_arrays_in_a_form…`, `test_confirm_with_nothing_pending…`, `test_the_telling_is_told_who…` |
| Install in a clean folder and fresh virtual environment, then start | tested on Linux | `tools/install_check.py`. **start.bat was not run on Windows**; it was reviewed and given CRLF line endings |
| Whether a consequence is sensible inside a result's bounds; whether a cited record really supports a verdict | AI judgement | visible in the journal |
| Real-model play over a long campaign | not tested | only a 3B coding model has been run, for a few turns |
