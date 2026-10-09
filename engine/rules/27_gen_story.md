## 27. Making a world — what is going on

```text
QUESTS    the player's first leads. At least one is MAIN. Every participant is a person id from the cast. Nobody must meet,
  fight or help for a quest to be solvable.
PRESSURES slow processes in the world that move whether or not the player acts: each has a clock (segments, pace
  "every <interval> while <condition>", first_check "YYYY-MM-DD HH:MM") sized to fit the whole span (a city-wide pressure moves in
  weeks, not nights), and on_fill = what the world does if nobody interferes. Zero is valid.
HIDDEN    something already true that the player does not know: the cause, what already happened, the evidence that follows from it,
  and at least two independent routes by which it could be found. Never evidence whose cause is undecided.
RIGHTS    ownership, custody, contracts, duties the player starts with. Parties are ids.
ENDINGS   only when the module bounded_scenario_endings is ON: what ends the story (core) and what ends it unseen (hidden).
  Otherwise both are [].
```
