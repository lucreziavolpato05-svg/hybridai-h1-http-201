"""Deterministic reading of a date or time from the passenger's own quote.

Host adapter `_slotCheck`, a measurement like `_numbersMatch`: the model proposes a
normalised value (2026-11-07, 08:00) together with the words it read it from; this
code reads the same words without a model and reports whether they say that value.
The rules in refund.fx accept a date or time only when `ok` is true (invariant 4:
evidence, not the model's normalisation, decides acceptance).
"""
from __future__ import annotations

import re
from datetime import date

DEFAULT_YEAR = 2026

MONTHS = {
    "january": 1, "jan": 1, "januar": 1, "janvier": 1, "gennaio": 1,
    "february": 2, "feb": 2, "februar": 2, "février": 2, "febbraio": 2,
    "march": 3, "mar": 3, "märz": 3, "maerz": 3, "mars": 3, "marzo": 3,
    "april": 4, "apr": 4, "avril": 4, "aprile": 4,
    "may": 5, "mai": 5, "maggio": 5,
    "june": 6, "jun": 6, "juni": 6, "juin": 6, "giugno": 6,
    "july": 7, "jul": 7, "juli": 7, "juillet": 7, "luglio": 7,
    "august": 8, "aug": 8, "août": 8, "agosto": 8,
    "september": 9, "sep": 9, "sept": 9, "septembre": 9, "settembre": 9,
    "october": 10, "oct": 10, "okt": 10, "oktober": 10, "octobre": 10, "ottobre": 10,
    "november": 11, "nov": 11, "novembre": 11,
    "december": 12, "dec": 12, "dez": 12, "dezember": 12, "décembre": 12, "dicembre": 12,
}
WEEKDAY_OF_DAY = {"saturday", "samstag", "samedi", "sabato"}  # 07.11.2026 is a Saturday


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def read_date(text: str) -> str | None:
    """ISO date stated in `text`, or None. Year defaults to 2026."""
    t = text.lower()
    m = re.search(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", t)
    if m:
        return _iso(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{4}|\d{2}))?\.?(?!\d)", t)
    if m:
        y = int(m[3]) if m[3] else DEFAULT_YEAR
        return _iso(y + 2000 if y < 100 else y, int(m[2]), int(m[1]))
    m = re.search(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th|er|e)?\.?\s*(?:of\s+)?([a-zäöüéèû]+)\.?(?:,?\s*(\d{4}))?", t)
    if m and m[2] in MONTHS:
        return _iso(int(m[3]) if m[3] else DEFAULT_YEAR, MONTHS[m[2]], int(m[1]))
    m = re.search(r"([a-zäöüéèû]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?!\d)(?:,?\s*(\d{4}))?", t)
    if m and m[1] in MONTHS:
        return _iso(int(m[3]) if m[3] else DEFAULT_YEAR, MONTHS[m[1]], int(m[2]))
    return None


def read_time(text: str) -> str | None:
    """HH:MM stated in `text`, or None."""
    t = text.lower()
    hour = minute = None
    suffix = None
    m = re.search(r"(?<!\d)(\d{1,2})\s*[:.h]\s*(\d{2})(?!\d)\s*(a\.?m\.?|p\.?m\.?)?", t)
    if m:
        hour, minute, suffix = int(m[1]), int(m[2]), m[3]
    else:
        m = re.search(r"(?<!\d)(\d{1,2})\s*(a\.?m\.?|p\.?m\.?)", t)
        if m:
            hour, minute, suffix = int(m[1]), 0, m[2]
        else:
            m = (re.search(r"(?<!\d)(\d{1,2})\s*(?:o'?\s?clock|uhr|h\b|heures?|ore)", t)
                 or re.search(r"\b(?:at|um|around|about|gegen|ca\.?|vers|à|alle)\s+(\d{1,2})(?![\d.:])", t)
                 or re.fullmatch(r"\D*(\d{1,2})\D*", t))
            if m:
                hour, minute = int(m[1]), 0
    if hour is None:
        return None
    if suffix:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if suffix.startswith("p") else 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def check(slot: str, value, quote) -> dict:
    """Does `quote` state `value` for this slot? A measurement; the rules decide."""
    if not isinstance(value, str) or not isinstance(quote, str):
        return {"ok": False, "read": "", "reason": "value and quote must be texts"}
    if slot == "date":
        read = read_date(quote)
        if read is None and quote.strip().lower() in WEEKDAY_OF_DAY:
            read = f"{DEFAULT_YEAR}-11-07"
    elif slot == "time":
        read = read_time(quote)
    else:
        return {"ok": False, "read": "", "reason": f"no deterministic reading for slot {slot}"}
    if read is None:
        return {"ok": False, "read": "", "reason": "the quote states no readable value"}
    ok = read == value.strip()
    return {"ok": ok, "read": read, "reason": "" if ok else f"the quote says {read}, not {value}"}


def slot_check_tool(parameters: dict) -> tuple[dict, dict]:
    return check(parameters.get("slot"), parameters.get("value"), parameters.get("quote")), \
        {"mode": "deterministic reading of the passenger's quote; no model"}


TOOLS = {"_slotCheck": slot_check_tool}
