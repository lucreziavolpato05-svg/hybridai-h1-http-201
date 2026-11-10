import pytest

from chat.backend import Step, Turn
from refund.chat_backend import RefundBackend


class CancellableConversation:
    def __init__(self):
        self.cancel_calls = 0

    def cancel(self):
        self.cancel_calls += 1


class FakeBot:
    def __init__(self, *results):
        self.results = iter(results)
        self.calls = []

    def turn(self, state, text):
        self.calls.append((state, text))
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def output(state=None, status="asking", done=False, steps=None):
    return {"reply": "A reply", "status": status, "steps": steps or [],
            "done": done, "state": state}


def test_first_turn_and_shallow_copied_state_preserve_opaque_conversation():
    conversation = object()
    bot = FakeBot(output(conversation), output(conversation))
    backend = RefundBackend(bot)

    first = backend.respond("hello", {})
    assert isinstance(first, Turn)
    assert first.status == "asking"
    assert isinstance(first.state["conversation"], str)
    assert first.state["conversation"]
    assert bot.calls[0] == (None, "hello")

    second = backend.respond("answer", dict(first.state))
    assert bot.calls[1][0] is conversation
    assert bot.calls[1][1] == "answer"
    assert second.state == first.state


def test_two_interleaved_conversation_ids_never_mix():
    a, b = object(), object()
    bot = FakeBot(output(a), output(b), output(a), output(b))
    backend = RefundBackend(bot)
    first = backend.respond("start a", {})
    second = backend.respond("start b", {})
    assert first.state["conversation"] != second.state["conversation"]
    backend.respond("continue a", dict(first.state))
    backend.respond("continue b", dict(second.state))
    assert bot.calls[0][0] is None
    assert bot.calls[1][0] is None
    assert bot.calls[2][0] is a
    assert bot.calls[3][0] is b


@pytest.mark.parametrize("status,done", [
    ("entitled", False), ("notEntitled", False), ("handedOn", False),
    ("failed", False), ("asking", True),
])
def test_finished_turn_clears_state_and_forgets_conversation(status, done):
    conversation = object()
    bot = FakeBot(output(conversation), output(conversation, status, done),
                  output(object()))
    backend = RefundBackend(bot)
    first = backend.respond("start", {})
    finished = backend.respond("finish", first.state)
    assert finished.status == status
    assert finished.state == {}
    assert bot.calls[1][0] is conversation
    restarted = backend.respond("reuse stale id", dict(first.state))
    assert bot.calls[2][0] is None
    assert restarted.state["conversation"] != first.state["conversation"]


def test_unknown_status_becomes_failed():
    backend = RefundBackend(FakeBot(output(object(), status="garbage")))
    turn = backend.respond("hello", {})
    assert turn.status == "failed"
    assert turn.state == {}


def test_bot_exception_returns_failed_reply_and_forgets_conversation():
    conversation = CancellableConversation()
    bot = FakeBot(output(conversation), RuntimeError("bot broke"), output(object()))
    backend = RefundBackend(bot)
    first = backend.respond("start", {})
    turn = backend.respond("crash", first.state)
    assert isinstance(turn, Turn)
    assert turn.status == "failed"
    assert turn.reply.strip()
    assert turn.state == {}
    assert conversation.cancel_calls == 1
    backend.respond("retry stale id", first.state)
    assert bot.calls[2][0] is None


def test_replaced_conversation_is_cancelled():
    old, new = CancellableConversation(), CancellableConversation()
    backend = RefundBackend(FakeBot(output(old), output(new)))
    first = backend.respond("start", {})
    second = backend.respond("replace", first.state)
    assert second.state == first.state
    assert old.cancel_calls == 1 and new.cancel_calls == 0
    assert backend._conversations[first.state["conversation"]] is new


@pytest.mark.parametrize("status", ["entitled", "notEntitled", "handedOn", "failed", "invalid"])
def test_forgetting_conversations_cancels_both_old_and_returned_states(status):
    old, returned = CancellableConversation(), CancellableConversation()
    backend = RefundBackend(FakeBot(output(old), output(returned, status=status)))
    first = backend.respond("start", {})
    finished = backend.respond("finish", first.state)
    assert finished.state == {} and not backend._conversations
    assert old.cancel_calls == 1 and returned.cancel_calls == 1


def test_cap_cancels_oldest_conversation_and_stale_id_starts_fresh():
    conversations = [CancellableConversation() for _ in range(52)]
    bot = FakeBot(*(output(conversation) for conversation in conversations))
    backend = RefundBackend(bot)
    first = backend.respond("start oldest", {})
    for _ in range(50):
        backend.respond("start another tab", {})
    assert len(backend._conversations) == 50
    assert conversations[0].cancel_calls == 1
    assert all(conversation.cancel_calls == 0 for conversation in conversations[1:])
    assert first.state["conversation"] not in backend._conversations
    fresh = backend.respond("reuse evicted id", first.state)
    assert bot.calls[-1][0] is None
    assert fresh.state != first.state
    assert len(backend._conversations) == 50
    assert conversations[1].cancel_calls == 1


def test_step_maps_actor_summary_and_tool_payload():
    raw = {"actor": "knowledgeBase", "tool": "_measure",
           "pattern": "P7 Division by competence", "summary": "Checked competence",
           "request": {"journey": "Bern"}, "receipt": {"eligible": True}, "ok": True}
    turn = RefundBackend(FakeBot(output(object(), steps=[raw]))).respond("check", {})
    assert len(turn.trace) == 1
    step = turn.trace[0]
    assert isinstance(step, Step)
    assert step.actor == "knowledge base"
    assert step.pattern == raw["pattern"]
    assert step.action == raw["summary"]
    assert step.data == {key: raw[key] for key in ("tool", "request", "receipt", "ok")}
