"""Adapter: the FrameX refund pipeline behind the chat UI's Backend seam.

    REFUND_BACKEND=refund.chat_backend:RefundBackend uv run python src/chat/app.py

The UI passes a plain dict back each turn (and copies it shallowly), so the
dict carries only a conversation id. The live FrameX conversation (a worker
thread blocked on the passenger's next answer) stays here, keyed by that id:
two browser tabs get two ids and never share a conversation.
"""
from __future__ import annotations

import threading
import uuid

from chat.backend import FAILED, STATUSES, Step, Turn

FAILED_REPLY = ("Sorry, I could not check your journey right now. This is a technical problem, "
                "not a decision about your refund. Please contact SBB customer service.")

_ACTORS = {"knowledgeBase": "knowledge base", "kb": "knowledge base"}


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
        try:
            out = self.bot.turn(conversation, message)
        except Exception as exc:  # never a verdict from a crash
            with self._lock:
                self._conversations.pop(cid, None)
            return Turn(FAILED_REPLY, FAILED, {},
                        [Step("P7 Competence", "host", "pipeline raised an error",
                              f"{type(exc).__name__}: {exc}")])
        status = out.get("status")
        if status not in STATUSES:
            status = FAILED
        done = bool(out.get("done")) or status != "asking"
        with self._lock:
            if done:
                self._conversations.pop(cid, None)
            else:
                self._conversations[cid] = out.get("state")
        new_state = {} if done else {"conversation": cid}
        reply = out.get("reply") or (FAILED_REPLY if status == FAILED else "")
        return Turn(reply, status, new_state, [_step(s) for s in out.get("steps", [])])
