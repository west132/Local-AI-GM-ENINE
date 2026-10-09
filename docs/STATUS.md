# What is built, what is not

Status of each V5 rule in the running program. A line here is true only if a test in `tests/` shows it.
`implemented` = the program does it and a test checks the effect on the saved world.
`partial` = some of it. `not yet` = the rule file tells the AI about it, but the program does nothing for it.

| V5 part | Status | Where / test |
|---|---|---|
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
| Real-model play over a long campaign | not tested | only a 3B coding model has been run, for a few turns |
