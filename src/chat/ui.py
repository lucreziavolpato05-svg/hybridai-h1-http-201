"""Pure chat logic, kept free of Gradio so it can be unit-tested.

Auditor rules this module keeps:
- The UI never decides or edits a verdict: the backend's reply is shown as-is
  (no Silent Rule Override).
- A failure is never shown as "no refund": an exception, an unknown status or
  an empty verdict reply becomes FAILED with a hand-on message (invariant 5).
- Every turn's trace is kept, so the workflow view shows what crossed each
  boundary (invariant 2, auditability).
"""
from __future__ import annotations

import json
from datetime import datetime

from .backend import (ASKING, ENTITLED, FAILED, HANDED_ON, NOT_ENTITLED, STATUSES,
                      Backend, Step, Turn)

MAX_MESSAGE_CHARS = 2000

FAILED_REPLY = ("Sorry, I could not check your journey right now. This is a technical problem, "
                "not a decision about your refund. Please contact SBB customer service.")
TOO_LONG_REPLY = (f"Your message is too long (over {MAX_MESSAGE_CHARS} characters). "
                  "Please describe your journey in a few sentences.")

STATUS_LABELS = {
    ASKING: "Waiting for your answer",
    ENTITLED: "Refund due",
    NOT_ENTITLED: "No refund",
    HANDED_ON: "Handed on to SBB customer service",
    FAILED: "Technical problem: handed on to SBB customer service",
}

TRACE_HEADERS = ["turn", "time", "pattern", "actor", "action", "data"]


def new_session() -> dict:
    """Everything the UI keeps between turns."""
    return {"backend_state": {}, "trace_rows": [], "turn": 0, "status": None, "form_dismissed": False}


def _data_text(data) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(data)


def _row(turn: int, step: Step) -> list:
    return [turn, datetime.now().strftime("%H:%M:%S"), step.pattern, step.actor, step.action,
            _data_text(step.data)]


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(status, "") if status else ""


def _checked(turn) -> Turn:
    """Fail closed: anything that is not a well-formed Turn becomes FAILED."""
    if not isinstance(turn, Turn):
        return Turn(FAILED_REPLY, FAILED, {}, [Step("P7 Competence", "host",
                    "backend returned something that is not a Turn", type(turn).__name__)])
    if turn.status not in STATUSES:
        return Turn(FAILED_REPLY, FAILED, turn.state, list(turn.trace) + [Step(
            "P7 Competence", "host", "unknown status from backend: treated as failure", turn.status)])
    if not (turn.reply or "").strip():
        return Turn(FAILED_REPLY, FAILED, turn.state, list(turn.trace) + [Step(
            "P7 Competence", "host", "empty reply from backend: treated as failure", turn.status)])
    return turn


# ---- forms: the backend may describe what it asks for in state["form"] ------------------
# {"slot", "kind": "choice"|"number"|"text"|"date"|"time", "label",
#  "options": [{"value", "label"}] (choice only), "min" (number only)}
# The UI only renders it and passes the answer on; the backend validates every value.
FORM_KINDS = ("choice", "number", "text", "date", "time")
DESCRIBE = "__describe__"
DESCRIBE_LABEL = "None of these / describe it"


def current_form(session: dict | None) -> dict | None:
    """The form the backend asked for in its latest state, or None. A malformed form is
    hidden rather than guessed at: the passenger can always type."""
    if not session or session.get("form_dismissed"):
        return None
    form = (session.get("backend_state") or {}).get("form")
    if not isinstance(form, dict) or form.get("kind") not in FORM_KINDS:
        return None
    if not isinstance(form.get("slot"), str) or not form["slot"]:
        return None
    if form["kind"] == "choice":
        options = form.get("options")
        if not isinstance(options, list) or not options or not all(
                isinstance(o, dict) and "value" in o and isinstance(o.get("label"), str) and o["label"].strip()
                for o in options):
            return None
    if form["kind"] == "number":
        low = form.get("min")
        if low is not None and (isinstance(low, bool) or not isinstance(low, (int, float))):
            return None
    return form


