"""Adapter: the FrameX refund pipeline behind the chat UI's Backend seam.

    REFUND_BACKEND=refund.chat_backend:RefundBackend uv run python src/chat/app.py

The UI passes a plain dict back each turn (and copies it shallowly), so the
dict carries only a conversation id. The live FrameX conversation (a worker
thread blocked on the passenger's next answer) stays here, keyed by that id:
two browser tabs get two ids and never share a conversation.

While asking, state["form"] describes the rules' question for a form widget
({slot, kind, label, options|min}). The UI answers it by setting
state["formAnswer"] = {"slot", "value"} and sending the chosen label as text.
"""
from __future__ import annotations

import threading
import uuid

from chat.backend import FAILED, STATUSES, Step, Turn

FAILED_REPLY = ("Sorry, I could not check your journey right now. This is a technical problem, "
                "not a decision about your refund. Please contact SBB customer service.")

_ACTORS = {"knowledgeBase": "knowledge base", "kb": "knowledge base"}
MAX_CONVERSATIONS = 50


def _cancel(*conversations):
    """Release each distinct conversation, including opaque test substitutes."""
    seen = set()
    for conversation in conversations:
        if conversation is None or id(conversation) in seen:
            continue
        seen.add(id(conversation))
        cancel = getattr(conversation, "cancel", None)
        if cancel is not None:
            cancel()


def _step(raw: dict) -> Step:
    data = {k: raw[k] for k in ("tool", "request", "receipt", "ok") if raw.get(k) not in (None, {}, "")}
    return Step(pattern=raw.get("pattern") or "-",
                actor=_ACTORS.get(raw.get("actor", ""), raw.get("actor") or "host"),
                action=raw.get("summary") or raw.get("tool") or "",
                data=data or None)


class RefundBackend:
    """Loads the knowledge base once; one FrameX conversation per conversation id."""

    def __init__(self, bot=None):
        if bot is None:
            from refund.host import RefundBot
            bot = RefundBot()
        self.bot = bot
        self._conversations: dict[str, object] = {}
        self._lock = threading.Lock()

    def respond(self, message: str, state: dict) -> Turn:
        cid = (state or {}).get("conversation")
        with self._lock:
            conversation = self._conversations.get(cid) if cid else None
        if conversation is None:
            cid = uuid.uuid4().hex
        # A UI form answer to the pending question goes to the rules as a receipt.
        form = (state or {}).get("formAnswer")
        kwargs = {"form": form} if conversation is not None and isinstance(form, dict) else {}
        try:
            out = self.bot.turn(conversation, message, **kwargs)
        except Exception as exc:  # never a verdict from a crash
            with self._lock:
                previous = self._conversations.pop(cid, None)
                _cancel(previous, conversation)
            return Turn(FAILED_REPLY, FAILED, {},
                        [Step("P7 Competence", "host", "pipeline raised an error",
                              f"{type(exc).__name__}: {exc}")])
        status = out.get("status")
        if status not in STATUSES:
            status = FAILED
        done = bool(out.get("done")) or status != "asking"
        returned = out.get("state")
        with self._lock:
            if done:
                previous = self._conversations.pop(cid, None)
                _cancel(previous, conversation, returned)
            else:
                previous = self._conversations.get(cid)
                _cancel(*(old for old in (previous, conversation) if old is not returned))
                self._conversations[cid] = returned
                # Dict insertion order retains the oldest conversation first.
                while len(self._conversations) > MAX_CONVERSATIONS:
                    oldest = next(iter(self._conversations))
                    _cancel(self._conversations.pop(oldest))
        new_state = {} if done else {"conversation": cid}
        if not done and isinstance(out.get("form"), dict):
            new_state["form"] = out["form"]
        reply = out.get("reply") or (FAILED_REPLY if status == FAILED else "")
        return Turn(reply, status, new_state, [_step(s) for s in out.get("steps", [])])
