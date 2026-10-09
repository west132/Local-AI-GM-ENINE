## 24. Making a world — the player character

Fill the character the person plays. Start from what they asked; if the idea names a source and a protagonist, use that protagonist as the source tells it.

```text
NAME     a FULL name: given name and family name (or the setting's full form). Never a first name alone, never a title alone.
GENDER   a plain word: man, woman, nonbinary, or the setting's own word. Never blank.
HISTORY  the facts that earn the skills and level. No skill above T1 without history that explains it.
SKILLS   each skill: id, class (ceiling), tier (now), class_source (what earned it), abilities (named things the skill can do).
SOURCE   canon: source_abilities lists every ability the protagonist really has when the story begins, as the source game has it;
  each names the skill that holds it, and that skill's abilities list contains it. An ability the source gives only later is NOT here.
  Original world: source_abilities = [].
LEVEL    1–20; the history must support it. hp is a starting value for that level; mp only if the character has an MP-drawing skill.
EQUIPMENT  what they carry at the start. price_ref = the item's name in the price list, or "personal". Items the profession implies
  and the story does not forbid (phone, wallet, tools) are included.
MONEY    a number in the world's currency, enough for about a week of the living costs unless the history says otherwise.
ITEM POINTS  0 none · 1 limited · 2 ordinary professional · 4 well-resourced · 8 elite or wealthy · 12 exceptional; basis in a few words.
KNOWLEDGE  facts they hold now, each with a short key. Nothing they could not know.
```
