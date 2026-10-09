# Local AI GM

A text role-playing game master that runs on your own computer. The program rolls the dice, keeps the clock, the records and the saves.
A local AI model decides what is possible, what the people in the world do, and tells the story.

## Run
1. Install Python 3.10 or newer.
2. Double-click `start.bat` (Windows) or run `./start.sh`. A page opens in your browser.
3. Open **Settings** and choose where the AI runs, using the buttons on the page — you never edit a file:
   - **server**: LM Studio or Ollama. Load a model there, start its server, press *Test the AI*.
   - **gguf**: put a `.gguf` model file in the `models` folder and pick it in the list. (Needs `pip install llama-cpp-python`.)
   - **demo**: no AI; only to look around the app.
3b. Press **Check this model** in Settings: seven short calls that tell you whether your model can fill the engine's forms, step by step, before you start a game.
4. On **Home**, make a new game from a bundled world or paste your own BACKGROUND, and play. Every page has Home and Settings links; **Go back to this round** rewinds a game.

## How it works
The order is fixed: **world fact > dice > AI** (see `docs/DESIGN.md`).
`engine/steps.yaml` is the turn, in the form the program executes: each step says what the AI sees, the form it must fill in, and what the program does with it.
`engine/rules/` holds the judgement rules each step loads. `docs/MAP_FROM_V5.md` shows where each part of NEW ENGINE v5.0 went.
`python tools/ui_check.py` clicks through the app in a real browser. `python -m pytest tests` runs the rest.
