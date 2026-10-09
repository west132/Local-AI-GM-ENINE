"""Where the AI lives. Both backends expose ask(system, user, schema) -> dict | str."""
from __future__ import annotations
import json, re, urllib.request

_THINK = re.compile(r"<think>.*?</think>", re.S)


def parse_json(text: str):
    text = _THINK.sub("", text).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def _finish(text: str, schema):
    return str(_THINK.sub("", text)).strip() if schema is None else parse_json(text)


class OpenAICompat:
    """LM Studio, Ollama, llama-server, vLLM: any OpenAI-style /v1/chat/completions."""
    def __init__(self, base="http://localhost:1234/v1", model="", temperature=0.3, max_tokens=1500, timeout=600):
        self.base, self.model, self.temperature, self.max_tokens, self.timeout = base.rstrip("/"), model, temperature, max_tokens, timeout

    def ask(self, system, user, schema=None, max_tokens=None):
        body = {"model": self.model, "temperature": self.temperature, "max_tokens": max_tokens or self.max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "reply", "strict": False, "schema": schema}}
        req = urllib.request.Request(self.base + "/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return _finish(json.load(r)["choices"][0]["message"]["content"], schema)


class LlamaCpp:
    """A .gguf run in-process."""
    def __init__(self, path, n_ctx=8192, n_gpu_layers=-1, temperature=0.3, max_tokens=1200):
        from llama_cpp import Llama
        self.llm = Llama(model_path=str(path), n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, verbose=False)
        self.temperature, self.max_tokens = temperature, max_tokens

    def ask(self, system, user, schema=None, max_tokens=None):
        kw = {"response_format": {"type": "json_object", "schema": schema}} if schema is not None else {}
        out = self.llm.create_chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=self.temperature, max_tokens=max_tokens or self.max_tokens, **kw)
        return _finish(out["choices"][0]["message"]["content"], schema)


class Demo:
    """Canned, valid replies: lets the app run end to end with no model at all."""
    def ask(self, system, user, schema=None, max_tokens=None):
        if schema is None:
            return "(demo) " + user.split("PLAYER:")[-1].split("\n")[0].strip()[:120]
        props = schema.get("properties", {})
        if "kind" in props:
            return {"kind": "fast", "steps": []}
        if "ok" in props:
            return {"ok": True}
        if "actors" in props:
            return {"actors": []}
        return {}


def make(settings):
    """The backend the settings page chose."""
    d = settings.data
    if d["backend"] == "demo":
        return Demo()
    if d["backend"] == "server":
        return OpenAICompat(d["url"], d["model"], d["temperature"], d["max_tokens"])
    files = settings.ggufs()
    name = d["gguf"] or (files[0] if files else "")
    if not name:
        raise FileNotFoundError("no model file in the models folder; put a .gguf there or choose another backend in Settings")
    return LlamaCpp(settings.models / name, d["ctx"], -1, d["temperature"], d["max_tokens"])


def probe(url: str) -> list[str]:
    """Ask a server which models it has. Raises on failure."""
    with urllib.request.urlopen(url.rstrip("/") + "/models", timeout=5) as r:
        return [m["id"] for m in json.load(r).get("data", [])]
