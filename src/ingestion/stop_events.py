"""Complete train-journey events from ist-daten-sbb; FrameX derives non-stop links."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Iterable
import warnings

from .emiter import property_fact
from .values import boolean, report_skips, source_uic, stable_id, text

DATASET_ID = "ist-daten-sbb"
WHERE = 'produkt_id = "Zug"'


@dataclass(frozen=True)
class StopEvent:
    identifier: str
    journey: str
    source_journey: str
    operator: str
    operating_day: str
    uic: str
    category: str | None
    arrival: datetime | None
    departure: datetime | None
    cancelled: bool | None
    passes_through: bool | None
    next_event: str | None = None

    @property
    def scheduled(self) -> datetime:
        return self.arrival or self.departure


def journey_key(record: dict) -> tuple[str, str, str]:
    day = date.fromisoformat(str(record.get("betriebstag"))).isoformat()
    operator, journey = text(record.get("betreiber_id")), text(record.get("fahrt_bezeichner"))
    if not operator or not journey:
        raise ValueError("Missing operator or journey identity; cannot safely build event chains")
    return day, operator, journey


def _time(value: object) -> datetime | None:
    value = text(value)
    if value is None:
        return None
    result = datetime.fromisoformat(value)
    if result.tzinfo is not None:
        raise ValueError("Expected source-local Europe/Berlin schedule timestamps")
    return result


def normalize_record(record: dict) -> StopEvent:
    day, operator, journey = journey_key(record)
    uic = source_uic(record.get("bpuic"))
    arrival, departure = _time(record.get("ankunftszeit")), _time(record.get("abfahrtszeit"))
    if arrival is None and departure is None:
        raise ValueError("Missing both scheduled arrival and departure")
    if arrival and departure and departure < arrival:
        raise ValueError("Departure precedes arrival")
    scheduled = arrival or departure
    if not 0 <= (scheduled.date() - date.fromisoformat(day)).days <= 1:
        raise ValueError("Schedule is outside operating day and following midnight")
    return StopEvent(
        identifier=stable_id("event", day, operator, journey, uic, str(arrival), str(departure)),
        journey=stable_id("journey", day, operator, journey), source_journey=journey,
        operator=operator, operating_day=day, uic=uic,
        category=text(record.get("verkehrsmittel_text")), arrival=arrival, departure=departure,
        cancelled=boolean(record.get("faellt_aus_tf")), passes_through=boolean(record.get("durchfahrt_tf")),
    )


def normalize_records(records: Iterable[dict]) -> list[StopEvent]:
    groups: dict[tuple[str, str, str], dict[str, StopEvent]] = defaultdict(dict)
    unsafe = set()
    errors: list[str] = []
    for index, record in enumerate(records):
        if (text(record.get("produkt_id")) or "").casefold() != "zug":
            continue
        # Missing group identity fails loudly: discarding it could hide an
        # intermediate stop in a journey we can no longer identify.
        key = journey_key(record)
        try:
            event = normalize_record(record)
            previous = groups[key].get(event.identifier)
            if previous is not None and previous != event:
                raise ValueError("Conflicting duplicate event")
            groups[key][event.identifier] = event
        except ValueError as exc:
            unsafe.add(key)
            errors.append(f"row {index}, journey {key}: {exc}")
    report_skips(DATASET_ID, errors)
    output: list[StopEvent] = []
    for key, events in sorted(groups.items()):
        ordered = sorted(events.values(), key=lambda event: (event.scheduled, event.identifier))
        # Source has no sequence field. Equal schedule times at distinct calls,
        # overlapping dwell intervals, or a malformed row make order uncertain.
        if any(a.scheduled == b.scheduled or (a.departure and a.departure > b.scheduled)
               for a, b in zip(ordered, ordered[1:])):
            unsafe.add(key)
        for index, event in enumerate(ordered):
            if key not in unsafe and index + 1 < len(ordered):
                event = replace(event, next_event=ordered[index + 1].identifier)
            output.append(event)
    if unsafe:
        warnings.warn(f"{DATASET_ID}: omitted nextStop links for {len(unsafe)} uncertain journeys", stacklevel=2)
    return output


def emit_records(events: Iterable[StopEvent], *, swiss_uics: set[str] | None = None) -> str:
    """Keep foreign calls as chain barriers, without exposing foreign stop points.

    Preparation passes the scoped DiDok UIC set. Raw scheduled times define call
    order, not delay/forecast order; no derived nonStopTo facts are emitted here.
    """
    facts: list[str] = []
    journeys: set[str] = set()
    for event in events:
        if event.journey not in journeys:
            journeys.add(event.journey)
            facts.extend([f"{event.journey}:Journey.",
                          property_fact(event.journey, "operatingDay", event.operating_day),
                          property_fact(event.journey, "sourceJourney", event.source_journey),
                          property_fact(event.journey, "operator", event.operator)])
        subject = event.identifier
        facts.extend([f"{subject}:StopEvent.", f"{subject}[journey -> {event.journey}].",
                      property_fact(subject, "sourceUic", event.uic),
                      property_fact(subject, "scheduledAt", event.scheduled.isoformat())])
        if swiss_uics is not None and event.uic in swiss_uics:
            facts.append(f"{subject}[atStopPoint -> station_{event.uic}].")
        for name, value in (("category", event.category), ("cancelled", event.cancelled),
                            ("passesThrough", event.passes_through)):
            if value is not None:
                facts.append(property_fact(subject, name, value))
        if event.next_event:
            facts.append(f"{subject}[nextStop -> {event.next_event}].")
    return "\n".join(facts) + ("\n" if facts else "")
