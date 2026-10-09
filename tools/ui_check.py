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
        pg.fill("input[name=temperature]", "9")
        pg.click("button:text('Save')")
        check("temperature" in pg.inner_text("body") and json.loads((tmp / "settings.json").read_text())["temperature"] == 0.5, "a bad value is refused with a reason and the old value kept")
        pg.click("#test"); pg.wait_for_function("document.getElementById('t').textContent.length>3")
        check("Demo mode" in pg.inner_text("#t"), "Test the AI button answers")
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
        check("R1" in pg.inner_text("#hdr") and "I wait" not in pg.inner_text("#log"), "rewind returns to round 1")
        pg.click("nav >> text=Settings"); check(pg.url.endswith("/settings"), "Settings reachable from the play page")
        check(not errors, f"no JavaScript errors {errors}")
        b.close()
finally:
    srv.terminate()
print("ALL PASS" if all(ok) else "FAILURES")
sys.exit(0 if all(ok) else 1)
