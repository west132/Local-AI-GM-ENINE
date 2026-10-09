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
    s.update({"backend": "gguf", "device": "cpu", "threads": "6", "ctx": "4096"})
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
