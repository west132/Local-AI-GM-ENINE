"""Dice only where the outcome could honestly go either way (AI_RULES v4.2, engine 13.1): settle what is obvious, ask again as needed."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from localgm import flow, mechanics as M
from test_flow import Scripted, world, OK, LOOP_REACT
from test_rules import react
from test_authority import ASK, MOOD, force_ask


def counting_ask(monkeypatch, band="YES"):
    calls = []
    monkeypatch.setattr(M, "ask", lambda l, rng=None: calls.append(l) or {"dice": [5, 5], "likelihood": l, "total": 10 + l, "band": band})
    return calls


def test_an_obvious_answer_is_used_and_nothing_is_rolled(monkeypatch):
    calls = counting_ask(monkeypatch, "NO, AND")                  # the dice would have said no
    w = world()
    ask = ASK("Does Hobb sell a room to a paying guest?", obvious="YES - he runs a guesthouse and wants a full house", governs=["npcs.hobb_marren.state.mood"])
    llm = Scripted([LOOP_REACT, ask, react(ops=[MOOD("pleased", requires={"on": "Does Hobb sell a room to a paying guest?", "answer": "YES"})]), "He nods.", OK])
    t = flow.run_turn(w, llm, "I ask Hobb for a room")
    assert calls == [] and t.rolled == 0 and t.settled == 1 and t.lines == []
    assert "YES (settled): he runs a guesthouse" in llm.seen[2][1]        # the AI is told the settled answer
    assert w.get("npcs.hobb_marren.state.mood") == "pleased"
    assert [e["kind"] for e in w.tree["resolved"]] == ["settled"]       # it is a fact of the campaign like any result


def test_a_settled_answer_binds_the_ai_like_a_roll(monkeypatch):
    counting_ask(monkeypatch)
    w = world()
    ask = ASK("Does Hobb sell a room to a paying guest?", obvious="YES - plain", governs=["npcs.hobb_marren.state.mood"])
    bad = react(ops=[MOOD("refuses", requires={"on": "Does Hobb sell a room to a paying guest?", "answer": "NO"})])
    good = react(ops=[MOOD("pleased", requires={"on": "Does Hobb sell a room to a paying guest?", "answer": "YES"})])
    llm = Scripted([LOOP_REACT, ask, bad, good, "ok", OK])
    flow.run_turn(w, llm, "x")
    assert "the result was YES (settled)" in llm.seen[3][1] and w.get("npcs.hobb_marren.state.mood") == "pleased"


def test_obvious_none_is_rolled_and_a_malformed_obvious_is_sent_back(monkeypatch):
    calls = counting_ask(monkeypatch)
    w = world()
    llm = Scripted([LOOP_REACT, ASK("Does Hobb sell a room?", obvious="maybe"), ASK("Does Hobb sell a room?", obvious="none", for_="x") | {},
                    react(), "ok", OK])
    # the second reply is valid: 'none' and no likelihood to justify
    flow.run_turn(w, llm, "x")
    assert "'obvious' is 'none' or" in llm.seen[2][1] and len(calls) == 1


def test_the_ai_can_ask_again_after_seeing_a_result_and_the_dice_are_not_capped(monkeypatch):
    calls = counting_ask(monkeypatch, "YES")
    w = world()
    first = react(asks=[{"question": "Is the desk clerk in?", "obvious": "none", "likelihood": 0}])
    second = react(asks=[{"question": "Does the clerk know the guest?", "obvious": "none", "likelihood": 0}])
    llm = Scripted([LOOP_REACT, {"asks": []}, first, second, react(), "ok", OK])
    t = flow.run_turn(w, llm, "x")
    assert len(calls) == 2 and t.rolled == 2 and t.ask_rounds == 2
    assert "Is the desk clerk in?' → YES" in llm.seen[3][1]                # it saw the first answer before the second ask
    assert "Does the clerk know the guest?' → YES" in llm.seen[4][1]


def test_asking_again_is_bounded_only_to_stop_a_loop(monkeypatch):
    counting_ask(monkeypatch)
    w = world()
    more = lambda i: react(asks=[{"question": f"Is it number {i}?", "obvious": "none", "likelihood": 0}])
    llm = Scripted([LOOP_REACT, {"asks": []}] + [more(i) for i in range(4)] + [more(99), react(), "ok", OK])
    t = flow.run_turn(w, llm, "x")
    assert t.ask_rounds == 4 and "no more questions this turn" in llm.seen[7][1]


def test_the_play_lessons_are_in_the_prompts_that_need_them():
    w = world()
    t = flow.Turn(w, "x")
    steps = {s["id"]: s for s in flow.load_steps()}
    for sid in ("sort", "wonder", "react", "fight"):
        text = flow.rules_text(steps[sid]["rules"])
        assert "never roll to avoid being the one who said yes" in text and "NEUTRAL" in text, sid
