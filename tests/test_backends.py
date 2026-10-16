import json, pathlib, sys, threading, types
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from localgm import backend, flow
from localgm.settings import Settings
from test_loops import run
from test_flow import world


class Srv(BaseHTTPRequestHandler):
    seen = []
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        Srv.seen.append((self.headers.get("Authorization"), body))
        if self.headers.get("Authorization") != "Bearer sk-secret-1234":
            self.send_response(401); self.end_headers(); return
        out = json.dumps({"choices": [{"message": {"content": '{"ok": true}'}}]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def do_GET(self):
        out = json.dumps({"data": [{"id": "model-a"}]}).encode()
        Srv.seen.append((self.headers.get("Authorization"), self.path))
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), Srv)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Srv.seen.clear()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


def test_the_api_key_is_sent_as_a_header_only(server):
    ai = backend.OpenAICompat(server, "m", api_key="sk-secret-1234")
    assert ai.ask("system rules", "user text", {"type": "object", "properties": {"ok": {"type": "boolean"}}}) == {"ok": True}
    auth, body = Srv.seen[-1]
    assert auth == "Bearer sk-secret-1234" and "sk-secret" not in body
    assert backend.probe(server, "sk-secret-1234") == ["model-a"] and Srv.seen[-1][0] == "Bearer sk-secret-1234"


def test_a_refused_key_gives_a_plain_error_without_the_key(server):
    ai = backend.OpenAICompat(server, "m", api_key="sk-wrong-9999")
    with pytest.raises(ConnectionError) as e:
        ai.ask("s", "u", None)
    assert "key was refused" in str(e.value) and "sk-wrong" not in str(e.value)


def test_settings_keep_the_key_hidden_and_validate(tmp_path):
    s = Settings(tmp_path)
    assert s.update({"backend": "api", "api_key": "sk-secret-1234", "url": "https://x/v1"}) == []
    assert s.key_hint() == "saved (…1234)"
    s.update({"api_key": "", "model": "m2"})                           # a blank box keeps the key
    assert s.api_key() == "sk-secret-1234" and s.data["model"] == "m2"
    s.update({"clear_api_key": "1"})
    assert s.api_key() == ""
    assert any("threads" in p for p in s.update({"threads": "999"})) and any("device" in p for p in s.update({"device": "gpu"}))


def test_the_three_backends_are_built_from_settings(tmp_path, monkeypatch):
    (tmp_path / "models").mkdir(); (tmp_path / "models" / "m.gguf").write_bytes(b"x")
    s = Settings(tmp_path)
    s.update({"backend": "api", "url": "https://x/v1", "model": "gpt"})
    with pytest.raises(ValueError, match="API key"):
        backend.make(s)
    s.update({"api_key": "k" * 12})
    ai = backend.make(s)
    assert isinstance(ai, backend.OpenAICompat) and ai._headers()["Authorization"] == "Bearer " + "k" * 12
    seen = {}
    class FakeLlama:
        def __init__(self, **kw): seen.update(kw)
    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=FakeLlama))
    s.update({"backend": "gguf", "tuning": "manual", "device": "cpu", "threads": "6", "ctx": "4096"})
    backend.make(s)
    assert seen["n_gpu_layers"] == 0 and seen["n_threads"] == 6 and seen["n_ctx"] == 4096
    s.update({"device": "auto", "threads": "0"})
    seen.clear()
    backend.make(s)
    assert seen["n_gpu_layers"] == -1 and "n_threads" not in seen


def test_fewer_calls_per_turn_when_asked():
    base = flow.run_turn(world(), __import__("test_loops").Bot(sort={"kind": "loop", "steps": ["react"]}), "x")
    few = flow.run_turn(world(), __import__("test_loops").Bot(sort={"kind": "loop", "steps": ["react"]}), "x", merge_questions=True, check_telling=False)
    assert "wonder" in base.ran and "audit" in base.ran
    assert "wonder" not in few.ran and "audit" not in few.ran and "react" in few.ran and "tell" in few.ran


