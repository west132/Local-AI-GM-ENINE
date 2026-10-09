"""Where the AI lives. Both backends expose ask(system, user, schema) -> dict | str."""
from __future__ import annotations
import copy
import json, re, urllib.error, urllib.request

_THINK = re.compile(r"<think>.*?</think>", re.S)


def close_json(text: str) -> str:
    """A reply cut off by the token limit: close the open string and brackets so it can be read and checked field by field."""
    stack, in_str, esc, out = [], False, False, []
    for ch in text:
        out.append(ch)
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    s = "".join(out)
    if in_str:
        s += '"'
    s = re.sub(r'[,:\s]+$', "", s)
    s = re.sub(r',\s*"[^"]*"$', "", s)               # a key with no value yet
    return s + "".join(reversed(stack))


def parse_json(text: str):
    text = _THINK.sub("", text).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        start = text.find("{")
        if start < 0:
            raise
        return json.loads(close_json(text[start:]))


def _finish(text: str, schema):
    return str(_THINK.sub("", text)).strip() if schema is None else parse_json(text)


class OpenAICompat:
    """LM Studio, Ollama, llama-server, vLLM: any OpenAI-style /v1/chat/completions."""
    def __init__(self, base="http://localhost:1234/v1", model="", temperature=0.3, max_tokens=1500, timeout=600, api_key=""):
        self.base, self.model, self.temperature, self.max_tokens, self.timeout = base.rstrip("/"), model, temperature, max_tokens, timeout
        self._key = api_key              # sent only as the Authorization header; never put in a prompt, a log or an error text

    def _headers(self) -> dict:
        return {"Content-Type": "application/json", **({"Authorization": "Bearer " + self._key} if self._key else {})}

    def ask(self, system, user, schema=None, max_tokens=None):
        body = {"model": self.model, "temperature": self.temperature, "max_tokens": max_tokens or self.max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "reply", "strict": False, "schema": schema}}
        req = urllib.request.Request(self.base + "/chat/completions", json.dumps(body).encode(), self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return _finish(json.load(r)["choices"][0]["message"]["content"], schema)
        except urllib.error.HTTPError as e:
            hint = {401: "the API key was refused (check it in Settings)", 403: "the API key has no access to this model", 404: "the address or model name is wrong",
                    429: "rate limit or quota reached"}.get(e.code, "the server returned an error")
            raise ConnectionError(f"{self.base}: HTTP {e.code}, {hint}") from None


class LlamaCpp:
    """A .gguf run in-process."""
    def __init__(self, path, n_ctx=8192, n_gpu_layers=-1, temperature=0.3, max_tokens=1200, n_threads=None):
        from llama_cpp import Llama
        kw = {"n_threads": n_threads} if n_threads else {}
        self.llm = Llama(model_path=str(path), n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, verbose=False, **kw)
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
        from . import demo_forms as D
        for field, key in (("title", "premise"), ("groups", "economy"), ("source_abilities", "player"),
                           ("start_location", "places"), ("npcs", "cast"), ("quests", "story")):
            if field in props and "required" in schema and field in schema["required"]:
                return copy.deepcopy(D.GOOD[key])
        if "kind" in props:
            return {"kind": "fast", "steps": [], "note": "(demo) it simply happens."}
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
        return OpenAICompat(d["url"], d["model"], d["temperature"], d["max_tokens"], api_key=settings.api_key())
    if d["backend"] == "api":
        if not settings.api_key():
            raise ValueError("backend 'api' needs an API key: enter it in Settings (or set LGM_API_KEY)")
        return OpenAICompat(d["url"], d["model"], d["temperature"], d["max_tokens"], api_key=settings.api_key())
    files = settings.ggufs()
    name = d["gguf"] or (files[0] if files else "")
    if not name:
        raise FileNotFoundError("no model file in the models folder; put a .gguf there or choose another backend in Settings")
    return LlamaCpp(settings.models / name, d["ctx"], 0 if d["device"] == "cpu" else -1, d["temperature"], d["max_tokens"], d["threads"] or None)


def probe(url: str, api_key: str = "") -> list[str]:
    """Ask a server which models it has. Raises on failure."""
    req = urllib.request.Request(url.rstrip("/") + "/models", headers={"Authorization": "Bearer " + api_key} if api_key else {})
    with urllib.request.urlopen(req, timeout=5) as r:
        return [m["id"] for m in json.load(r).get("data", [])]
