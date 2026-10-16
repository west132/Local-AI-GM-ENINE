import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from localgm import backend, modelcheck


class Good:
    """A model that answers every form correctly."""
    def ask(self, system, user, schema=None, max_tokens=None):
        if "REPLY with one JSON" not in system:
            return "Hobb looks up from the desk and shakes his head slowly. The big rooms are taken, he says, but the attic is free if you don't mind the stairs, and the price is a little higher."
        form = system.split("REPLY with one JSON")[1]
        if "mode:" in form:
            text = user.rsplit("PLAYER: ", 1)[1].split("\n")[0]
            scene = "Hobb looks up from the desk and shakes his head slowly. The big rooms are taken, he says, but the attic is free if you don't mind the stairs, and the price is a little higher."
            if "attack" in text:
                return {"mode": "fight", "foes": [{"id": "rat", "name": "rat", "v": 1, "size": "small"}], "kill": True,
                        "exchanges": [{"foe": "rat", "roll": {"capability": 0, "base": 8}, "on_success": "full", "my_source": "unarmed", "on_failure": "setback", "attackers": []}]}
            if "lock" in text:
                return {"mode": "roll", "cites": ["player"], "roll": {"subject": "pick_lock", "capability": 0, "base": 10, "stakes": {"success": "it opens", "failure": "it stays shut", "harm": "none"}}}
            if "whether he has a room" in text:
                return {"mode": "ask", "asks": [{"question": "Does Hobb have a room tonight?", "obvious": "YES - he runs a guesthouse", "likelihood": 0, "cites": ["npcs.hobb_marren"]}]}
            return {"mode": "done", "cites": ["npcs.hobb_marren"], "report": "It happens.", "minutes": 20, "ops": [], "scene": scene}
        return {"ok": True}


def test_a_capable_model_passes_every_check():
    res = modelcheck.run(Good())
    assert res["passed"] == res["total"] == 7 and res["verdict"].startswith("Good")


def test_a_model_that_cannot_fill_the_forms_is_told_so_with_reasons():
    class Junk:
        def ask(self, system, user, schema=None, max_tokens=None):
            if schema is None:
                return "ok"
            raise ValueError("not json")
    res = modelcheck.run(Junk())
    assert res["passed"] < 5 and "Good" not in res["verdict"]
    assert all(r["note"] for r in res["rows"]) and any("no usable reply" in r["note"] for r in res["rows"])


def test_a_model_that_echoes_the_player_instead_of_telling_fails_the_telling_check():
    class Echo(Good):
        def ask(self, system, user, schema=None, max_tokens=None):
            out = super().ask(system, user, schema, max_tokens)
            if isinstance(out, dict) and out.get("mode") == "done":
                out["scene"] = "I ask Hobb for a room. " * 5
            return out
    res = modelcheck.run(Echo())
    assert not next(r for r in res["rows"] if r["name"] == "Tells the scene")["ok"]
