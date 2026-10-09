# Design rule: world fact > dice > AI

This order is permanent. Every part of the program is built to enforce it, and `tests/test_authority.py` proves it.

1. **World fact.** What the records establish bounds every decision. A known fact is not rolled again, and an outcome that
   violates established reality is not allowed. *Enforced by:* verdicts must cite records that exist; a roll or question that was
   already resolved is reused, not rerolled, unless the AI states what materially changed; records may not lose established
   entries (relationships, knowledge, history, fields), shapes are checked, and program-owned values cannot be written by the AI.
2. **Dice.** They settle only genuine uncertainty, inside those bounds. The program freezes the stakes, then rolls. *Enforced by:*
   the order `wonder` (AI names the uncertainty) → program rolls → `react` (AI is told the result); every result is saved in
   the `resolved` ledger and shown to the AI in later rounds; a change to a path the result decides must say which result it
   depends on (`requires`) and the program rejects it if it disagrees; reversing a decided path later needs a stated cause.
3. **AI.** Judges, chooses consequences and tells the story inside both. *Enforced by:* the AI can only propose; the program
   validates the whole proposal on a copy and commits all of it or none of it; narration changes nothing; hidden records are not
   shown to the narrator; anyone learning something needs a channel; every change is journaled with its cause.

## What the program cannot check

It does not understand lore. The AI interprets the world and cites the records it relied on; the program checks that the records
exist and that what the AI then writes agrees with the dice and with the shapes the engine needs. Whether a consequence is
*sensible* inside a result's bounds, whether a stated channel is plausible, and whether a cited record really supports a verdict
stay the AI's judgement. They are visible in the journal (`journal.jsonl`: `events`) so a continuity error can be traced.

Model limits belong in the backend (prompts, retries, output format), never in the rules: a small model gets narrower tasks,
not permission to break them.


## Calendars

Time is the program's. A BACKGROUND writes every date in one of two ways:

1. Nothing special: `YYYY-MM-DD` (a fantasy world may use a year like `0482`).
2. Its own calendar, as a table the program computes from:

```yaml
calendar:
  era: Year                       # printed before the year
  months:                         # the whole year, in order
    - {name: Thawmonth, days: 30}
    - {name: Floodmonth, days: 31}
    - {name: Harvestwane, days: 29}
  leap: {every: 4, month: Thawmonth, extra: 1}     # optional
  weekdays: [Moonday, Fireday, Starday]            # optional
  start_weekday: Fireday                           # weekday of day 1 of month 1 of year 1
```

Dates are then written `Year 318, Floodmonth 6` (and `… 18:30`, `… dawn`) in `world_state.time.date`, plan notes (`state.due`) and pressure
first checks. `localgm/clock.py` turns them into day numbers, adds days across months, years and leap days, and prints them back. The AI is never asked to
convert or count a date; if it has to read a plan note at all, every date in the note must come back on the right day. The table is the program's
(`calendar` cannot be edited by the AI). The generator can fill the table from the idea and checks every date it writes against it.


## Hand-offs between AI calls

Each AI call is a new request: it knows only what the program puts in front of it. So every decision one call makes must be carried by the program to the
calls that need it, and a turn the program could not record is dropped, never narrated.

- The sorter's `note` (fast / retrieval / continuation) is passed to the telling as "THE GM'S DECISION"; a retrieval also gets the player's records.
- The world step's `report` (what happened, who did what and why, only what the player could perceive) is passed to the telling as "WHAT HAPPENED",
  after the program accepted the changes it proposed. Secrets named in it are refused.
- Results of dice and questions are passed to the next call as RESULTS; resolved ones are frozen in the ledger.
- A step the turn cannot do without that fails twice raises `TurnFailed`: no change is kept, the round does not advance. Only the self-check, the ten-round check and
  the recap may fail without dropping the turn.

## What an AI call looks like

Every AI call has the same shape, and the order matters because a model acts on what it reads last:

1. **System**: only the rule files that step needs to judge by (`engine/steps.yaml`, `rules:`), then the exact form to fill (`REPLY with one JSON object only: …`).
   The sorter, for example, gets 3 rule files, not the whole rulebook.
2. **Records**: only what that step needs. The sorter sees who is here and what they are doing, not their secrets; the judge, the question step and the world step also see the
   exact record paths they may cite or write, the place ids, and the player's own state.
3. **YOUR TASK NOW** (`engine/tasks.yaml`): what to do in this call, in a few short lines, with the options spelled out and one example from another game. This is the last thing
   the model reads before it answers.
4. On a retry, what the program refused and why.

Nothing here depends on the size of the model: a clear task, only the relevant records, and the exact spelling of what must be written help every model, and a strong model
simply has more room to be good inside it.
