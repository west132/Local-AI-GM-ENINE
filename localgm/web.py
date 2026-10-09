"""The app: home page, settings page, play page. Everything is changed with buttons; nothing is edited by hand.
python -m localgm.web [--port 8765]"""
from __future__ import annotations
import argparse, html, json, pathlib, shutil, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import backend, flow, modelcheck, savefile, settings as S
from .store import Game

HERE = pathlib.Path(__file__).resolve().parent.parent
CSS = """
:root{--bg:#fafaf7;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#dcdcd4;--acc:#2d5f4a;--bad:#a33}
@media(prefers-color-scheme:dark){:root{--bg:#17181a;--fg:#e8e8e3;--mut:#9a9a93;--card:#1f2124;--line:#34363a;--acc:#6fb59a;--bad:#e07a7a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
nav{display:flex;gap:16px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line);background:var(--card)}
nav a{color:var(--fg);text-decoration:none;font-weight:600}nav a:hover{color:var(--acc)}nav .sp{flex:1}
main{max-width:860px;margin:0 auto;padding:16px}h1{font-size:1.4rem}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:12px 0}
label{display:block;margin:10px 0 2px;font-weight:600}input,select,textarea{width:100%;padding:8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);font:inherit}
button,.btn{background:var(--acc);color:#fff;border:0;border-radius:6px;padding:8px 14px;font:inherit;cursor:pointer;text-decoration:none;display:inline-block}
button.alt{background:transparent;color:var(--fg);border:1px solid var(--line)}.mut{color:var(--mut)}.bad{color:var(--bad)}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.row>*{flex:0 0 auto}.row .grow{flex:1 1 200px}
.log .you{color:var(--acc);margin-top:14px;font-weight:600}.log .roll{font-family:ui-monospace,monospace;font-size:.85rem;color:var(--mut);white-space:pre-wrap}
.log .prose{white-space:pre-wrap}.hdr{font-family:ui-monospace,monospace;font-size:.85rem;color:var(--mut)}
@media(max-width:600px){main{padding:12px}}
"""


def page(title: str, body: str, extra_head: str = "") -> bytes:
    nav = '<nav><a href="/">Home</a><a href="/settings">Settings</a><span class="sp"></span><span class="mut">Local AI GM</span></nav>'
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{CSS}</style>{extra_head}</head><body>{nav}<main>{body}</main></body></html>').encode()


