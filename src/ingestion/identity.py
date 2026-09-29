"""Shared station identity only; dataset field semantics stay in each adapter."""

import re


def uic_code(value: object, field: str) -> str:
    """Accept a full seven-digit UIC/BPUIC, never guess from a short DiDok ID."""
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{7}", value.strip()):
        raise ValueError(f"{field} must be a full seven-digit UIC/BPUIC: {value!r}")
    return value.strip()


def station_identifier(uic: str) -> str:
    return f"station_{uic_code(uic, 'uic')}"
