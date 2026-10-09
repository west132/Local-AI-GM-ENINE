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
}
CHOICES = {"backend": ["gguf", "server", "demo"], "language": ["en", "zh"]}


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
        for k, default in DEFAULTS.items():
            if k not in form:
                continue
            raw = str(form[k]).strip()
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
                if k == "gguf" and v and not (self.models / v).is_file():
                    raise ValueError(f"{v} is not in the models folder")
                new[k] = v
            except ValueError as e:
                problems.append(f"{k}: {e}")
        self.data = new
        self.save()
        return problems

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def ggufs(self) -> list[str]:
        if not self.models.is_dir():
            return []
        return sorted(p.name for p in self.models.glob("*.gguf") if "mmproj" not in p.name.lower())
