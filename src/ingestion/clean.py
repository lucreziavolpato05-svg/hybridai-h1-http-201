"""Cleaning helpers for inconsistent SBB record fields."""

from __future__ import annotations

import json


PASSENGER_RAIL_MODES = {"TRAIN", "RACK_RAILWAY"}


def text(value) -> str | None:
    if value is None:
        return None
    value = " ".join(str(value).split())
    return value or None


def passenger_rail(record: dict) -> bool:
    """Keep stops that include a passenger rail mode, excluding bus-only stops."""
    modes = {part for part in (text(record.get("meansoftransport")) or "").split("|")}
    return bool(modes & PASSENGER_RAIL_MODES)


def parse_vias(value: str | None) -> list[dict]:
    """Parse SBB's semicolon-delimited JSON objects, ignoring malformed pieces."""
    vias = []
    for raw_part in (value or "").split(";"):
        try:
            item = json.loads(raw_part)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and text(item.get("station_name")):
            vias.append(item)
    return vias