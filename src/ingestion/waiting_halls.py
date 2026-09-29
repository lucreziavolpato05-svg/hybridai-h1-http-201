"""Waiting-room installations, preserving SBB's exact lifecycle status."""

import json
from dataclasses import dataclass

from .emiter import property_fact
from .values import report_skips, source_uic, stable_id, text

DATASET_ID = "haltestelle-wartehallen"


@dataclass(frozen=True)
class WaitingHall:
    identifier: str
    uic: str
    status: str | None


def normalize_record(record: dict) -> WaitingHall:
    uic = source_uic(record.get("bpuic"))
    # This dataset exposes no installation ID. Content identity preserves
    # distinct physical rows without pretending there is an upstream FID.
    identifier = stable_id("waitinghall", json.dumps(record, sort_keys=True, ensure_ascii=False))
    return WaitingHall(identifier, uic, text(record.get("status")))


def normalize_records(records: list[dict]) -> list[WaitingHall]:
    halls, errors = {}, []
    for index, record in enumerate(records):
        try:
            hall = normalize_record(record)
            halls[hall.identifier] = hall
        except ValueError as exc:
            errors.append(f"row {index}: {exc}")
    report_skips(DATASET_ID, errors)
    return list(halls.values())


def emit_records(halls: list[WaitingHall]) -> str:
    facts = []
    for hall in halls:
        facts.extend([f"{hall.identifier}:WaitingHall.",
                      f"{hall.identifier}[atStopPoint -> station_{hall.uic}]."])
        if hall.status is not None:
            facts.append(property_fact(hall.identifier, "status", hall.status))
    return "\n".join(facts) + ("\n" if facts else "")
