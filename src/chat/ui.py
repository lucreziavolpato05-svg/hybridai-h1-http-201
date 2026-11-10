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
    return {"backend_state": {}, "trace_rows": [], "turn": 0, "status": None}


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


def handle_message(message: str, history: list, session: dict, backend: Backend):
    """One chat turn. Returns (history, session) with the passenger's message,
    the reply and the trace rows appended. ``history`` uses Gradio's messages
    format: [{"role": "user"|"assistant", "content": str}, ...]."""
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

    rows.append(_row(turn_no, Step("-", "passenger", "message", text)))
    try:
        turn = backend.respond(text, dict(session["backend_state"]))
    except Exception as exc:  # the backend must never crash the chat or turn into a "no"
        turn = Turn(FAILED_REPLY, FAILED, session["backend_state"],
                    [Step("P7 Competence", "host", "backend raised an error",
                          f"{type(exc).__name__}: {exc}")])
    turn = _checked(turn)

    rows.extend(_row(turn_no, s) for s in turn.trace)
    rows.append(_row(turn_no, Step("-", "host", f"reply shown ({turn.status})", None)))
    history.append({"role": "assistant", "content": turn.reply})
    session.update(turn=turn_no, trace_rows=rows, status=turn.status,
                   backend_state=dict(turn.state or {}))
    return history, session
