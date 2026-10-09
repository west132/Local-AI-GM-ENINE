import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from localgm import backend, modelcheck


class Good:
    """A model that answers every form correctly."""
    def ask(self, system, user, schema=None, max_tokens=None):
        if "REPLY with one JSON" not in system:
            return "Hobb looks up from the desk and shakes his head slowly. The big rooms are taken, he says, but the attic is free if you don't mind the stairs, and the price is a little higher."
        form = system.split("REPLY with one JSON")[1]
        if "kind:" in form:
            return {"kind": "fast", "steps": [], "note": "It simply happens."}
        if "verdict" in form:
            return {"verdict": "certain", "cites": ["locations.harbour_guesthouse"]}
        if "asks" in form and "minutes" not in form:
            return {"asks": []}
        if "minutes" in form:
            return {"minutes": 20, "ops": []}
        return {"ok": True}


def test_a_capable_model_passes_every_check():
    res = modelcheck.run(Good())
    assert res["passed"] == res["total"] == 7 and res["verdict"].startswith("Good")


def test_a_model_that_cannot_fill_the_forms_is_told_so_with_reasons():
    res = modelcheck.run(backend.Demo())
    assert res["passed"] < 5 and "Good" not in res["verdict"]
    assert all(r["note"] for r in res["rows"]) and any("no usable reply" in r["note"] for r in res["rows"])


def test_a_model_that_echoes_the_player_instead_of_telling_fails_the_telling_check():
    class Echo(Good):
        def ask(self, system, user, schema=None, max_tokens=None):
            if "REPLY with one JSON" not in system:
                return "I ask Hobb for a room."
            return super().ask(system, user, schema, max_tokens)
    res = modelcheck.run(Echo())
    assert not next(r for r in res["rows"] if r["name"] == "Tells the scene")["ok"]
