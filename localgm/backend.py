"""Where the AI lives. Both backends expose ask(system, user, schema) -> dict | str."""
from __future__ import annotations
import json, os, pathlib, platform, re, struct, subprocess, sys, urllib.error, urllib.request

from .simgm import SimGM

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
    """A .gguf run in-process. kv: "f16" or "q8_0" (the attention cache; q8_0 halves its memory and needs flash attention)."""
    def __init__(self, path, n_ctx=8192, n_gpu_layers=-1, temperature=0.3, max_tokens=1200, n_threads=None, kv="f16"):
        from llama_cpp import Llama
        kw = {"n_threads": n_threads} if n_threads else {}
        if kv == "q8_0":
            kw.update(flash_attn=True, type_k=8, type_v=8)          # GGML_TYPE_Q8_0
        elif n_gpu_layers != 0:
            kw.update(flash_attn=True)
        self.llm = Llama(model_path=str(path), n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, verbose=False, **kw)
        self.temperature, self.max_tokens = temperature, max_tokens

    def ask(self, system, user, schema=None, max_tokens=None):
        kw = {"response_format": {"type": "json_object", "schema": schema}} if schema is not None else {}
        out = self.llm.create_chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=self.temperature, max_tokens=max_tokens or self.max_tokens, **kw)
        return _finish(out["choices"][0]["message"]["content"], schema)


def make(settings):
    """The backend the settings page chose."""
    d = settings.data
    if d["backend"] == "demo":
        return SimGM()
    if d["backend"] == "server":
        return OpenAICompat(d["url"], d["model"], d["temperature"], d["max_tokens"], api_key=settings.api_key())
    if d["backend"] == "api":
        if not settings.api_key():
            raise ValueError("backend 'api' needs an API key: enter it in Settings (or set LGM_API_KEY)")
        return OpenAICompat(d["url"], d["model"], d["temperature"], d["max_tokens"], api_key=settings.api_key())
    files = settings.ggufs()
    name = d["gguf"] or (best_fit(settings.models, files, settings.hardware()) if d.get("tuning", "auto") == "auto" else "") or (files[0] if files else "")
    if not name:
        raise FileNotFoundError("no model file in the models folder; put a .gguf there or choose another backend in Settings")
    path = settings.models / name
    if d.get("tuning", "auto") == "auto":
        hw = settings.hardware()
        plan = plan_load(path, {**hw, "gpus": [] if d["device"] == "cpu" else hw["gpus"]})          # "cpu" is still honoured: never use the card
        return LlamaCpp(path, plan["n_ctx"], plan["n_gpu_layers"], d["temperature"], d["max_tokens"], plan["n_threads"], plan["kv"])
    return LlamaCpp(path, d["ctx"], 0 if d["device"] == "cpu" else -1, d["temperature"], d["max_tokens"], d["threads"] or None)


# ---------- this PC and the model file: the settings that give the best speed the PC can hold ----------
# A model's weights have to sit in the graphics card's memory (VRAM) to run fast; whatever does not fit is run by the processor from ordinary RAM, several times slower.
# Besides the weights the card holds the attention cache (it grows with the context length) and some working memory. The program reads both sides and decides.

WANT_CTX = (32768, 24576)      # the one-form turn sends the rules (~14k tokens) with the records: it needs 24k at least, 32k is comfortable
RESERVE_MB = 1300              # working memory and the display, kept free on the card


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=8).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _ram_mb() -> int:
    try:
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong),
                            ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            m = MS(); m.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return int(m.total // 2**20)
        if sys.platform == "darwin":
            return int(_run(["sysctl", "-n", "hw.memsize"]).strip() or 0) // 2**20
        for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, AttributeError):
        pass
    return 0


def _offload():
    """Can the installed llama-cpp-python put layers on a graphics card? (The plain pip build cannot.) None = it is not installed."""
    try:
        import llama_cpp
        return bool(llama_cpp.llama_supports_gpu_offload())
    except ImportError:
        return None
    except Exception:
        return True          # an older library without the question: assume it can; loading will tell