def choice_items(form: dict) -> list[tuple[str, str]]:
    """Radio entries (label, index) for a choice form, plus the free-text escape."""
    return [(o["label"], str(i)) for i, o in enumerate(form["options"])] + [(DESCRIBE_LABEL, DESCRIBE)]


def _number_text(value) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def submit_form(choice, number, history: list, session: dict, backend: Backend, text=None):
    """The passenger answered the form: pass {"slot", "value"} as state["formAnswer"] and the
    option's label (or the number / typed text) as the message. Returns (history, session).
    A number is always passed as a float (JSON number); text/date/time as a string."""
    form = current_form(session)
    if form is None:
        return list(history or []), dict(session or new_session())
    if form["kind"] == "choice":
        if choice in (None, ""):
            return list(history or []), dict(session)
        if choice == DESCRIBE:  # the passenger will type instead; nothing is sent
            return list(history or []), dict(session, form_dismissed=True)
        try:
            option = form["options"][int(choice)]
        except (ValueError, IndexError, TypeError):
            return list(history or []), dict(session)
        answer, message = {"slot": form["slot"], "value": option["value"]}, option["label"]
    elif form["kind"] == "number":
        if number is None or isinstance(number, bool):
            return list(history or []), dict(session)
        try:
            value = float(number)
        except (TypeError, ValueError):
            return list(history or []), dict(session)
        answer, message = {"slot": form["slot"], "value": value}, _number_text(value)
    else:  # text, date, time: a small text field next to the question
        typed = (text or "").strip() if isinstance(text, str) else ""
        if not typed:
            return list(history or []), dict(session)
        answer, message = {"slot": form["slot"], "value": typed}, typed
    return handle_message(message, history, session, backend, form_answer=answer)


def handle_message(message: str, history: list, session: dict, backend: Backend, form_answer: dict | None = None):
    """One chat turn. Returns (history, session) with the passenger's message,
    the reply and the trace rows appended. ``history`` uses Gradio's messages
    format: [{"role": "user"|"assistant", "content": str}, ...].
    A typed message never carries a formAnswer; a form submit does."""
    history = list(history or [])
    session = dict(session or new_session())
    text = (message or "").strip()
    if not text:
        return history, session

    turn_no = session["turn"] + 1
    rows = list(session["trace_rows"])
    history.append({"role": "user", "content": text})

    if len(text) > MAX_MESSAGE_CHARS:
        history.append({"role": "assistant", "content": TOO_LONG_REPLY})
        rows.append(_row(turn_no, Step("P5 Rules steer", "host", "message refused: too long", len(text))))
        session.update(turn=turn_no, trace_rows=rows, status=ASKING)
        return history, session

    state = dict(session["backend_state"])
    state.pop("formAnswer", None)
    if form_answer is not None:
        state["formAnswer"] = dict(form_answer)
        rows.append(_row(turn_no, Step("-", "passenger", "form answer", {"text": text, **form_answer})))
    else:
        rows.append(_row(turn_no, Step("-", "passenger", "message", text)))
    session["form_dismissed"] = False
    try:
        turn = backend.respond(text, state)
    except Exception as exc:  # the backend must never crash the chat or turn into a "no"
        turn = Turn(FAILED_REPLY, FAILED, session["backend_state"],
                    [Step("P7 Competence", "host", "backend raised an error",
                          f"{type(exc).__name__}: {exc}")])
    turn = _checked(turn)

    rows.extend(_row(turn_no, s) for s in turn.trace)
    rows.append(_row(turn_no, Step("-", "host", f"reply shown ({turn.status})", None)))
    history.append({"role": "assistant", "content": turn.reply})
    session.update(turn=turn_no, trace_rows=rows, status=turn.status,
                   backend_state=dict(turn.state or {}),
                   form_dismissed=turn.status == FAILED)  # no stale form after a failure
    return history, session
