"""Turn normalized platforms into F-logic source text for FrameX."""

from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Iterable

from .normalizer import Platform


def literal(value: str | float | bool) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if not math.isfinite(value):
        raise ValueError("FrameX numbers must be finite")
    # FrameX documents decimal literals; do not rely on exponent syntax.
    return format(Decimal(str(value)), "f")


def property_fact(subject: str, name: str, value: str | float | bool) -> str:
    return f"{subject}[{name} -> {literal(value)}]."


def emit_record(platform: Platform) -> str:
    subject = platform.identifier
    facts = [f"{subject}:Platform.", property_fact(subject, "sourceDataset", "perron")]
    properties = (
        ("sourceId", platform.fid), ("number", platform.platform_number),
        ("platformType", platform.platform_type),
        ("structuralLengthM", platform.structural_length_m),
        ("line", platform.line), ("lineKm", platform.line_km),
        ("grossAreaM2", platform.gross_area_m2), ("netAreaM2", platform.net_area_m2),
        ("railFreeAccess", platform.rail_free_access), ("region", platform.region),
        ("latitude", platform.latitude), ("longitude", platform.longitude),
    )
    for name, value in properties:
        if value is not None:
            facts.append(property_fact(subject, name, value))
    station = platform.station_identifier
    if station is not None:
        facts.extend([f"{station}:Station.", f"{subject}[station -> {station}]."])
    # Keep stop details even when neither station identifier is available.
    for name, value in (
        ("name" if station else "stationName", platform.station_name),
        ("abbreviation", platform.station_abbreviation),
        ("uic", platform.station_uic), ("didokCode", platform.didok_code),
        ("lod", platform.station_lod),
    ):
        if value is not None:
            facts.append(property_fact(station or subject, name, value))
    return "\n".join(facts) + "\n"


def emit_records(platforms: Iterable[Platform]) -> str:
    """Emit facts only, leaving the caller's world assumption and rules intact."""
    return "".join(emit_record(platform) for platform in platforms)
