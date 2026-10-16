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

1. **System**: only the rule files that step needs to judge by (`engine/steps.yaml`, `rules:` → sections of `engine/rules.md`), then the exact form to fill (`REPLY with one JSON object only: …`).
   The sorter, for example, gets 3 rule files, not the whole rulebook.
2. **Records**: only what that step needs. The sorter sees who is here and what they are doing, not their secrets; the judge, the question step and the world step also see the
   exact record paths they may cite or write, the place ids, and the player's own state.
3. **YOUR TASK NOW** (the step's `task:` in `engine/steps.yaml`): what to do in this call, in a few short lines, with the options spelled out and one example from another game. This is the last thing
   the model reads before it answers.
4. On a retry, what the program refused and why.

Nothing here depends on the size of the model: a clear task, only the relevant records, and the exact spelling of what must be written help every model, and a strong model
simply has more room to be good inside it.

## Two ways to play a turn

`turn_style` in Settings picks how an action is asked of the AI; the program around it (dice, arithmetic, time, ledger, owned paths, all-or-nothing commit, leak filter, coherence check) is the same.

- **one** (default): `single:` in `engine/steps.yaml`. One form with a `mode`: `done` (record the changes and tell the scene, in the same reply), `roll`, `ask`, `fight`, `decision`, `confirm`. Only `done` is final.
  For the other modes the program does its part (rolls, answers, fights, stops for the player) and asks the same form again with the results under RESULTS, so a turn is one call, two when dice or a person's answer are needed
  (a new offer's shape and a due that fell during the action can add one more). A `done` reply is checked as a whole *before anything is recorded*: the telling (labels, headings, words put in the player's mouth, secrets),
  the report, the typed fields, the ops against the ledger and the owned paths; if any part fails the AI is sent back with the reason and nothing was kept. At most three rolls, questions or fights per turn, then it must decide.
  The prompt carries the rules (about 14,000 tokens) first in the system text, and every call of the turn (also the re-reading, the ten-round check, the recap and a retelling) starts with that same text, so a server or library that keeps the start of the last prompt reads it once, not once per call; this needs a context of at least 24,576 tokens (32,768 recommended).
  The last five exchanges (the player's line and what the AI told, shortened) are kept in the save as `recent_turns` and shown as THE STORY JUST NOW. They are the AI's continuity, not part of a save file (export leaves them out), and the AI cannot write them.
- **steps**: `turn:` in the same file, the older pipeline (sort, judge, fight, wonder, react, offer, quest, injury, ending, tell, audit): shorter prompts, more calls.

## Reading the PC (automatic settings)

`backend.scan()` reads the graphics card (name, memory total/free, through the driver's `nvidia-smi`; Apple silicon counts 70% of its shared memory), RAM and processor threads, and whether the installed llama-cpp-python can use a card at all.
`backend.read_gguf()` reads a model file's header (size, layers, attention heads, context it was trained for) without loading it, which gives the cost of the attention cache per token.
`backend.plan_load()` then picks, in order of preference: everything on the card with a 32768 context; the cache in 8-bit to make room; a 24576 context; and only then some layers left to the processor (slow, and refused if RAM cannot hold the rest).
`best_fit()` chooses the largest file in `models` that sits wholly on the card. With **Performance settings: auto** (default) `backend.make` uses the plan; **manual** uses the three fields on the Settings page.
This is arithmetic from the file and the card, not a speed benchmark; real speed also depends on the model and the library build, and the memory figures are estimates (the card's free memory at the time of the scan is what counts).
With LM Studio as the engine the page only prints the figures to set there (GPU offload, context length): LM Studio does the loading.

## How the parts fit together

**Where each thing lives (one place each).** `engine/steps.yaml`: the turn: for every step its rule sections, what the AI is shown, its task, its form and the program handler.
`engine/rules.md`: all judgement rules, numbered sections. `engine/generate.yaml`: the six world-making forms. `localgm/flow.py` runs the turn; `rules.py`, `state.py`, `combat.py`, `clock.py`,
`mechanics.py` hold the arithmetic and the records; `coherence.py` checks the whole world agrees with itself; `simgm.py` is a practice GM with no AI.

**A turn, end to end** (steps style; the one-form style folds sort, judge, fight, wonder, react, quest, injury, ending and tell into one form and keeps everything after it). player words → *sort* (note) → *judge* (verdict, roll set-up, asks) → program rolls / settles → *fight* → *wonder* → program answers → *react* (report, ops, time, move)
→ program validates and commits all or nothing → dues that fell are decided in a second pass → *tell* (from the note / report / results) → *audit* → coherence check.
Every arrow is a hand-off the program carries; nothing is passed by a model "remembering".

**What keeps the parts honest together** (each one was added because a real run or test found the parts disagreeing):
- the AI is shown exactly what it must cite or write: record paths, place ids *with names*, the player's state;
- the second look of a turn (things that fell due while the action happened) is told the action is already done;
- a long jump owes a check for every interval that passed, filled in the same turn (one decision from the AI, the program fills the segments);
- the made-world generator writes only what the engine derives itself (it does not write hp), and everything the engine requires (a quest level);
- `coherence.check` after every turn: the player is somewhere real, nobody has a plan that can never happen, nobody travelling with the player is left behind, no due or clock was missed,
  hp and cash are in range, one MAIN quest, results point at records that exist; and between turns time only moves forward and every changed record has a cause on the journal.
  Anything found is shown under the turn and kept in the journal.
- whole games (all five bundled worlds, a made world, an imported chat save, rewind and export/import in the middle) are played through the real loop by the practice GM, and every turn
  must leave the world in agreement with itself (`tests/test_loops.py`, "whole games").
