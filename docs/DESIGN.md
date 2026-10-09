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
