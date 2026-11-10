"""The backend's form (state["form"]): the UI renders it and passes answers on; it decides nothing."""
from __future__ import annotations

import pytest

from chat.backend import ASKING, FAILED, ENTITLED, Turn
from chat.ui import (DESCRIBE, DESCRIBE_LABEL, choice_items, current_form, handle_message, new_session,
                     submit_form)

TRAINS = {"slot": "train", "kind": "choice", "label": "Which train did you take?",
          "options": [{"value": "ev_1", "label": "07:48 (arrives 08:52)"},
                      {"value": "ev_2", "label": "08:11 (arrives 09:13)"}]}
PRICE = {"slot": "ticket_price", "kind": "number", "label": "What did your ticket cost (CHF)?", "min": 0}


class Scripted:
    """Returns the scripted turns in order and records (message, state) of every call."""

    def __init__(self, *turns):
        self.turns, self.calls = list(turns), []

    def respond(self, message, state):
        self.calls.append((message, state))
        return self.turns.pop(0)


def asking(form, **extra):
    return Turn("Question?", ASKING, {"form": form, "case": "c1", **extra}, [])


def session_with(form):
    s = new_session()
    s["backend_state"] = {"form": form, "case": "c1"}
    return s


# ---- reading the form ---------------------------------------------------------------

def test_no_form_means_nothing_to_render():
    assert current_form(new_session()) is None
    assert current_form(session_with(None)) is None


@pytest.mark.parametrize("bad", [
    {"slot": "x", "kind": "slider"},                                   # unknown kind
    {"kind": "number"},                                                # no slot
    {"slot": "train", "kind": "choice", "options": []},                # choice without options
    {"slot": "train", "kind": "choice", "options": [{"label": "a"}]},  # option without value
    {"slot": "train", "kind": "choice", "options": [{"value": 1, "label": " "}]},
    {"slot": "p", "kind": "number", "min": "0"},                       # min not a number
    "not a dict",
])
def test_a_malformed_form_is_hidden_not_guessed(bad):
    assert current_form(session_with(bad)) is None


def test_choice_gets_the_describe_option_last():
    items = choice_items(TRAINS)
    assert items[:2] == [("07:48 (arrives 08:52)", "0"), ("08:11 (arrives 09:13)", "1")]
    assert items[-1] == (DESCRIBE_LABEL, DESCRIBE)


# ---- answering the form -------------------------------------------------------------

def test_choice_sends_the_option_label_and_the_form_answer():
    b = Scripted(Turn("Done.", ENTITLED, {}, []))
    history, s = submit_form("1", None, [], session_with(TRAINS), b)
    message, state = b.calls[0]
    assert message == "08:11 (arrives 09:13)"
    assert state["formAnswer"] == {"slot": "train", "value": "ev_2"}
    assert state["case"] == "c1", "the rest of the backend state is passed on unchanged"
    assert history[-2]["content"] == "08:11 (arrives 09:13)"


@pytest.mark.parametrize("given,text,value", [(23, "23", 23), (23.0, "23", 23), (19.9, "19.9", 19.9)])
def test_number_sends_the_number_as_text(given, text, value):
    b = Scripted(Turn("Thanks.", ASKING, {}, []))
    submit_form(None, given, [], session_with(PRICE), b)
    assert b.calls[0] == (text, {"form": PRICE, "case": "c1", "formAnswer": {"slot": "ticket_price", "value": value}})


def test_the_ui_does_not_check_the_minimum_the_backend_does():
    b = Scripted(Turn("A price must be above 0. What did it cost?", ASKING, {"form": PRICE}, []))
    submit_form(None, -5, [], session_with(PRICE), b)
    assert b.calls[0][1]["formAnswer"]["value"] == -5


def test_describe_it_sends_nothing_and_hides_the_form():
    b = Scripted()
    history, s = submit_form(DESCRIBE, None, [], session_with(TRAINS), b)
    assert b.calls == [] and history == []
    assert current_form(s) is None


def test_typing_after_describe_sends_a_plain_message_and_the_next_form_shows_again():
    b = Scripted(asking(PRICE))
    _, s = submit_form(DESCRIBE, None, [], session_with(TRAINS), b)
    _, s = handle_message("the one a bit after 8", [], s, b)
    assert "formAnswer" not in b.calls[0][1]
    assert current_form(s) == PRICE


def test_a_typed_message_never_carries_a_form_answer():
    s = session_with(TRAINS)
    s["backend_state"]["formAnswer"] = {"slot": "train", "value": "ev_1"}  # stale, from an earlier submit
    b = Scripted(Turn("ok", ASKING, {}, []))
    handle_message("I took the 811 one", [], s, b)
    assert "formAnswer" not in b.calls[0][1]


@pytest.mark.parametrize("choice", [None, "", "7", "x"])
def test_an_empty_or_unknown_choice_sends_nothing(choice):
    b = Scripted()
    submit_form(choice, None, [], session_with(TRAINS), b)
    assert b.calls == []


def test_text_forms_have_no_widget_answer():
    b = Scripted()
    form = {"slot": "destination", "kind": "text", "label": "Where were you going?"}
    submit_form(None, 5, [], session_with(form), b)
    assert b.calls == []
    assert current_form(session_with(form)) == form


# ---- the form follows the backend's latest state ------------------------------------

def test_form_disappears_when_the_backend_stops_asking():
    b = Scripted(Turn("Your delay was 70 min.", ENTITLED, {"done": True}, []))
    _, s = submit_form("0", None, [], session_with(TRAINS), b)
    assert current_form(s) is None


def test_a_new_form_replaces_the_old_one():
    b = Scripted(asking(PRICE))
    _, s = submit_form("0", None, [], session_with(TRAINS), b)
    assert current_form(s) == PRICE


def test_no_stale_form_after_a_failure():
    class Raises:
        def respond(self, message, state):
            raise TimeoutError("model")
    _, s = submit_form("0", None, [], session_with(TRAINS), Raises())
    assert s["status"] == FAILED and current_form(s) is None


def test_form_answer_is_recorded_in_the_trace():
    b = Scripted(Turn("ok", ASKING, {}, []))
    _, s = submit_form("1", None, [], session_with(TRAINS), b)
    row = next(r for r in s["trace_rows"] if r[4] == "form answer")
    assert '"value": "ev_2"' in row[5] and row[3] == "passenger"
