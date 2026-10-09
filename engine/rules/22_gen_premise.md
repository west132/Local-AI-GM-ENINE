## 22. Making a world — the premise

The person gave a short idea. Turn it into the setting. Everything they asked for is fixed; fill the rest so the world holds together.

```text
SOURCE   idea names a game, book, show or film → source_game = its name, mode = canon, canon_scope = what is fixed
  (history before the start) and that its main course is the actors' default plan. No source → source_game "", mode original.
CALENDAR  by default dates are written YYYY-MM-DD (a fantasy world may use a year like 0482). A world with its own calendar fills `calendar`
  with a TABLE the program can compute from: era (printed before the year), months [{name, days}] covering the whole year, an optional
  leap rule {every, month, extra}, optional weekdays + start_weekday. Every date in every form is then written "<era> <year>, <Month> <day>"
  (Year 318, Floodmonth 6) and must be a real date of the table. Never write a date the table cannot make; never leave a month out.
START    an opening moment the story really begins at, not a summary: date YYYY-MM-DD, clock HH:MM, daypart, season, weather.
ANCHORS  only what stops incompatible invention later: who lives here, what powers exist and their limits, technology, who rules,
  money and trade, what threatens. One line each. Never leave a required list empty; write "none" if there truly is none.
NORMS    what the law protects; for each common kind of fighter, how readily it breaks (retreats, surrenders, flees).
MP       draws_mp lists the powers that cost MP; [] if the setting has none.
MODULES  turn ON every module the setting fits, and say why in a few words:
  numeric_level_xp          levels and XP are visible in the setting or the story; ON for nearly every adventure
  equipment_power_tiers     gear has power grades, magic items, cyberware, relics; ON when gear can be better than other gear
  flexible_item_entitlement the person can have more kit than the opening list (a loadout, a quartermaster, a merchant); ON when
                            the setting has any way to obtain kit
  bounded_scenario_endings  the story has a defined end (a case closes, a war is won); OFF for open-ended worlds
Turn a module OFF only when it would not fit, and the reason says so.
background_id: lowercase words joined by underscores plus _v1.
```
