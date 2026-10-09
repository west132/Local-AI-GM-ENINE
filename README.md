# Local AI GM

A text role-playing game master that runs on your own computer, based on the NEW ENGINE v5.0 rules.

- **The program** rolls every die, does every sum, keeps the clock and calendar, money, supplies, records and saves, and refuses anything that breaks a fact or a result.
- **The AI** is the game master: it decides what is possible, what people and the world do, and tells the story. It never rolls, and it cannot change what the records or the dice have settled (**world fact > dice > AI**, see `docs/DESIGN.md`).

You can run the AI three ways with the same game: a model file inside the app (on the CPU or a graphics card), a local server (LM Studio / Ollama), or an online API with a key.

## Quick start
1. Install Python 3.10 or newer (Windows: tick "Add Python to PATH").
2. Windows: double-click `start.bat`. Mac / Linux: run `./start.sh`. The first run makes a private `.venv` folder and installs what it needs; then a page opens in your browser.
3. **Settings** → choose where the AI runs (everything is buttons and boxes; you never edit a file):
   - **gguf** — a model file in the `models` folder, run inside this app. Pick the file, choose *cpu* or *auto*, press **Save**.
   - **server** — LM Studio or Ollama. Load a model there, start its server, enter the address, press **Test the AI**.
   - **api** — an online service. Enter its address, model name and API key, press **Save**, then **Test the AI**.
   - **demo** — no AI; only to look around.
4. Press **Check this model** (a few short calls). Home shows the result, and asks before you start a game on an AI that was not checked or did badly.
5. **Home** → pick a world, name your game, **Start**. Or **Make a new world** from a short idea, or **Continue from a save file**.

Full steps for each way of running the AI, and fixes for common problems: **`docs/INSTALL.md`**.

## What you can do in the app
- **Play**: type what you do. The page shows the program's roll lines, then the story. **Go back to this round** rewinds a game. **Export save** downloads a SAVE file.
- **Make a new world** from an idea (a game, a setting, who you play). The AI fills six forms; the program checks every one (full names, genders, a price list, which modules fit, plan dates, the source game's starting abilities) and writes the BACKGROUND.
- **Continue from a save file** made in a chat with NEW ENGINE v5.0 (choose the world it belongs to), or one exported here.
- **Settings**: where the AI runs, CPU/threads, context size, temperature, reply length, language, and two switches that save AI calls on slow computers.

## Worlds, saves and folders
```text
models/      your .gguf files (backend "gguf")
saves/       one folder per game: state, a snapshot of every round, the journal
worlds/      worlds you made with "Make a new world"
examples/    five bundled worlds (harbour guesthouse, Ashfall, Tarnstead, Last Scion, Cyberpunk Red)
settings.json   written by the Settings page (it holds your API key if you entered one; keep it private)
```
A BACKGROUND writes every date as `YYYY-MM-DD`, or defines its own calendar as a table (months, days, leap rule); see "Calendars" in `docs/DESIGN.md`.

## How it works
`engine/steps.yaml` is the turn in the form the program executes: sort → (confirm) → judge → fight → ask → react → offer → quest → injury → ending → ten-round check → tell → check → recap.
Each step says what the AI sees, the form it must fill in, and what the program does with it. `engine/rules/` holds the judgement rules each step loads.
The program passes every decision from one AI call to the next, and a turn it cannot record is dropped whole (nothing kept, the round does not advance).

| Read | For |
|---|---|
| `docs/INSTALL.md` | installing and running with each kind of AI; troubleshooting |
| `docs/DESIGN.md` | the authority order, calendars, how decisions are handed between AI calls |
| `docs/STATUS.md` | every V5 rule: implemented, partial or not yet, and the test that shows it |
| `docs/PROJECT_SUMMARY.md` | what was built, what the runs showed, what is not tested |
| `docs/MAP_FROM_V5.md` | where each part of NEW ENGINE v5.0 went |
| `docs/runs/` | recorded Ashfall test runs (raw calls and transcripts) |

## Checking the software
```text
pip install -r requirements-dev.txt
python -m pytest tests          # the rules, the loop, the backends, the calendar, the generator
python tools/audit_flows.py     # every step, rule file and form field is wired into the loop
python tools/ui_check.py        # clicks through the app in a real browser (needs: playwright install chromium)
python tools/install_check.py   # installs into a clean folder and fresh venv, then starts the app
```
In the app, **Check this model** tells you whether *your* AI can fill the engine's forms. Honest limits are listed in `docs/STATUS.md` and `docs/PROJECT_SUMMARY.md`:
only a strong model has played a full ten-round game so far, and Windows `start.bat` has not been run on Windows.
