"""Settings live in settings.json and are written by the program from the settings page, never by hand."""
from __future__ import annotations
import json, os, pathlib

DEFAULTS = {
    "backend": "gguf",            # gguf = a model file in the models folder | server = LM Studio / Ollama | demo
    "gguf": "",                   # file name inside the models folder; empty = the first one found
    "url": "http://localhost:1234/v1",
    "model": "",
    "ctx": 16384,
    "temperature": 0.3,
    "max_tokens": 1500,
    "language": "en",
    "api_key": "",                # backend "api" only; kept in this file, never shown again, never sent anywhere but the API address
    "device": "auto",             # model file only: auto = use the GPU if the library has one, cpu = never
    "threads": 0,                 # model file only: CPU threads, 0 = let the library choose
    "merge_questions": "yes",     # yes = the world step asks its open questions in the same call (one AI call fewer per turn)
    "check_telling": "yes",       # yes = the AI re-reads its telling against the facts (one AI call per turn)
}
CHOICES = {"backend": ["gguf", "server", "api", "demo"], "language": ["en", "zh"], "device": ["auto", "cpu"],
           "merge_questions": ["yes", "no"], "check_telling": ["yes", "no"]}


class Settings:
    def __init__(self, root="."):
        self.root = pathlib.Path(root)
        self.path = self.root / "settings.json"
        self.models = self.root / "models"
        self.saves = self.root / "saves"
        self.data = dict(DEFAULTS)
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass          # unreadable file: fall back to defaults; the next save rewrites it

    def update(self, form: dict) -> list[str]:
        """Validate the page's values, keep the good ones, return a list of problems. Writes the file."""
        problems, new = [], dict(self.data)
        if form.get("clear_api_key"):
            new["api_key"] = ""
        for k, default in DEFAULTS.items():
            if k not in form:
                continue
            raw = str(form[k]).strip()
            if k == "api_key" and not raw:
                continue                  # the page never shows the key, so a blank box means "keep it"
            try:
                v = type(default)(raw) if not isinstance(default, str) else raw
                if k in CHOICES and v not in CHOICES[k]:
                    raise ValueError(f"must be one of {CHOICES[k]}")
                if k == "ctx" and not 2048 <= v <= 1_000_000:
                    raise ValueError("2048 to 1000000")
                if k == "temperature" and not 0 <= v <= 2:
                    raise ValueError("0 to 2")
                if k == "max_tokens" and not 100 <= v <= 16000:
                    raise ValueError("100 to 16000")
                if k == "threads" and not 0 <= v <= 256:
                    raise ValueError("0 (automatic) to 256")
                if k == "gguf" and v and not (self.models / v).is_file():
                    raise ValueError(f"{v} is not in the models folder")
                new[k] = v
            except ValueError as e:
                problems.append(f"{k}: {e}")
        self.data = new
        self.save()
        return problems

    def turn_options(self) -> dict:
        return {"merge_questions": self.data["merge_questions"] == "yes", "check_telling": self.data["check_telling"] == "yes"}

    def fingerprint(self) -> str:
        """Which AI this is: a check result belongs to one model on one backend."""
        d = self.data
        return "|".join(str(d.get(k, "")) for k in ("backend", "model", "gguf", "url", "device", "ctx"))

    def remember_check(self, res: dict) -> None:
        self.data["last_check"] = {"for": self.fingerprint(), "passed": res["passed"], "total": res["total"], "verdict": res["verdict"]}
        self.save()

    def check_status(self) -> tuple[str, str]:
        """(level, text) for Home: good | usable | weak | none."""
        c = self.data.get("last_check")
        if self.data["backend"] == "demo":
            return "demo", "Demo mode: no AI is used."
        if not c or c.get("for") != self.fingerprint():
            return "none", "This AI has not been checked yet. Settings → Check this model."
        level = "good" if c["passed"] == c["total"] else "usable" if c["passed"] >= c["total"] - 2 else "weak"
        return level, f"AI check: {c['passed']}/{c['total']} — {c['verdict']}"

    def api_key(self) -> str:
        return self.data.get("api_key") or os.environ.get("LGM_API_KEY", "")

    def key_hint(self) -> str:
        k = self.api_key()
        return "" if not k else "saved (…" + k[-4:] + ")" if len(k) > 8 else "saved"

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def ggufs(self) -> list[str]:
        if not self.models.is_dir():
            return []
        return sorted(p.name for p in self.models.glob("*.gguf") if "mmproj" not in p.name.lower())