def test_a_merged_world_step_can_ask_and_then_decide():
    from test_loops import Bot
    ask = {"asks": [{"question": "Does Hobb have a room for the night?", "obvious": "YES - it is a guesthouse and he is the owner", "likelihood": 1}]}
    t = flow.run_turn(world(), Bot(sort={"kind": "loop", "steps": ["react"]}, react=[ask, {"asks": [], "report": "It happens.", "minutes": 5, "ops": []}]),
                      "I ask Hobb for a room", merge_questions=True)
    assert "wonder" not in t.ran and any("settled" in r for r in t.results) and t.ran.count("react") == 2


def test_home_knows_whether_this_ai_was_checked(tmp_path):
    s = Settings(tmp_path)
    s.update({"backend": "server", "model": "m1"})
    assert s.check_status()[0] == "none"
    s.remember_check({"passed": 7, "total": 7, "verdict": "Good"})
    assert s.check_status() == ("good", "AI check: 7/7 — Good")
    s.update({"model": "m2"})                                             # another model: the old result does not apply
    assert s.check_status()[0] == "none"
    s.update({"model": "m1"}); s.remember_check({"passed": 3, "total": 7, "verdict": "Weak"})
    assert s.check_status()[0] == "weak"
    s.update({"backend": "demo"})
    assert s.check_status()[0] == "demo"


# ---------- the same scripted game through every adapter ----------

def _scenario_bot():
    from test_loops import Bot
    ask = {"asks": [{"question": "Does Hobb have a room for the night?", "obvious": "YES - it is a guesthouse and he is the owner", "likelihood": 1}]}
    return Bot(sort={"kind": "loop", "steps": ["react"]}, react=[ask, {"asks": [], "report": "Hobb hands over a key.", "minutes": 10,
               "ops": [{"op": "set", "path": "npcs.hobb_marren.state.status", "value": "has given Rin a room key", "requires": {"on": "Does Hobb have a room for the night?", "answer": "YES"}}]}],
               tell="Hobb slides a brass key across the desk.")


def _play(llm):
    w = world()
    t = flow.run_turn(w, llm, "I ask Hobb for a room")
    return w, t


def test_the_same_game_gives_the_same_world_through_every_adapter(server, monkeypatch):
    direct_w, direct_t = _play(_scenario_bot())
    bot = _scenario_bot()

    class Play(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            system, user = req["messages"][0]["content"], req["messages"][1]["content"]
            schema = req.get("response_format", {}).get("json_schema", {}).get("schema")
            r = bot.ask(system, user, schema)
            out = json.dumps({"choices": [{"message": {"content": r if isinstance(r, str) else json.dumps(r)}}]}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    srv = HTTPServer(("127.0.0.1", 0), Play)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    http_w, http_t = _play(backend.OpenAICompat(f"http://127.0.0.1:{srv.server_port}/v1", "m"))
    srv.shutdown()

    bot2 = _scenario_bot()
    class FakeLlama:
        def __init__(self, **kw): pass
        def create_chat_completion(self, messages, temperature, max_tokens, response_format=None, **kw):
            schema = (response_format or {}).get("schema")
            r = bot2.ask(messages[0]["content"], messages[1]["content"], schema)
            return {"choices": [{"message": {"content": r if isinstance(r, str) else json.dumps(r)}}]}
    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=FakeLlama))
    gguf_w, gguf_t = _play(backend.LlamaCpp("x.gguf", 4096, 0))

    for w, t in ((http_w, http_t), (gguf_w, gguf_t)):
        assert w.tree == direct_w.tree and w.round == 1
        assert t.prose == direct_t.prose == "Hobb slides a brass key across the desk."
        assert any("WHAT HAPPENED" in f and "hands over a key" in f for f in t.facts)
    assert direct_w.get("npcs.hobb_marren.state.status") == "has given Rin a room key"


# ---------- reading this PC and the model file, and choosing the load settings ----------

