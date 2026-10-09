## 16. Reading the starting plans

Each actor's plan note mixes moments on the clock with conditions that have none. Split it. Copy what it says; invent nothing.

```text
DUE      a moment on the clock: day_offset from TODAY (0 = today, 1 = tomorrow) and the time (HH:MM, or dawn, morning, noon,
  afternoon, dusk, evening, night); what: the move that happens then
TRIGGER  a condition with no clock ("immediately if ...", "on the first ...", "when ..."): keep the words
A note of (none given) is an undated plan: give the earliest believable DUE for the move, or a TRIGGER if it truly waits on an event.
A note can give several dues and triggers. Use today's date given to count day_offset; the program does the rest.
```
