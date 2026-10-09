# Ashfall R1–R10 test runs

Two 10-round runs of the same game on the same world (`examples/ashfall_hunter/background.md`), with the same ten player inputs
(`ashfall_r10_inputs.txt`). Dice are real (OS random source). Nothing was edited, re-rolled or retried by hand between rounds.

**How the player inputs were made.** The R10 save in the old repo (`tests/data/ashfall/save_ashfall_hunter_R10.md`) has no chat log, only
records stamped with the round that wrote them. The ten inputs are my reconstruction of the player's decisions from those stamps
(take the case → phone Pike and go to the embankment → kill the creature → knock on hut 3 → hear Eli and show the shard →
take him to the workshop → test the shard → call Nadia and collect the balance → sofa and clinic promise → sleep).
They are NOT the player's original words.

**Two caveats about run A (Claude as the AI).** I had read the R10 save before the run, so I knew how the original game went; I tried to
decide only from the records and rule text in each prompt, but that knowledge is a possible bias. And the engine's program, not I,
rolled every die: where the dice disagreed with the original game (Nadia countered the fee, Eli first refused the door), I followed them.

Files: `ashfall_r10_claude/TRANSCRIPT.md` is the readable version; `calls/NNNN.json` is every request and reply in order;
`systems/` is the rule text each call carried; `rounds.jsonl` is the per-round record.
