"""_slotCheck: a date or time the model normalised must be what the passenger's quote says.

Deterministic, no engine and no model (invariant 4: evidence decides acceptance).
"""
from __future__ import annotations

import pytest

from refund.slots import check, read_date, read_time, slot_check_tool

# ---- _slotCheck: a normalised value must be what the passenger's words say ----------

@pytest.mark.parametrize("quote,value", [
    ("7 November", "2026-11-07"), ("on 7.11.", "2026-11-07"), ("07.11.2026", "2026-11-07"),
    ("November 7th", "2026-11-07"), ("am 7. November", "2026-11-07"), ("le 7 novembre", "2026-11-07"),
    ("2026-11-07", "2026-11-07"), ("Saturday", "2026-11-07"),
])
def test_dates_the_quote_states_are_accepted(quote, value):
    assert check("date", value, quote)["ok"] is True


@pytest.mark.parametrize("quote,value", [
    ("8 November", "2026-11-07"),        # the model "corrected" the day: must be refused
    ("yesterday", "2026-11-07"),         # nothing readable: never guessed
    ("7 November 2025", "2026-11-07"),
])
def test_a_date_the_quote_does_not_state_is_refused(quote, value):
    assert check("date", value, quote)["ok"] is False


@pytest.mark.parametrize("quote,value", [
    ("8 o'clock", "08:00"), ("at 8", "08:00"), ("08:11", "08:11"), ("8.11", "08:11"),
    ("um 8 Uhr", "08:00"), ("9 pm", "21:00"), ("8h30", "08:30"),
])
def test_times_the_quote_states_are_accepted(quote, value):
    assert check("time", value, quote)["ok"] is True


@pytest.mark.parametrize("quote,value", [("8 o'clock", "09:00"), ("in the morning", "08:00"), ("8:11", "08:00")])
def test_a_time_the_quote_does_not_state_is_refused(quote, value):
    assert check("time", value, quote)["ok"] is False


def test_other_slots_and_bad_input_are_never_ok():
    assert check("price", "46", "CHF 46")["ok"] is False
    assert check("date", None, "7 November")["ok"] is False
    output, evidence = slot_check_tool({"slot": "date", "value": "2026-11-07", "quote": "7 November"})
    assert output["ok"] is True and "no model" in evidence["mode"]


def test_readers():
    assert read_date("31 February") is None and read_time("25:00") is None
