"""Unit tests for the chat UI logic (src/chat). No model, no engine needed.

Auditor focus: the UI shows the backend's verdict unchanged, and a failure is
never shown as a refusal (invariants 3 and 5).
"""
from __future__ import annotations

import pytest

from chat import backend as be
from chat.backend import (ASKING, ENTITLED, FAILED, HANDED_ON, NOT_ENTITLED, DemoBackend, Step,
                          Turn, load_backend)
from chat.ui import (FAILED_REPLY, MAX_MESSAGE_CHARS, STATUS_LABELS, TRACE_HEADERS,
                     handle_message, new_session, status_label)


class Fixed:
    """A backend that returns one prepared turn and records what it was given."""

    def __init__(self, turn):
        self.turn, self.calls = turn, []

    def respond(self, message, state):
        self.calls.append((message, state))
        return self.turn


class Raises:
    def respond(self, message, state):
        raise ConnectionError("model endpoint unreachable")


VERDICT = Turn("Your train arrived 72 min late: you get 25 % of the ticket price, CHF 11.50.",
               ENTITLED, {"case": "x"},
               [Step("P1 Sensor", "model", "extracted origin", {"origin": "St. Gallen", "quote": "St. Gallen"}),
                Step("P3 Translator", "model", "phrased verdict", {"decision": "entitled"})])


def send(backend, message="St. Gallen to Zürich HB at 8", history=None, session=None):
    return handle_message(message, history or [], session or new_session(), backend)


# ---- normal turns -------------------------------------------------------------

def test_reply_is_shown_exactly_as_the_backend_wrote_it():
    history, session = send(Fixed(VERDICT))
    assert history[-2] == {"role": "user", "content": "St. Gallen to Zürich HB at 8"}
    assert history[-1] == {"role": "assistant", "content": VERDICT.reply}
    assert session["status"] == ENTITLED


def test_backend_state_is_carried_to_the_next_turn():
    b = Fixed(VERDICT)
    _, session = send(b)
    send(b, "second message", session=session)
    assert b.calls[1][1] == {"case": "x"}


def test_backend_cannot_mutate_the_ui_session_through_state():
    class Mutates:
        def respond(self, message, state):
            state["sneaky"] = True
            return Turn("ok?", ASKING, {}, [])
    session = new_session()
    session["backend_state"] = {"a": 1}
    _, after = send(Mutates(), session=session)
    assert session["backend_state"] == {"a": 1}
    assert after["backend_state"] == {}


def test_trace_rows_show_every_backend_step_with_pattern_and_actor():
    _, session = send(Fixed(VERDICT))
    rows = session["trace_rows"]
    assert all(len(r) == len(TRACE_HEADERS) for r in rows)
    patterns = [r[2] for r in rows]
    assert "P1 Sensor" in patterns and "P3 Translator" in patterns
    assert rows[0][3] == "passenger"


def test_trace_accumulates_over_turns_with_turn_numbers():
    b = Fixed(VERDICT)
    _, s = send(b)
    _, s = send(b, "again", session=s)
    assert {r[0] for r in s["trace_rows"]} == {1, 2}
    assert s["turn"] == 2


def test_empty_message_does_not_call_the_backend():
    b = Fixed(VERDICT)
    history, session = send(b, "   ")
    assert b.calls == [] and history == [] and session["turn"] == 0


def test_too_long_message_is_refused_before_the_backend():
    b = Fixed(VERDICT)
    history, session = send(b, "x" * (MAX_MESSAGE_CHARS + 1))
    assert b.calls == []
    assert "too long" in history[-1]["content"]
    assert session["status"] == ASKING


# ---- failures stay failures (invariant 5) -------------------------------------

@pytest.mark.parametrize("bad", [
    Raises(),
    Fixed(Turn("You get nothing.", "maybe", {}, [])),          # status outside the contract
    Fixed(Turn("   ", NOT_ENTITLED, {}, [])),                  # empty verdict text
    Fixed({"reply": "no refund", "status": NOT_ENTITLED}),     # not a Turn at all
    Fixed(None),
])
def test_any_backend_failure_becomes_failed_never_a_verdict(bad):
    history, session = send(bad)
    assert session["status"] == FAILED
    assert history[-1]["content"] == FAILED_REPLY
    assert "no refund" not in history[-1]["content"].lower()
    assert "customer service" in status_label(FAILED).lower()


def test_failure_is_recorded_in_the_trace_with_its_reason():
    _, session = send(Raises())
    reasons = " ".join(r[5] for r in session["trace_rows"])
    assert "ConnectionError" in reasons and "unreachable" in reasons


def test_failed_turn_keeps_the_previous_backend_state():
    session = new_session()
    session["backend_state"] = {"origin": "sp_8506302"}
    _, after = send(Raises(), session=session)
    assert after["backend_state"] == {"origin": "sp_8506302"}


# ---- labels -------------------------------------------------------------------

def test_every_status_has_a_label_and_handed_on_names_customer_service():
    assert set(STATUS_LABELS) == set(be.STATUSES)
    assert "customer service" in status_label(HANDED_ON).lower()
    assert status_label(None) == "" and status_label("bogus") == ""


# ---- demo backend and loading -------------------------------------------------

def test_demo_backend_never_gives_a_verdict():
    d, state = DemoBackend(), {}
    for msg in ["St. Gallen to Zürich HB at 8", "CHF 40", "anything"]:
        turn = d.respond(msg, state)
        state = turn.state
        assert turn.reply.startswith("[DEMO]")
        assert turn.status not in (ENTITLED, NOT_ENTITLED)


def test_demo_backend_on_request(monkeypatch):
    monkeypatch.setenv("REFUND_BACKEND", "demo")
    assert isinstance(load_backend(), DemoBackend)


def test_default_backend_is_the_real_pipeline(monkeypatch):
    assert be.DEFAULT_BACKEND == "refund.chat_backend:RefundBackend"
    monkeypatch.delenv("REFUND_BACKEND", raising=False)
    monkeypatch.setattr(be, "DEFAULT_BACKEND", "chat.backend:DemoBackend")  # don't load the KB in a unit test
    assert isinstance(load_backend(), DemoBackend)


def test_load_backend_from_spec_and_factory():
    assert isinstance(load_backend("chat.backend:DemoBackend"), DemoBackend)


def test_load_backend_rejects_non_backend():
    with pytest.raises(TypeError):
        load_backend("chat.backend:STATUSES")


def test_gradio_app_builds():
    gr = pytest.importorskip("gradio")
    from chat.app import build_demo
    assert isinstance(build_demo(DemoBackend()), gr.Blocks)


def test_gradio_app_launches_with_theme_css_and_js():
    """launch() is where theme, CSS and JS are applied in Gradio 6: building alone missed a crash."""
    pytest.importorskip("gradio")
    requests = pytest.importorskip("requests")
    from chat.app import build_demo, launch
    demo = build_demo(DemoBackend())
    try:
        launch(demo, prevent_thread_lock=True, server_port=7899, quiet=True)
        page = requests.get("http://127.0.0.1:7899/", timeout=30)
        assert page.status_code == 200
    finally:
        demo.close()