def fake_gguf(path, size_mb, layers=40, heads=32, kv_heads=8, emb=5120, head_dim=128, ctx=131072, arch="llama"):
    """A real GGUF header (with a tokenizer-sized string array in front, as real files have) over a sparse body of the wanted size."""
    import struct
    def string(x): b = x.encode(); return struct.pack("<Q", len(b)) + b
    kvs = [(string("general.architecture"), 8, string(arch)), (string("general.name"), 8, string(path.stem)),
           (string("tokenizer.ggml.tokens"), 9, struct.pack("<IQ", 8, 3) + string("a") + string("bb") + string("ccc")),
           (string(f"{arch}.block_count"), 4, struct.pack("<I", layers)), (string(f"{arch}.context_length"), 4, struct.pack("<I", ctx)),
           (string(f"{arch}.embedding_length"), 4, struct.pack("<I", emb)), (string(f"{arch}.attention.head_count"), 4, struct.pack("<I", heads)),
           (string(f"{arch}.attention.head_count_kv"), 4, struct.pack("<I", kv_heads)), (string(f"{arch}.attention.key_length"), 4, struct.pack("<I", head_dim))]
    head = b"GGUF" + struct.pack("<IQQ", 3, 0, len(kvs)) + b"".join(k + struct.pack("<I", t) + v for k, t, v in kvs)
    with open(path, "wb") as f:
        f.write(head)
        f.truncate(int(size_mb * 2**20))
    return path


RTX = {"gpus": [{"name": "NVIDIA GeForce RTX 3090 Ti", "vram_mb": 24564, "free_mb": 23000}], "ram_mb": 32000, "threads": 24, "cores": 12, "offload": True}


def test_the_model_file_header_gives_its_size_layers_and_cache_cost(tmp_path):
    m = backend.read_gguf(fake_gguf(tmp_path / "mistral-24b.gguf", 14336))
    assert m["layers"] == 40 and round(m["file_mb"]) == 14336 and m["kv_bytes_per_token"] == 2 * 40 * 8 * 128 * 2 and m["trained_ctx"] == 131072
    (tmp_path / "x.gguf").write_bytes(b"not a model at all")
    with pytest.raises(ValueError, match="not a .gguf"):
        backend.read_gguf(tmp_path / "x.gguf")


def test_the_pc_is_read_from_the_driver_and_the_system(monkeypatch):
    monkeypatch.setattr(backend, "_run", lambda cmd: "NVIDIA GeForce RTX 3090 Ti, 24564, 23800\n" if "--query-gpu=name,memory.total,memory.free" in " ".join(cmd) else "")
    monkeypatch.setattr(backend, "_ram_mb", lambda: 32768)
    monkeypatch.setattr(backend, "_offload", lambda: True)
    hw = backend.scan()
    assert hw["gpus"] == [{"name": "NVIDIA GeForce RTX 3090 Ti", "vram_mb": 24564, "free_mb": 23800}] and hw["ram_mb"] == 32768 and hw["cores"] >= 1
    monkeypatch.setattr(backend, "_run", lambda cmd: "")
    assert backend.scan()["gpus"] == []                                                # no driver, no card: the processor


