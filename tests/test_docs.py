import pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from localgm import settings

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_every_file_the_readme_and_install_guide_name_exists():
    for doc in ("README.md", "docs/INSTALL.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        for path in re.findall(r"`((?:docs|engine|tools|tests|localgm|examples)/[\w./-]+|[\w-]+\.(?:bat|sh|txt))`", text):
            if "*" in path or path.endswith("/"):
                continue
            assert (ROOT / path).exists(), f"{doc} names {path}, which does not exist"


def test_the_install_guide_covers_every_setting_choice():
    text = (ROOT / "docs/INSTALL.md").read_text(encoding="utf-8")
    for backend in settings.CHOICES["backend"]:
        assert f"`{backend}`" in text, backend
    for word in ("cpu", "threads", "API key", "Context size", "Check this model", "LGM_API_KEY", "llama-cpp-python"):
        assert word in text, word


def test_the_requirements_files_and_start_scripts_agree():
    assert "pyyaml" in (ROOT / "requirements.txt").read_text()
    assert "-r requirements.txt" in (ROOT / "requirements-dev.txt").read_text()
    for f in ("start.sh", "start.bat"):
        assert "requirements.txt" in (ROOT / f).read_text() and "localgm.web" in (ROOT / f).read_text()
    assert b"\r\n" in (ROOT / "start.bat").read_bytes() and b"\r\n" not in (ROOT / "start.sh").read_bytes()
