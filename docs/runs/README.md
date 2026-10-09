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

## Run A2 — the same ten inputs on the fixed engine (`ashfall_r10_claude_fixed/`)

Same AI (Claude, answering through the relay), same world, same ten inputs, real dice, nothing edited or retried. The engine had since gained:
ask-before-roll (`verdict: ask`), the `obvious` field and the play lessons, no cap on questions, a ten-round check, the program's own
bookkeeping of companions, and the program-owned work-source and temper routines.

Numbers come from `python tools/compare_runs.py ashfall_r10_claude ashfall_r10_claude_fixed`:

```text
                                        A (first engine)       A2 (fixed engine)
rounds ok                                          10/10                   10/10
AI calls                                              68                      67
dice lines printed                                    12                       8
  of which open questions                             10                       5
  of which skill/fight rolls                           2                       2
questions settled without dice        n/a (not recorded)                       7
prompt chars sent (≈ tokens × 4)                  922205                  992350
refused / failed AI answers                            0                       0
```

**What changed.** Open-question dice went from 10 to 5, and seven questions were settled from the records with no roll (does Nadia show her own
locator, is Pike's job still open, does Eli agree to leave a hut that a monster found, does Nadia pay a contract balance she owes…).
Fights and skill rolls are unchanged (the same two). Rounds 2, 6, 8 and 10 had no dice at all.

**What did not change.** Prompt size did not go down; it went up about 8 % (the resolved-facts list and the ten-round step). The savings from
fewer rolls are in play quality, not tokens.

**Caveats, so the comparison is not read too kindly.**
- The AI is the same one that played A, and during A2 I opened A's recorded answers several times (rounds 1, 2, 3, 4, 7) to match the form of a reply, so my decisions are
  not independent of A's and several of A2's answers (fight exchanges, ops shapes) follow A's closely. The dice are independent.
- Dice differ: A2 Eli's first refusal came out NO, BUT where A had NO, AND. The two runs therefore diverge from round 4.
- The ten inputs were reconstructed (see above). Input 8 says "take the $350 balance"; in both runs Nadia's counter-offer made the contract
  $200 + $500, so the AI paid the contracted $500 and the input's "$350" was not followed. That is a mismatch in the reconstructed inputs, not an
  engine decision.

**What A2 found in the engine** (fixed afterwards, in `engine/rules/12_world.md` + the react form + `flow.py`):
1. **Nothing moved the player.** After "I ride to the embankment" the next step still showed the workshop as the place, because only the AI could
   write `world_state.location`, and neither run's AI thought to. Fixed: the react form has `moved_to`; the program checks the place exists and moves
   the player. (Tests: `test_the_player_is_moved_by_the_program…`.)
2. **Noise in fights.** When the AI listed three exchanges and the foe fell in the first, the narrator was told "already down" twice. Fixed:
   quiet skip for exchanges after the foe fell in the same fight.
3. **Quest step skipped.** In round 6 (Eli safe at the workshop) the sorter did not include `quest`, so the "find Eli" quest stayed open until round 8.
   Not changed: it is the sorter's judgement, and the ten-round check is the safety net (in this run nothing was left to close at round 10).

Files are laid out like run A: `TRANSCRIPT.md`, `calls/NNNN.json`, `systems/`, `rounds.jsonl`.

## Run B — a 3B coding model as the AI (`ashfall_r10_3b/`) — stopped early, partial

The only model available in the sandbox was a 3B coding model (Qwen2.5-Coder-3B, q4, CPU). It was given the same world and the same ten inputs
on the engine as it stood when the run began (before the A2 fixes). **The run did not finish:** the container was restarted while it was
working on input 8, so it covers inputs 1–7 (attempts 1–7 of the log). Nothing was edited. Files: `TRANSCRIPT.md`, `calls/`, `systems/`, `rounds.jsonl`.

What the data shows, no more:
- 4 of the 7 attempted inputs were accepted by the program (rounds R1–R4); 3 were refused and rolled back whole (`ok: false`), each because the sort step
  returned text that was not valid JSON. A refused round changes nothing, so the game stayed consistent, but the 3B model could not carry a turn
  reliably.
- It is slow on CPU: 7–12 minutes per attempted input.
- The header shows time stuck at 19:40 after four accepted rounds: the model did not advance the clock.
- This says the program survives a weak model without corrupting state. It says nothing about how a 14B or larger model will play; that is still untested.
