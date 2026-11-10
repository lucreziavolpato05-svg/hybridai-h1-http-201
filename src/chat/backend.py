"""The seam between the chat UI and the refund pipeline.

The UI only ever calls ``Backend.respond(message, state) -> Turn``. The real
pipeline (LLM + FrameX rules) is built separately; to plug it in, either make
it return a ``Turn`` or write a small adapter in ``load_backend``. Nothing in
the UI decides a refund: it shows what the backend returns, unchanged.

Select the backend with the environment variable REFUND_BACKEND="module:attr",
where attr is a Backend instance or a zero-argument factory. Unset, the real FrameX
pipeline runs (refund.chat_backend:RefundBackend); REFUND_BACKEND=demo runs the
clearly labelled DemoBackend, for UI work without the engine or a model.
"""
from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

# What a turn can end in. Anything else is treated as "failed" by the UI.
ASKING = "asking"            # the rules need more information from the passenger
ENTITLED = "entitled"        # refund due (also when under the CHF 5 minimum payout)
NOT_ENTITLED = "notEntitled"  # delay under 60 min
HANDED_ON = "handedOn"       # the rules cannot settle it: SBB customer service
FAILED = "failed"            # a technical failure: never a verdict
STATUSES = (ASKING, ENTITLED, NOT_ENTITLED, HANDED_ON, FAILED)


@dataclass
class Step:
    """One entry of the workflow view: who did what, under which pattern."""
    pattern: str   # e.g. "P1 Sensor", "P5 Rules steer", "P3 Translator", "P7 Competence"
    actor: str     # "passenger" | "model" | "rules" | "knowledge base" | "host"
    action: str    # short description, e.g. "extracted origin with quote"
    data: Any = None  # what crossed the boundary (dict, str, ...)


@dataclass
class Turn:
    reply: str
    status: str
    state: dict = field(default_factory=dict)
    trace: list[Step] = field(default_factory=list)


class Backend(Protocol):
    def respond(self, message: str, state: dict) -> Turn: ...


class DemoBackend:
    """Scripted stand-in so the UI runs before the pipeline exists.

    It makes no model call, reads no knowledge base and gives NO real verdict:
    every reply is prefixed with [DEMO].
    """

    def respond(self, message: str, state: dict) -> Turn:
        n = state.get("turns", 0) + 1
        new_state = dict(state, turns=n)
        trace = [Step("P1 Sensor", "model", "demo: would extract origin, destination, date, time, price",
                      {"message": message})]
        if n == 1:
            trace.append(Step("P5 Rules steer", "rules", "demo: ticket price missing -> ask", {"missing": ["ticketPrice"]}))
            return Turn("[DEMO] What did you pay for your ticket (CHF)?", ASKING, new_state, trace)
        trace.append(Step("P7 Competence", "rules", "demo: no real pipeline -> hand on", None))
        return Turn("[DEMO] No refund pipeline is connected yet. In the real system this case would be "
                    "decided by the rules or handed on to SBB customer service.", HANDED_ON, new_state, trace)


DEFAULT_BACKEND = "refund.chat_backend:RefundBackend"   # the FrameX refund pipeline


def load_backend(spec: str | None = None) -> Backend:
    """REFUND_BACKEND="module:attr" selects the backend; unset means the real pipeline,
    "demo" the scripted DemoBackend (no model, no knowledge base, no verdicts)."""
    spec = spec if spec is not None else os.environ.get("REFUND_BACKEND", "")
    spec = spec.strip() or DEFAULT_BACKEND
    if spec.lower() == "demo":
        return DemoBackend()
    module_name, _, attr = spec.partition(":")
    obj = getattr(importlib.import_module(module_name), attr or "backend")
    if isinstance(obj, type) or (callable(obj) and not hasattr(obj, "respond")):
        obj = obj()
    if not hasattr(obj, "respond"):
        raise TypeError(f"{spec} is not a Backend (needs .respond(message, state) -> Turn)")
    return obj
