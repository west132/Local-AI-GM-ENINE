"""Install the way start.bat does, in a clean folder and a fresh virtual environment, then open the app.
python tools/install_check.py     (needs network for pip; Linux/Mac run start.sh's steps, Windows runs start.bat)"""
import pathlib, shutil, subprocess, sys, tempfile, time, urllib.request, venv

ROOT = pathlib.Path(__file__).resolve().parent.parent
work = pathlib.Path(tempfile.mkdtemp()) / "install"
shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", "runs", ".venv", "__pycache__", ".pytest_cache"))
venv.create(work / ".venv", with_pip=True)
bin_ = work / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
py = str(bin_ / ("python.exe" if sys.platform == "win32" else "python"))
steps = []

def step(ok, what):
    steps.append(ok); print(("PASS " if ok else "FAIL ") + what)

r = subprocess.run([py, "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=work, capture_output=True, text=True)
step(r.returncode == 0, "pip install -r requirements.txt" + ("" if r.returncode == 0 else "\n" + r.stderr[-400:]))
srv = subprocess.Popen([py, "-m", "localgm.web", "--port", "8798"], cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    page = ""
    for _ in range(60):
        try:
            page = urllib.request.urlopen("http://127.0.0.1:8798/", timeout=1).read().decode(); break
        except OSError:
            time.sleep(0.25)
    step("Your games" in page, "the app starts from a clean folder and shows Home")
    for path in ("/settings", "/export/none"):
        try:
            code = urllib.request.urlopen("http://127.0.0.1:8798" + path, timeout=3).status
        except urllib.error.HTTPError as e:
            code = e.code
        step(code in (200, 404), f"{path} answers ({code})")
    step(not (work / "examples").exists() or any((work / "examples").iterdir()), "example worlds shipped")
finally:
    srv.terminate()
bat = (ROOT / "start.bat").read_bytes()
step(b"\r\n" in bat, "start.bat has Windows line endings")
print("OK" if all(steps) else "FAILURES")
sys.exit(0 if all(steps) else 1)