def scan() -> dict:
    """What this PC has: graphics cards (name, memory), RAM, processor threads. Nothing here needs the user to know any of it."""
    gpus = []
    smi = "nvidia-smi"
    if sys.platform == "win32" and not _run([smi, "-L"]):
        smi = r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
    for line in _run([smi, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"]).splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) == 3 and parts[1].isdigit():
            gpus.append({"name": parts[0], "vram_mb": int(parts[1]), "free_mb": int(parts[2]) if parts[2].isdigit() else int(parts[1])})
    ram = _ram_mb()
    if not gpus and sys.platform == "darwin" and platform.machine() == "arm64":
        gpus = [{"name": "Apple silicon (shared memory)", "vram_mb": int(ram * 0.7), "free_mb": int(ram * 0.7)}]        # unified memory: about 70% can be used by the GPU
    threads = os.cpu_count() or 4
    return {"gpus": sorted(gpus, key=lambda g: -g["vram_mb"]), "ram_mb": ram, "threads": threads, "cores": max(1, threads // 2) if threads > 4 else threads,
            "offload": _offload()}


def read_gguf(path) -> dict:
    """The size, layer count and attention-cache cost of a model file, from its header (the weights are not loaded)."""
    path = pathlib.Path(path)
    info = {"file_mb": path.stat().st_size / 2**20}
    want = {"general.architecture", "general.name"}
    kv: dict = {}
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError(f"{path.name} is not a .gguf file")
        version = struct.unpack("<I", f.read(4))[0]
        if version < 2:
            raise ValueError("this .gguf is too old (version 1)")
        _tensors, n_kv = struct.unpack("<QQ", f.read(16))

        def rd(fmt):
            return struct.unpack(fmt, f.read(struct.calcsize(fmt)))[0]

        def string():
            return f.read(rd("<Q")).decode("utf-8", "replace")
        SIZES = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}

        def value(t):
            if t == 8:
                return string()
            if t == 9:
                et, n = rd("<I"), rd("<Q")
                if et in SIZES:
                    f.seek(n * struct.calcsize(SIZES[et]), 1)
                else:
                    for _ in range(n):
                        value(et)
                return None
            return rd(SIZES[t])
        for _ in range(n_kv):
            key, t = string(), rd("<I")
            v = value(t)
            if key in want or key.split(".", 1)[-1] in ("block_count", "context_length", "embedding_length", "attention.head_count", "attention.head_count_kv",
                                                        "attention.key_length", "attention.value_length"):
                kv[key] = v
    arch = kv.get("general.architecture", "")
    g = lambda k, default=None: kv.get(f"{arch}.{k}", default)
    layers, heads = g("block_count"), g("attention.head_count")
    if not layers or not heads or not g("embedding_length"):
        raise ValueError(f"{path.name}: cannot read the model's layout from the file")
    kv_heads = g("attention.head_count_kv", heads)
    if isinstance(kv_heads, list):
        kv_heads = max(kv_heads)
    head_dim = g("attention.key_length") or g("embedding_length") // heads
    info.update(name=kv.get("general.name", path.stem), arch=arch, layers=int(layers), trained_ctx=int(g("context_length", 4096)),
                kv_bytes_per_token=int(2 * layers * kv_heads * head_dim * 2))          # keys + values, 2 bytes each (16-bit)
    return info


def plan_load(path, hw: dict, ctx: int | None = None) -> dict:
    """The best way to run this file on this PC: how many layers on the card, how long a context, which cache type, how many threads.
    The order of preference: everything on the card with a 32k context; the cache in 8-bit to make room; a 24k context; and only then
    some layers left to the processor. `ctx` pins the context length."""
    m = read_gguf(path)
    gpu = hw["gpus"][0] if hw.get("gpus") else None
    no_offload = bool(gpu) and hw.get("offload") is False
    if no_offload:
        gpu = None            # the card is there but the installed library cannot use it
    ctx_max = max(2048, min(m["trained_ctx"], 131072))
    options = [(ctx, "f16"), (ctx, "q8_0")] if ctx else [(c, kv) for c in WANT_CTX for kv in ("f16", "q8_0")]
    options = [(min(c, ctx_max), kv) for c, kv in options]
    plan = {"model": m["name"], "file_mb": round(m["file_mb"]), "layers": m["layers"], "n_threads": min(8, hw.get("cores", 4)), "notes": []}
    ram_free = hw.get("ram_mb", 0) - 2500           # the system and the app keep a share
    if gpu:
        budget = gpu["free_mb"] - RESERVE_MB
        for c, kv in options:
            cache = m["kv_bytes_per_token"] * c * (0.53125 if kv == "q8_0" else 1) / 2**20
            if m["file_mb"] + cache <= budget:
                return {**plan, "device": "gpu", "n_gpu_layers": -1, "n_ctx": c, "kv": kv, "gpu_layers": m["layers"], "est_vram_mb": round(m["file_mb"] + cache + RESERVE_MB), "fits": True,
                        "speed": "fast", "notes": [f"all {m['layers']} layers on the graphics card, context {c}" + (", cache in 8-bit to save memory" if kv == "q8_0" else "")]}
        # some layers go to the processor: the smallest context that works keeps the most on the card
        c, kv = options[-1]
        cache = m["kv_bytes_per_token"] * c * 0.53125 / 2**20
        per_layer = (m["file_mb"] + cache) / (m["layers"] + 1)
        on_gpu = max(0, min(m["layers"], int(budget / per_layer)))
        rest = (m["file_mb"] + cache) * (1 - on_gpu / (m["layers"] + 1))
        fits = rest <= ram_free
        return {**plan, "device": "gpu+cpu", "n_gpu_layers": on_gpu, "n_ctx": c, "kv": "q8_0", "gpu_layers": on_gpu, "fits": fits, "speed": "slow",
                "est_vram_mb": round(on_gpu * per_layer + RESERVE_MB),
                "notes": [f"{on_gpu} of {m['layers']} layers fit on the graphics card; the rest run on the processor (several times slower)" + ("" if fits else "; there is not enough RAM for that either")]}
    c, kv = options[-1] if ctx else (WANT_CTX[-1], "q8_0")
    c = min(c, ctx_max)
    cache = m["kv_bytes_per_token"] * c * 0.53125 / 2**20
    fits = m["file_mb"] + cache <= ram_free
    return {**plan, "device": "cpu", "n_gpu_layers": 0, "n_ctx": c, "kv": "f16", "gpu_layers": 0, "fits": fits, "speed": "very slow", "n_threads": hw.get("cores", 4), "est_vram_mb": 0,
            "notes": (["the installed llama-cpp-python was built without graphics-card support, so the card is not used: install its CUDA build (docs/INSTALL.md) or use LM Studio as the engine"]
                      if no_offload else ["no usable graphics card found: the model runs on the processor"]) + ([] if fits else ["it does not fit in RAM"])}


def best_fit(models_dir, files: list[str], hw: dict) -> str:
    """Of the model files in the folder, the largest one that runs fully on the card (the largest file is the strongest of what fits).
    If none does, the one that loses the least speed."""
    scored = []
    for name in files:
        try:
            p = plan_load(pathlib.Path(models_dir) / name, hw)
        except (OSError, ValueError, struct.error):
            continue
        scored.append((p["device"] == "gpu", p["fits"], -p["file_mb"] if p["device"] != "gpu" else p["file_mb"], name))
    return max(scored)[3] if scored else ""


def biggest_file_mb(hw: dict, ctx: int = 32768) -> int:
    """About how large a model file can be and still sit wholly on the card with `ctx` tokens of context (24B-class cache cost assumed)."""
    if not hw.get("gpus"):
        return 0
    cache = 164 * 1024 * ctx * 0.53125 / 2**20            # ~0.16 MB per token at 16-bit for a 24B-class model, halved by an 8-bit cache
    return max(0, int(hw["gpus"][0]["free_mb"] - RESERVE_MB - cache))


def probe(url: str, api_key: str = "") -> list[str]:
    """Ask a server which models it has. Raises on failure."""
    req = urllib.request.Request(url.rstrip("/") + "/models", headers={"Authorization": "Bearer " + api_key} if api_key else {})
    with urllib.request.urlopen(req, timeout=5) as r:
        return [m["id"] for m in json.load(r).get("data", [])]
