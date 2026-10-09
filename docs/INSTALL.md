# Installing and running Local AI GM

Nothing here asks you to edit a file by hand. Everything about the AI is set on the **Settings** page.

## 1. What you need
- Python **3.10 or newer** (Windows: from python.org, tick **Add Python to PATH**; Linux: `python3` and `python3-venv`; Mac: python.org or Homebrew).
- An internet connection for the first run (it installs one small package, `pyyaml`).
- One AI, in any of the three ways in section 3.

## 2. Start the app
**Windows:** double-click `start.bat`. **Mac / Linux:** open a terminal in this folder and run `./start.sh`.

The first run creates a private `.venv` folder, installs the requirements and opens `http://127.0.0.1:8765` in your browser. Later runs start at once.
Keep the black window open while you play; closing it stops the app. Your games are saved after every round in the `saves` folder.

If the page does not open by itself, open `http://127.0.0.1:8765` yourself. To use another port: `python -m localgm.web --port 9000` (inside the activated `.venv`).

## 3. Choose where the AI runs (Settings page)

Press **Save**, then **Test the AI**, then **Check this model**. Home shows the check result and asks before you start a game on an AI that was not checked or scored badly.

### A. A model file inside the app — `gguf` (works offline, no server)
1. Install the library once. In the activated `.venv`:
   ```text
   pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
   ```
   (Windows: open a terminal in this folder, run `.venv\Scripts\activate`, then the line above. This is a prebuilt CPU wheel; no compiler needed.
   If you have a graphics card and want it used, follow the library's own instructions for a CUDA/Metal build instead, then choose *auto* below.)
2. Put a `.gguf` model file in the `models` folder (make the folder if it is not there). Instruction-tuned models of 7B and larger work best; a 14B is the intended size.
3. Settings → **Where the AI runs: gguf**, pick the file, **Run the model file on: cpu** (never use a graphics card) or **auto**, set **CPU threads** (0 = automatic; a good value is your number of physical cores) and **Context size** (the engine needs about 16384 for long games; lower it if you run out of memory).
4. Save, Test, Check.

CPU speed: a 14B model on a CPU takes minutes per turn; a 7B is faster. The two switches at the bottom of Settings cut AI calls per turn:
*Fewer AI calls per turn = yes* and *AI re-reads its telling = no* roughly halve the waiting on a slow computer (a little less careful).

### B. A local server — `server` (LM Studio, Ollama, llama-server and similar)
1. Install and open LM Studio (or Ollama), download a model, load it, and **start the local server**.
2. Settings → **Where the AI runs: server**. **Server or API address**: LM Studio shows `http://localhost:1234/v1` by default; Ollama's OpenAI-compatible address is `http://localhost:11434/v1`.
3. **Model name**: leave blank to use whatever is loaded, or type the model's name.
4. Save, Test (it lists the models the server has), Check.

### C. An online API — `api`
1. Get an API key from your provider. The provider must offer an OpenAI-style `/v1/chat/completions` address.
2. Settings → **Where the AI runs: api**. Enter the **address** (for example `https://api.openai.com/v1`), the **model name**, and the **API key**. Save.
3. The key is stored in `settings.json` on this computer and sent only to that address, as a header. It is never shown on the page again (you see its last four characters), never put in a prompt, a save or a log. Leave the box blank later to keep it; tick *remove the saved key* to delete it. You can instead set the environment variable `LGM_API_KEY` before starting the app.
4. Each turn is several paid calls. Turn on the two call-saving switches if you want fewer.
5. Test, Check. A refused key shows "the API key was refused".

### D. Demo — `demo`
No AI. The app answers with canned text so you can look at the pages, try saves, rewind, import and export. It is not a game.

## 4. Your first game
Home → choose a world (`harbour_guesthouse` is the small safe one) → name the game → **Start**. Say what you do. The page shows lines such as `ask 2d10: 7+2 +1 = 10 → NO, BUT (…)` (the program's dice) and then the story.
If the AI gives an answer the program cannot use twice in a row, the turn is dropped whole: nothing is recorded, the round does not advance, and the page tells you to send the action again.

## 5. Other things on Home
- **Make a new world**: describe it in a few lines (a game it comes from, a setting, who you play). It takes several AI calls; the finished world appears in the World list. A world may use its own calendar written as a table (see `docs/DESIGN.md`, "Calendars").
- **Continue from a save file**: choose the world the save belongs to, then pick or paste the SAVE file made in a chat with NEW ENGINE v5.0 (or one you exported here). The play page has **Export save**.
- **Go back to this round** (play page) rewinds the game; later rounds are removed.

## 6. Folders
```text
models/       .gguf files
saves/        your games (one folder each; deleting a game on Home deletes its folder)
worlds/       worlds made with "Make a new world"
settings.json what the Settings page saved
```
Back up `saves/` to keep your games. The BACKGROUND of each game is copied into its folder, so a game does not depend on the bundled files.

## 7. Troubleshooting
| You see | Do this |
|---|---|
| "Python 3.10 or newer is needed" | install a newer Python; Windows: tick *Add Python to PATH*, reopen the window |
| Linux: "Could not make the .venv folder" | `sudo apt install python3-venv` |
| "Installing the requirements failed" | check the internet connection and run the start file again |
| gguf: "no model file in the models folder" | put a `.gguf` file in `models`, press Save |
| gguf: `ModuleNotFoundError: llama_cpp` | do step A.1 inside the `.venv` |
| gguf: out of memory or very slow | lower **Context size**, use a smaller or more compressed model (Q4), set **cpu** and the right **threads** |
| server: "Cannot reach it" | the server is not running, or the address is wrong; LM Studio: start its local server |
| api: "the API key was refused" | re-enter the key; check it has access to that model |
| api: HTTP 404 | the address or model name is wrong |
| Check this model says *Weak* or *Not capable* | use a larger or better instruction-tuned model; the program drops turns the AI cannot fill, but play will be frustrating |
| A turn says "could not give a usable answer … step" | nothing was recorded; send the action again; if it repeats, the model is too weak for that step |
| The page says the AI is still working | the AI is slow; wait, a CPU turn can take minutes |

## 8. Developers
```text
pip install -r requirements-dev.txt
python -m pytest tests
python tools/audit_flows.py
python tools/ui_check.py          # after: playwright install chromium
python tools/install_check.py     # clean-folder install on this OS
```
`start.bat` has been reviewed but **not run on Windows**; `tools/install_check.py` does the same steps on Linux and Mac and passes there.
