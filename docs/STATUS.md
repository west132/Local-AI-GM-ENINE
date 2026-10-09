# What is built, what is not

Status of each V5 rule in the running program. A line here is true only if a test in `tests/` shows it.
`implemented` = the program does it and a test checks the effect on the saved world.
`partial` = some of it. `not yet` = the rule file tells the AI about it, but the program does nothing for it.

| V5 part | Status | Where / test |
|---|---|---|
| Dice, check, odds, ask, XP, growth, HP, damage, time | implemented | `mechanics.py`; identical to the V5 helper on ~10k compared cases (script in session history, not in repo) |
| Roll, then consequence (AI told the result before it writes outcomes) | implemented | step order in `steps.yaml`; `test_the_ai_sees_the_ask_result…` |
| Failed roll with harm → HP in code | implemented | `test_a_failed_roll_costs_hp…` |
| Skill evidence from a successful roll (once per period) | implemented | same test |
| XP award on a win (numeric-level worlds) | partial | code path exists in `_resolve`; no test yet |
| Skill tier / class growth at a boundary | not yet | `mechanics.grow` exists but nothing calls it |
| Odds stop (risky roll waits for the player) | implemented | `test_odds_stop_waits…` |
| Money | implemented | `test_money_and_time…` |
| Time and actor dues, incl. dues that fall during an action | implemented | `test_a_due_that_falls…` |
| Pressure clocks (AI judges "operated", program fills and reschedules) | implemented | `test_a_due_clock…`; on-fill consequences are given to the AI to resolve, not enforced |
| Trackers | implemented | `test_quest_step…` |
| All-or-nothing commit, shape checks, no record deleted or replaced | implemented | `test_owned_paths_and_bad_shapes…` |
| A crashed turn leaves the saved world untouched | implemented | `test_the_real_world_is_untouched…` |
| Fights (exchanges, damage, soak, down/dead) | partial | `combat.py`; morale and per-attacker budgets are the AI's judgement only |
| Lasting injuries | partial | the program says one is owed; recording it is left to the AI |
| Open-question rules (yes/no, likelihood needs a fact) | implemented | `test_wh_question…` |
| Hidden truth / cases / witnesses | not yet | the AI sees the records; nothing checks that narration respects them beyond the audit step |
| Quests: levels, shape roll, accept/reject | not yet | rule text only; ops are validated for shape, not for quest rules |
| Equipment tiers, flexible item entitlement, endings module | not yet | |
| Real-model play over a long campaign | not tested | only a 3B coding model has been run, for a few turns |
