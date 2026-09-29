"""Clean the SBB perron schema into typed platform records."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


def text(value: object) -> str | None:
    """Collapse whitespace and treat missing or blank values as unknown."""
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def number(value: object, field: str, *, minimum: float | None = None,
           maximum: float | None = None) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{field} must be a number")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a number: {value!r}") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum) or (maximum is not None and result > maximum):
        raise ValueError(f"{field} is outside its valid range: {value!r}")
    return result


def code(value: object, field: str) -> str | None:
    """Preserve numeric identifiers as strings, including any leading zeros."""
    value = text(value)
    if value is not None and (not value.isascii() or not value.isdecimal()):
        raise ValueError(f"{field} must contain digits: {value!r}")
    return value


def rail_free_access(value: object) -> bool | None:
    cleaned = text(value)
    if cleaned is None:
        return None
    if cleaned.casefold() in {"ja", "yes", "true", "1"}:
        return True
    if cleaned.casefold() in {"nein", "no", "false", "0"}:
        return False
    raise ValueError(f"Unknown z_schienenfrei value: {value!r}")


@dataclass(frozen=True)
class Platform:
    fid: str
    station_name: str | None
    station_abbreviation: str | None
    station_uic: str | None
    didok_code: str | None
    platform_number: str | None
    platform_type: str | None
    structural_length_m: float | None
    line: str | None
    line_km: float | None
    gross_area_m2: float | None
    net_area_m2: float | None
    rail_free_access: bool | None
    region: str | None
    latitude: float | None
    longitude: float | None
    station_lod: str | None

    @property
    def identifier(self) -> str:
        return f"platform_{self.fid}"

    @property
    def station_identifier(self) -> str | None:
        # Prefer the full UIC; keep short DiDok codes in a separate ID namespace.
        if self.station_uic is not None:
            return f"station_{self.station_uic}"
        if self.didok_code is not None:
            return f"station_didok_{self.didok_code}"
        return None


def normalize_record(record: dict) -> Platform:
    fid = code(record.get("fid"), "fid")
    if fid is None:
        raise ValueError("Platform is missing its installation identifier (fid)")
    point = record.get("geopos") or {}
    if not isinstance(point, dict):
        raise ValueError("geopos must be an object")
    return Platform(
        fid=fid,
        station_name=text(record.get("bps_name")),
        station_abbreviation=text(record.get("bps")),
        station_uic=code(record.get("bpuic"), "bpuic"),
        didok_code=code(record.get("dst_id"), "dst_id"),
        platform_number=text(record.get("p_nr")),
        platform_type=text(record.get("perrontyp")),
        structural_length_m=number(record.get("p_lange"), "p_lange", minimum=0),
        line=code(record.get("linie"), "linie"),
        line_km=number(record.get("km"), "km"),
        gross_area_m2=number(record.get("perronflach_brutto_m2"), "perronflach_brutto_m2", minimum=0),
        net_area_m2=number(record.get("perronflach_netto_m2"), "perronflach_netto_m2", minimum=0),
        rail_free_access=rail_free_access(record.get("z_schienenfrei")),
        region=text(record.get("dok_pfm")),
        latitude=number(point.get("lat"), "geopos.lat", minimum=-90, maximum=90),
        longitude=number(point.get("lon"), "geopos.lon", minimum=-180, maximum=180),
        station_lod=text(record.get("lod")),
    )


def normalize_records(records: Iterable[dict]) -> list[Platform]:
    """Deduplicate identical installations; reject conflicting or invalid rows."""
    platforms: dict[str, Platform] = {}
    for index, record in enumerate(records):
        try:
            platform = normalize_record(record)
            previous = platforms.get(platform.identifier)
            if previous is not None and previous != platform:
                raise ValueError(f"Conflicting records for {platform.identifier}")
            platforms[platform.identifier] = platform
        except ValueError as exc:
            raise ValueError(f"Record {index} (fid={record.get('fid')!r}): {exc}") from exc
    return list(platforms.values())
