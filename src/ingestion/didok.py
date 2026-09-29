"""Typed Swiss passenger-rail service points from SBB's DiDok dataset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .emiter import property_fact
from .identity import station_identifier, uic_code

DATASET_ID = "dienststellen-gemass-opentransportdataswiss"
ORDER_BY = "number"
WHERE = ('isocountrycode = "CH" AND stoppoint = "true" AND '
         '(meansoftransport like "%TRAIN%" OR meansoftransport like "%RACK_RAILWAY%")')
CANTONS = frozenset("AG AI AR BE BL BS FR GE GL GR JU LU NE NW OW SG SH SO SZ TG TI UR VD VS ZG ZH".split())
RAIL_MODES = {"TRAIN", "RACK_RAILWAY"}
MODE_IDS = {name: f"mode_{name.lower()}" for name in (
    "TRAIN", "RACK_RAILWAY", "TRAM", "BUS", "BOAT", "CABLE_CAR", "CHAIRLIFT", "CABLE_RAILWAY",
)}


def _text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    return " ".join(value.split()) or None


def _flag(value: object, field: str) -> bool | None:
    if value is None or value == "":
        return None
    if type(value) is bool:
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ValueError(f"{field} must be true or false: {value!r}")


def _date(value: object, field: str) -> date | None:
    text = _text(value, field)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date: {value!r}") from exc


@dataclass(frozen=True)
class ServicePoint:
    uic: str
    designation: str | None
    canton: str | None
    modes: tuple[str, ...]

    @property
    def identifier(self) -> str:
        return station_identifier(self.uic)


def normalize_record(record: dict, *, as_of: date | None = None) -> ServicePoint | None:
    """Keep Swiss rail stops valid on as_of; do not guess absent scope evidence."""
    as_of = as_of or date.today()
    country = _text(record.get("isocountrycode"), "isocountrycode")
    if country is None or country.upper() != "CH":
        return None
    if _flag(record.get("stoppoint"), "stoppoint") is not True:
        return None
    mode_text = _text(record.get("meansoftransport"), "meansoftransport")
    modes = {part.strip().upper() for part in (mode_text or "").split("|") if part.strip()}
    if not modes & RAIL_MODES:
        return None
    if modes - MODE_IDS.keys():
        raise ValueError(f"Unsupported transport modes: {sorted(modes - MODE_IDS.keys())}")
    valid_from = _date(record.get("validfrom"), "validfrom")
    valid_to = _date(record.get("validto"), "validto")
    if valid_from and valid_to and valid_from > valid_to:
        raise ValueError("validfrom must not be after validto")
    if (valid_from and as_of < valid_from) or (valid_to and as_of > valid_to):
        return None
    canton = _text(record.get("cantonabbreviation"), "cantonabbreviation")
    if canton is not None:
        canton = canton.upper()
        if canton not in CANTONS:
            raise ValueError(f"Unknown Swiss canton abbreviation: {canton!r}")
    return ServicePoint(
        uic=uic_code(record.get("number"), "number"),
        designation=_text(record.get("designationofficial"), "designationofficial"),
        canton=canton, modes=tuple(sorted(modes)),
    )


def normalize_records(records: Iterable[dict], *, as_of: date | None = None) -> list[ServicePoint]:
    as_of = as_of or date.today()
    points: dict[str, ServicePoint] = {}
    for index, record in enumerate(records):
        try:
            point = normalize_record(record, as_of=as_of)
            if point is None:
                continue
            previous = points.get(point.identifier)
            if previous is not None and previous != point:
                raise ValueError(f"Conflicting service points for {point.identifier}")
            points[point.identifier] = point
        except ValueError as exc:
            raise ValueError(f"DiDok record {index} (number={record.get('number')!r}): {exc}") from exc
    return list(points.values())


def emit_records(points: Iterable[ServicePoint]) -> str:
    """Assert base facts only; the ontology derives interchanges and other classes."""
    facts: list[str] = []
    for point in points:
        subject = point.identifier
        facts.append(f"{subject}:StopPoint.")
        if point.designation is not None:
            facts.append(property_fact(subject, "designation", point.designation))
        if point.canton is not None:
            canton = f"canton_{point.canton.lower()}"
            facts.extend([f"{canton}:Canton.", f"{subject}[inCanton -> {canton}]."])
        for mode in point.modes:
            target = MODE_IDS[mode]
            facts.extend([f"{target}:Mode.", f"{subject}[servesMode -> {target}]."])
    return "\n".join(facts) + ("\n" if facts else "")
