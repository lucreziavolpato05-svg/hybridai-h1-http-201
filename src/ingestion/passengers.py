"""Annual average daily passenger traffic (DTV, Monday through Sunday)."""

import re
from dataclasses import dataclass

from .emiter import literal
from .normalizer import number
from .values import report_skips, source_uic, text

DATASET_ID = "passagierfrequenz"


@dataclass(frozen=True)
class PassengerFrequency:
    uic: str
    year: str
    daily_traffic: float


def normalize_record(record: dict) -> PassengerFrequency | None:
    uic = source_uic(record.get("uic"))
    year = text(record.get("jahr_annee_anno"))
    if year is None or not re.fullmatch(r"[0-9]{4}", year):
        raise ValueError(f"Invalid observation year: {year!r}")
    value = number(record.get("dtv_tjm_tgm"), "dtv_tjm_tgm", minimum=0)
    if value is None:
        return None
    return PassengerFrequency(uic, year, value)


def normalize_records(records: list[dict]) -> list[PassengerFrequency]:
    observations, conflicting, errors = {}, set(), []
    for index, record in enumerate(records):
        try:
            observation = normalize_record(record)
            if observation is None:
                continue
            key = (observation.uic, observation.year)
            if key in observations and observations[key] != observation:
                conflicting.add(key)
                raise ValueError(f"Conflicting DTV values for {key}; observation omitted")
            observations[key] = observation
        except ValueError as exc:
            errors.append(f"row {index}: {exc}")
    report_skips(DATASET_ID, errors)
    return [observation for key, observation in observations.items() if key not in conflicting]


def emit_records(observations: list[PassengerFrequency]) -> str:
    # The acceptance contract uses string-valued years, consistently in facts/queries.
    return "".join(f"station_{row.uic}[observedFrequency({literal(row.year)}) -> {literal(row.daily_traffic)}].\n"
                   for row in observations)
