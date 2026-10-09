"""Click through the real app in a real browser: settings change, new game, play, back to Home, rewind.
python tools/ui_check.py   (starts its own server on a temp folder with the demo AI)"""
import json, pathlib, subprocess, sys, tempfile, time, urllib.request
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "models").mkdir()
(tmp / "models" / "fake-model.gguf").write_bytes(b"x")
srv = subprocess.Popen([sys.executable, "-m", "localgm.web", "--port", "8799", "--root", str(tmp)], cwd=ROOT)
for _ in range(50):
    try:
        urllib.request.urlopen("http://127.0.0.1:8799/", timeout=1); break
    except OSError:
        time.sleep(0.2)
ok = []

def check(cond, what):
    ok.append(bool(cond)); print(("PASS " if cond else "FAIL ") + what)

try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        pg = b.new_page(viewport={"width": 390, "height": 800})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("http://127.0.0.1:8799/")
        check("Your games" in pg.inner_text("body"), "home page opens")
        pg.click("text=Settings")
        check(pg.url.endswith("/settings"), "Settings link works")
        pg.select_option("select[name=backend]", "demo")
        pg.select_option("select[name=gguf]", "fake-model.gguf")
        pg.fill("input[name=temperature]", "0.5")
        pg.click("button:text('Save')")
        check("Saved." in pg.inner_text("body"), "settings save from the page")
        saved = json.loads((tmp / "settings.json").read_text())
        check(saved["backend"] == "demo" and saved["gguf"] == "fake-model.gguf" and saved["temperature"] == 0.5, "the program wrote settings.json (no hand editing)")
        pg.select_option("select[name=backend]", "api"); pg.select_option("select[name=device]", "cpu"); pg.fill("input[name=threads]", "6")
        pg.fill("input[name=api_key]", "sk-secret-1234"); pg.select_option("select[name=check_telling]", "no")
        pg.click("button:text('Save')")
        saved = json.loads((tmp / "settings.json").read_text())
        check(saved["backend"] == "api" and saved["api_key"] == "sk-secret-1234" and saved["device"] == "cpu" and saved["threads"] == 6 and saved["check_telling"] == "no",
              "API key, CPU-only, threads and the call-saving choices are saved from the page")
        check("sk-secret-1234" not in pg.content() and "…1234" in pg.content(), "the page never shows the saved key back, only its last four characters")
        pg.select_option("select[name=backend]", "demo"); pg.select_option("select[name=check_telling]", "yes"); pg.click("button:text('Save')")
        check(json.loads((tmp / "settings.json").read_text())["api_key"] == "sk-secret-1234", "saving with the key box blank keeps the key")
        pg.fill("input[name=temperature]", "9")
        pg.click("button:text('Save')")
        check("temperature" in pg.inner_text("body") and json.loads((tmp / "settings.json").read_text())["temperature"] == 0.5, "a bad value is refused with a reason and the old value kept")
        pg.click("#test"); pg.wait_for_function("document.getElementById('t').textContent.length>3")
        check("Demo mode" in pg.inner_text("#t"), "Test the AI button answers")
        pg.click("#check"); pg.wait_for_function("document.getElementById('chk').innerText.includes('Tells the scene')", timeout=60000)
        check("/7" in pg.inner_text("#t") and "Weak" in pg.inner_text("#t") or "Not capable" in pg.inner_text("#t") or "Usable" in pg.inner_text("#t"),
              "Check this model runs and shows a verdict with a row per step")
        pg.click("text=Back to Home")
        check(pg.url.rstrip("/").endswith("8799"), "Back to Home works from Settings")
        pg.fill("input[name=name]", "g1")
        pg.select_option("select[name=world]", "tarnstead_low_fantasy")
        pg.click("button:text('Start')")
        pg.wait_for_selector("#in"); pg.wait_for_function("document.getElementById('st').textContent==''")
        check("/play/g1" in pg.url, "new game opens the play page")
        pg.fill("#in", "I look around the inn."); pg.click("#go")
        pg.wait_for_selector(".prose")
        check("(demo) I look around" in pg.inner_text("#log"), "a turn runs and the reply appears")
        check("R1" in pg.inner_text("#hdr"), "header shows round 1")
        pg.click("nav >> text=Home")
        check(pg.locator("text=g1").count() > 0 and "round 1" in pg.inner_text("body"), "Home lists the game with its round")
        pg.click("text=Continue")
        check("I look around" in pg.inner_text("#log"), "Continue brings the saved log back")
        pg.fill("#in", "I wait."); pg.click("#go"); pg.wait_for_function("document.querySelectorAll('.prose').length>=2")
        pg.on("dialog", lambda d: d.accept())
        pg.select_option("#rn", "1"); pg.click("button:text('Go back to this round')")
        pg.wait_for_load_state(); pg.wait_for_selector("#hdr")
        pg.wait_for_function("document.getElementById('hdr').textContent.startsWith('R1')")
        check("R1" in pg.inner_text("#hdr") and "I wait" not in pg.inner_text("#log"), "rewind returns to round 1")
        with pg.expect_download() as dl:
            pg.click("text=Export save")
        exp = pathlib.Path(dl.value.path()).read_text()
        check("# PART B" in exp and "PART A" in exp, "Export gives a SAVE file")
        pg.goto("http://127.0.0.1:8799/")
        pg.fill("form[action='/import'] input[name=name]", "from_chat")
        pg.select_option("form[action='/import'] select[name=world]", "ashfall_hunter")
        pg.fill("#savetext", (ROOT / "tests" / "data" / "ashfall_R10.md").read_text())
        pg.click("text=Import and continue")
        pg.wait_for_selector("#hdr")
        check("R10" in pg.inner_text("#hdr") and "hale_workshop" in pg.inner_text("#hdr"), "A chat-made R10 save imports and opens at round 10")
        pg.goto("http://127.0.0.1:8799/")
        pg.fill("#idea", "Ember Road, a grim road fantasy; I am a toll-road warden")
        pg.click("text=Make this world")
        pg.wait_for_function("document.getElementById('st').textContent.startsWith('Done')", timeout=30000)
        check("ember_road_v1" in pg.inner_text("#st"), "Make a new world from an idea finishes and names the world")
        pg.click("text=Home")
        check(pg.locator("select[name=world] option[value=ember_road_v1]").count() >= 1, "the new world is in the World list")
        pg.fill("form[action='/new'] input[name=name]", "g_made")
        pg.select_option("form[action='/new'] select[name=world]", "ember_road_v1")
        pg.click("button:text('Start')")
        pg.wait_for_selector("#hdr")
        check("R0" in pg.inner_text("#hdr") and "toll_gate" in pg.inner_text("#hdr"), "a game starts in the made world at its start place")
        pg.click("nav >> text=Settings"); check(pg.url.endswith("/settings"), "Settings reachable from the play page")
        check(not errors, f"no JavaScript errors {errors}")
        b.close()
finally:
    srv.terminate()
print("ALL PASS" if all(ok) else "FAILURES")
sys.exit(0 if all(ok) else 1)