class App:
    def __init__(self, root="."):
        self.root = pathlib.Path(root)
        self.settings = S.Settings(root)
        self.ai = None
        self.ai_key = None
        self.job: dict = {"state": "idle"}
        self.lock = threading.Lock()

    # ----- the model -----
    def model(self):
        key = json.dumps(self.settings.data, sort_keys=True)
        if self.ai is None or key != self.ai_key:
            self.ai, self.ai_key = None, None
            self.ai = backend.make(self.settings)
            self.ai_key = key
        return self.ai

    # ----- background work: one at a time (one GPU) -----
    def start(self, game: str, what: str, fn) -> bool:
        with self.lock:
            if self.job.get("state") == "running":
                return False
            self.job = {"state": "running", "game": game, "what": what, "step": "starting", "t0": time.time()}
        flow.on_step = lambda sid: self.job.update(step=sid)

        def run():
            try:
                self.job["result"] = fn()
                self.job["state"] = "done"
            except Exception as e:      # shown on the page; nothing is swallowed
                self.job.update(state="error", error=f"{type(e).__name__}: {e}")
            finally:
                flow.on_step = None
        threading.Thread(target=run, daemon=True).start()
        return True

    def games(self) -> list[dict]:
        out = []
        for d in sorted(self.settings.saves.glob("*/state.json"), key=lambda p: -p.stat().st_mtime):
            s = json.loads(d.read_text(encoding="utf-8"))
            out.append({"name": d.parent.name, "round": s["round"], "place": s["tree"]["world_state"]["location"],
                        "world": s["tree"].get("background_id", ""), "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(d.stat().st_mtime))})
        return out

    def worlds(self) -> list[str]:
        d = HERE / "examples"
        return sorted(p.parent.name for p in d.glob("*/background.md"))

    def open(self, name: str) -> Game:
        return Game.open(self.settings.saves, name)


APP: App


# ---------- pages ----------

def home() -> bytes:
    rows = "".join(
        f'<div class="card row"><div class="grow"><b>{html.escape(g["name"])}</b><div class="mut">{html.escape(g["world"])} · round {g["round"]} · '
        f'{html.escape(g["place"])} · {g["when"]}</div></div><a class="btn" href="/play/{urllib.parse.quote(g["name"])}">Continue</a>'
        f'<form method="post" action="/delete" onsubmit="return confirm(\'Delete this game and all its saves?\')">'
        f'<input type="hidden" name="name" value="{html.escape(g["name"])}"><button class="alt">Delete</button></form></div>'
        for g in APP.games()) or '<p class="mut">No games yet.</p>'
    opts = "".join(f'<option value="{w}">{w}</option>' for w in APP.worlds())
    model = APP.settings.data
    where = {"gguf": f"model file: {model['gguf'] or 'first in models folder'}", "server": f"server: {model['url']}", "demo": "demo (no AI)"}[model["backend"]]
    body = f'''<h1>Your games</h1>{rows}
<h1>New game</h1><form class="card" method="post" action="/new" enctype="application/x-www-form-urlencoded">
<label>Game name</label><input name="name" required pattern="[A-Za-z0-9_\\-]+" title="letters, numbers, - and _" placeholder="my_game">
<label>World</label><select name="world">{opts}<option value="__paste">Paste my own BACKGROUND…</option></select>
<div id="paste" hidden><label>BACKGROUND text</label><textarea name="background" rows="8"></textarea></div>
<p class="mut">AI: {html.escape(where)} — change it in <a href="/settings">Settings</a>.</p><button>Start</button></form>
<script>const s=document.querySelector('select[name=world]');s.onchange=()=>document.getElementById('paste').hidden=s.value!='__paste'</script>
<h1>Continue from a save file</h1><form class="card" method="post" action="/import">
<p class="mut">A SAVE file made in a chat (or exported here). Choose the world it belongs to.</p>
<label>Game name</label><input name="name" required pattern="[A-Za-z0-9_\\-]+" placeholder="my_game_r10">
<label>World</label><select name="world">{opts}<option value="__paste">Paste my own BACKGROUND…</option></select>
<div id="paste2" hidden><label>BACKGROUND text</label><textarea name="background" rows="5"></textarea></div>
<label>Save file</label><input type="file" id="savefile" accept=".md,.txt"><textarea name="save" id="savetext" rows="4" required placeholder="…or paste the save here"></textarea>
<button>Import and continue</button></form>
<script>document.querySelectorAll('select[name=world]')[1].onchange=e=>document.getElementById('paste2').hidden=e.target.value!='__paste';
document.getElementById('savefile').onchange=async e=>{{document.getElementById('savetext').value=await e.target.files[0].text()}}</script>'''
    return page("Home", body)


def settings_page(msg="", errs=()) -> bytes:
    d = APP.settings.data
    files = APP.settings.ggufs()

    def sel(name, options, cur):
        return f'<select name="{name}">' + "".join(f'<option value="{html.escape(o)}"{" selected" if o == cur else ""}>{html.escape(o or "(first one found)")}</option>' for o in options) + "</select>"
    notes = "".join(f'<p class="bad">{html.escape(e)}</p>' for e in errs) + (f'<p style="color:var(--acc)">{html.escape(msg)}</p>' if msg else "")
    body = f'''<h1>Settings</h1>{notes}<form class="card" method="post" action="/settings">
<label>Where the AI runs</label>{sel("backend", S.CHOICES["backend"], d["backend"])}
<p class="mut">gguf = a model file you put in the <code>models</code> folder · server = LM Studio / Ollama · demo = no AI, just to try the app</p>
<label>Model file (in the models folder — {len(files)} found)</label>{sel("gguf", [""] + files, d["gguf"])}
<label>Server address (LM Studio default shown)</label><input name="url" value="{html.escape(d["url"])}">
<label>Server model name (blank = whatever is loaded)</label><input name="model" value="{html.escape(d["model"])}">
<label>Context size (tokens, model file only)</label><input name="ctx" type="number" value="{d["ctx"]}">
<label>Temperature (0–2)</label><input name="temperature" type="number" step="0.05" value="{d["temperature"]}">
<label>Longest single reply (tokens)</label><input name="max_tokens" type="number" value="{d["max_tokens"]}">
<label>Language</label>{sel("language", S.CHOICES["language"], d["language"])}
<div class="row" style="margin-top:14px"><button>Save</button><button type="button" class="alt" id="test">Test the AI</button><button type="button" class="alt" id="check">Check this model (7 short calls)</button><a class="btn alt" href="/">Back to Home</a></div>
<p id="t" class="mut"></p><div id="chk"></div></form>
<script>document.getElementById('test').onclick=async()=>{{const f=new FormData(document.querySelector('form'));
document.getElementById('t').textContent='Testing…';const r=await fetch('/settings/test',{{method:'POST',body:new URLSearchParams(f)}});
document.getElementById('t').textContent=(await r.json()).message}}
document.getElementById('check').onclick=async()=>{{const f=new FormData(document.querySelector('form'));
const t=document.getElementById('t'),box=document.getElementById('chk');box.innerHTML='';
const r=await fetch('/settings/check',{{method:'POST',body:new URLSearchParams(f)}});if(!r.ok){{t.textContent=await r.text();return}}
while(true){{const j=await (await fetch('/api/check/status')).json();
 if(j.state=='running'){{t.textContent='Checking… '+j.step+' ('+j.secs+'s)';await new Promise(x=>setTimeout(x,1500));continue}}
 if(j.state=='error'){{t.textContent=j.error;return}}
 const c=j.result.check;t.textContent=c.passed+'/'+c.total+' — '+c.verdict+' ('+c.calls+' calls, '+c.secs+'s)';
 box.innerHTML='<table style="width:100%;border-collapse:collapse">'+c.rows.map(x=>'<tr><td>'+(x.ok?'✔':'✘')+'</td><td>'+x.name+'</td><td class="mut">'+x.secs+'s'+(x.retried?' · retried':'')+'</td><td class="mut">'+x.note.replace(/</g,'&lt;')+'</td></tr>').join('')+'</table>';return}}}}</script>'''
    return page("Settings", body)


def play_page(name: str) -> bytes:
    g = APP.open(name)
    log = ""
    jp = g.dir / "journal.jsonl"
    if jp.exists():
        for l in jp.read_text(encoding="utf-8").splitlines():
            e = json.loads(l)
            log += turn_html(e["input"], e.get("lines", []), e.get("prose", ""), e.get("header", ""))
    rounds = "".join(f'<option value="{int(p.stem)}">{int(p.stem)}</option>' for p in sorted((g.dir / "snapshots").glob("*.json")))
    body = f'''<div class="row"><h1 class="grow">{html.escape(name)}</h1><span class="hdr" id="hdr">{html.escape(header(g.world))}</span></div>
<div class="card log" id="log">{log or '<span class="mut">Say what you do.</span>'}</div>
<div class="card"><form id="f" class="row"><input class="grow" id="in" autocomplete="off" placeholder="What do you do?" autofocus>
<button id="go">Send</button></form><p id="st" class="mut"></p>
<div class="row"><a class="btn alt" href="/">Home</a><a class="btn alt" href="/settings">Settings</a><a class="btn alt" href="/export/{urllib.parse.quote(name)}">Export save</a>
<form id="rw" class="row"><select id="rn">{rounds}</select><button class="alt">Go back to this round</button></form></div></div>
<script>
const N={json.dumps(name)},$=id=>document.getElementById(id);
function esc(s){{return s.replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]))}}
function add(e){{ $('log').insertAdjacentHTML('beforeend',e) }}
async function poll(){{ const r=await (await fetch('/api/'+N+'/status')).json();
 if(r.state=='running'){{ $('st').textContent='Working… ('+r.step+', '+r.secs+'s)'; setTimeout(poll,1500); return }}
 $('go').disabled=false; $('st').textContent='';
 if(r.state=='error'){{ $('st').innerHTML='<span class="bad">'+esc(r.error)+'</span>'; return }}
 if(r.result&&r.result.html){{ add(r.result.html); $('hdr').textContent=r.result.header; window.scrollTo(0,document.body.scrollHeight) }}
 if(r.result&&r.result.reload) location.reload() }}
$('f').onsubmit=async ev=>{{ev.preventDefault(); const t=$('in').value.trim(); if(!t) return; $('in').value=''; $('go').disabled=true;
 const r=await fetch('/api/'+N+'/turn',{{method:'POST',body:new URLSearchParams({{text:t}})}});
 if(!r.ok){{ $('st').textContent=await r.text(); $('go').disabled=false; return }} poll()}};
$('rw').onsubmit=async ev=>{{ev.preventDefault(); if(!confirm('Go back to round '+$('rn').value+'? Later rounds are removed.')) return;
 await fetch('/api/'+N+'/rewind',{{method:'POST',body:new URLSearchParams({{round:$('rn').value}})}}); location.reload()}};
poll();
</script>'''
    return page(name, body)


def header(w) -> str:
    from .__main__ import header as h
    return h(w)


def turn_html(text: str, lines: list[str], prose: str, hdr: str = "") -> str:
    return (f'<div class="you">&gt; {html.escape(text)}</div>' + (f'<div class="hdr">{html.escape(hdr)}</div>' if hdr else "")
            + "".join(f'<div class="roll">{html.escape(l)}</div>' for l in lines) + f'<div class="prose">{html.escape(prose)}</div>')


# ---------- request handling ----------

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body: bytes, code=200, ctype="text/html; charset=utf-8", headers=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, to: str):
        self.send(b"", 303, headers=[("Location", to)])

    def json(self, obj, code=200):
        self.send(json.dumps(obj, ensure_ascii=False).encode(), code, "application/json")

    def form(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8"), keep_blank_values=True).items()}

    def do_GET(self):
        path = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in path.path.strip("/").split("/") if p]
        try:
            if not parts:
                return self.send(home())
            if parts == ["settings"]:
                return self.send(settings_page())
            if parts[0] == "play" and len(parts) == 2:
                return self.send(play_page(parts[1]))
            if parts[0] == "export" and len(parts) == 2:
                g = APP.open(parts[1])
                body = savefile.export_save(g.world, (g.dir / "background.md").read_text(encoding="utf-8"), parts[1]).encode()
                return self.send(body, 200, "text/markdown; charset=utf-8", [("Content-Disposition", f'attachment; filename="save_{parts[1]}_R{g.world.round}.md"')])
            if parts[0] == "api" and len(parts) == 3 and parts[2] == "status":
                j = dict(APP.job)
                out = {"state": j.get("state", "idle"), "step": j.get("step", ""), "secs": int(time.time() - j["t0"]) if "t0" in j else 0}
                if j.get("state") in ("done", "error") and j.get("game") == parts[1]:
                    out["result"], out["error"] = j.get("result"), j.get("error")
                    APP.job = {"state": "idle"}
                return self.json(out)
            self.send(page("Not found", '<h1>Not found</h1><p><a href="/">Home</a></p>'), 404)
        except FileNotFoundError:
            self.send(page("Not found", '<h1>No such game</h1><p><a href="/">Home</a></p>'), 404)

    def do_POST(self):
        parts = [urllib.parse.unquote(p) for p in urllib.parse.urlparse(self.path).path.strip("/").split("/") if p]
        f = self.form()
        try:
            if parts == ["settings"]:
                errs = APP.settings.update(f)
                return self.send(settings_page("Saved." if not errs else "", errs))
            if parts == ["settings", "check"]:
                for k, v in f.items():
                    if k in ("backend", "url", "model", "gguf"):
                        APP.settings.data[k] = v          # check what is on the page; Save is still the player's choice
                started = APP.start("check", "check", lambda: {"check": modelcheck.run(APP.model(), lambda i, n: APP.job.update(step=n))})
                return self.json({"started": started}) if started else self.send(b"The AI is busy with another job.", 409, "text/plain")
            if parts == ["settings", "test"]:
                return self.json({"message": self.test_ai(f)})
            if parts == ["delete"]:
                name = pathlib.Path(f["name"]).name
                shutil.rmtree(APP.settings.saves / name, ignore_errors=True)
                return self.redirect("/")
            if parts == ["new"]:
                return self.new_game(f)
            if parts == ["import"]:
                return self.import_game(f)
            if parts[0] == "api" and len(parts) == 3:
                name = parts[1]
                if parts[2] == "turn":
                    return self.turn(name, f.get("text", "").strip())
                if parts[2] == "rewind":
                    g = APP.open(name)
                    g.rewind(int(f["round"]))
                    return self.json({"ok": True})
            self.send(b"not found", 404, "text/plain")
        except Exception as e:
            self.send(f"{type(e).__name__}: {e}".encode(), 400, "text/plain; charset=utf-8")

    def test_ai(self, f) -> str:
        probe = S.Settings.__new__(S.Settings)
        probe.__dict__.update(APP.settings.__dict__)
        probe.data = dict(APP.settings.data)
        try:
            for k, v in f.items():
                if k in probe.data and k in ("backend", "url", "model", "gguf"):
                    probe.data[k] = v
            if probe.data["backend"] == "server":
                ms = backend.probe(probe.data["url"])
                return f"Connected. Models on the server: {', '.join(ms) or 'none loaded'}"
            if probe.data["backend"] == "demo":
                return "Demo mode: no AI is used."
            files = probe.ggufs()
            return f"Found {len(files)} model file(s): {', '.join(files)}" if files else "No .gguf file in the models folder yet."
        except Exception as e:
            return f"Cannot reach it: {e}"

    def new_game(self, f):
        name = pathlib.Path(f["name"]).name
        if f.get("world") == "__paste":
            text = f.get("background", "")
        else:
            text = (HERE / "examples" / pathlib.Path(f["world"]).name / "background.md").read_text(encoding="utf-8")
        g = Game.new(APP.settings.saves, name, text)

        def setup():
            flow.intake(g.world, APP.model())
            g.save()
            return {"reload": True}
        if not APP.start(name, "intake", setup):
            return self.send(page("Busy", '<p>The AI is busy with another job. <a href="/">Home</a></p>'), 409)
        self.redirect(f"/play/{urllib.parse.quote(name)}")

    def import_game(self, f):
        name = pathlib.Path(f["name"]).name
        bg = f.get("background", "") if f.get("world") == "__paste" else \
            (HERE / "examples" / pathlib.Path(f["world"]).name / "background.md").read_text(encoding="utf-8")
        try:
            world, notes = savefile.import_save(f["save"], bg)
        except Exception as e:
            return self.send(page("Cannot read that save", f'<h1>Cannot read that save</h1><p class="bad">{html.escape(type(e).__name__ + ": " + str(e))}</p>'
                                  '<p>Check that the world chosen is the one the save was made on.</p><p><a href="/">Home</a></p>'), 400)
        g = Game.from_world(APP.settings.saves, name, bg, world)
        if world.needs_intake():
            def setup():
                flow.intake(g.world, APP.model())
                g.save()
                return {"reload": True}
            APP.start(name, "intake", setup)
        self.redirect(f"/play/{urllib.parse.quote(name)}")

    def turn(self, name: str, text: str):
        if not text:
            return self.send(b"say something", 400, "text/plain")
        g = APP.open(name)

        def run():
            t = flow.run_turn(g.world, APP.model(), text)
            hdr = header(g.world)
            g.log({"input": text, "sort": t.sort, "lines": t.lines, "facts": t.facts, "events": t.events, "prose": t.prose, "header": hdr})
            g.save()
            return {"html": turn_html(text, t.lines + [f"Cash: {' '.join(str(x) for x in g.world.cash() if x != '')}"], t.prose, hdr), "header": hdr}
        if not APP.start(name, "turn", run):
            return self.send(b"The AI is still working on the last turn.", 409, "text/plain")
        self.json({"started": True})


def main(argv=None):
    global APP
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--root", default=".")
    ap.add_argument("--open", action="store_true", help="open the browser")
    a = ap.parse_args(argv)
    APP = App(a.root)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"Local AI GM: http://127.0.0.1:{a.port}")
    if a.open:
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{a.port}")).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