def test_the_load_settings_follow_what_fits_on_the_card(tmp_path):
    q4 = backend.plan_load(fake_gguf(tmp_path / "q4.gguf", 14336), RTX)                  # a 24B model at Q4: everything fits, full-size cache, 32k
    assert (q4["device"], q4["n_gpu_layers"], q4["n_ctx"], q4["kv"], q4["fits"]) == ("gpu", -1, 32768, "f16", True)
    q5 = backend.plan_load(fake_gguf(tmp_path / "q5.gguf", 17408), RTX)                  # Q5: the cache is halved (8-bit) to keep it all on the card
    assert (q5["device"], q5["n_ctx"], q5["kv"]) == ("gpu", 32768, "q8_0")
    q6 = backend.plan_load(fake_gguf(tmp_path / "q6.gguf", 20480), RTX)                  # Q6 does not leave room: some layers go to the processor
    assert q6["device"] == "gpu+cpu" and 0 < q6["n_gpu_layers"] < 40 and q6["speed"] == "slow" and q6["fits"] and q6["n_ctx"] == 24576
    big = backend.plan_load(fake_gguf(tmp_path / "big.gguf", 60000), {**RTX, "ram_mb": 16000})
    assert not big["fits"] and "RAM" in " ".join(big["notes"])
    cpu = backend.plan_load(fake_gguf(tmp_path / "small.gguf", 2000), {"gpus": [], "ram_mb": 16000, "threads": 8, "cores": 4, "offload": None})
    assert (cpu["device"], cpu["n_gpu_layers"], cpu["n_threads"]) == ("cpu", 0, 4) and cpu["fits"]
    plain = backend.plan_load(fake_gguf(tmp_path / "q4b.gguf", 14336), {**RTX, "offload": False})
    assert plain["device"] == "cpu" and "CUDA build" in " ".join(plain["notes"])        # the card is there but the installed library cannot use it
    short = backend.plan_load(fake_gguf(tmp_path / "short.gguf", 4000, ctx=8192), RTX)
    assert short["n_ctx"] == 8192                                                        # never more context than the model was trained for


def test_the_best_file_is_the_largest_one_that_sits_wholly_on_the_card(tmp_path):
    for n, mb in (("q4.gguf", 14336), ("q5.gguf", 17408), ("q6.gguf", 20480), ("small.gguf", 4000)):
        fake_gguf(tmp_path / n, mb)
    assert backend.best_fit(tmp_path, ["q4.gguf", "q5.gguf", "q6.gguf", "small.gguf"], RTX) == "q5.gguf"
    assert backend.best_fit(tmp_path, ["q6.gguf"], RTX) == "q6.gguf"                     # nothing fits wholly: still the least bad
    assert backend.best_fit(tmp_path, [], RTX) == "" and 18000 < backend.biggest_file_mb(RTX) < 22000


def test_automatic_mode_loads_the_file_with_the_planned_settings_and_manual_mode_does_not(tmp_path, monkeypatch):
    (tmp_path / "models").mkdir()
    fake_gguf(tmp_path / "models" / "q4.gguf", 14336); fake_gguf(tmp_path / "models" / "q5.gguf", 17408)
    seen = {}
    class FakeLlama:
        def __init__(self, **kw): seen.update(kw)
    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=FakeLlama))
    s = Settings(tmp_path); s._hw = RTX
    s.update({"backend": "gguf"})
    backend.make(s)                                                                      # no file chosen: the best one for this PC, loaded the way it fits
    assert seen["model_path"].endswith("q5.gguf") and seen["n_gpu_layers"] == -1 and seen["n_ctx"] == 32768 and seen["type_k"] == 8 and seen["flash_attn"]
    seen.clear(); s.update({"gguf": "q4.gguf", "device": "cpu"})
    backend.make(s)
    assert seen["n_gpu_layers"] == 0                                                     # "never use the card" is still honoured in automatic mode
    seen.clear(); s.update({"device": "auto", "tuning": "manual", "ctx": "20000"})
    backend.make(s)
    assert seen["n_ctx"] == 20000 and "type_k" not in seen


def test_the_settings_page_shows_the_pc_and_what_will_be_done_with_the_chosen_file(tmp_path):
    from localgm import web
    (tmp_path / "models").mkdir()
    fake_gguf(tmp_path / "models" / "q5.gguf", 17408)
    web.APP = web.App(tmp_path)
    web.APP.settings._hw = RTX
    web.APP.settings.update({"backend": "gguf"})
    page = web.settings_page().decode()
    assert "RTX 3090 Ti" in page and "24 GB graphics memory" in page and "chosen as the best fit" in page and "all 40 layers on the graphics card" in page and "Scan this PC again" in page
    web.APP.settings.update({"backend": "server"})
    assert "GPU Offload" in web.settings_page().decode()
    web.APP.settings._hw = {**RTX, "offload": False}
    web.APP.settings.update({"backend": "gguf"})
    assert "cannot use the graphics card" in web.settings_page().decode()
