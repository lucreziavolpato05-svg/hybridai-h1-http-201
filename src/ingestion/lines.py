"""Station memberships of infrastructure lines from Line (Operation Points)."""

from dataclasses import dataclass

from .emiter import property_fact
from .normalizer import code
from .values import report_skips, source_uic

DATASET_ID = "linie-mit-betriebspunkten"


@dataclass(frozen=True)
class LineMembership:
    uic: str
    line: str


def normalize_record(record: dict) -> LineMembership:
    line = code(record.get("linie"), "linie")
    if line is None:
        raise ValueError("Missing infrastructure line number")
    return LineMembership(source_uic(record.get("bpuic")), line)


def normalize_records(records: list[dict]) -> list[LineMembership]:
    memberships, errors = {}, []
    for index, record in enumerate(records):
        try:
            membership = normalize_record(record)
            memberships[(membership.uic, membership.line)] = membership
        except ValueError as exc:
            errors.append(f"row {index}: {exc}")
    report_skips(DATASET_ID, errors)
    return list(memberships.values())


def emit_records(memberships: list[LineMembership]) -> str:
    facts, seen = [], set()
    for row in memberships:
        line = f"line_{row.line}"
        if line not in seen:
            seen.add(line)
            facts.extend([f"{line}:Line.", property_fact(line, "label", row.line)])
        facts.append(f"station_{row.uic}[servedByLine -> {line}].")
    return "\n".join(facts) + ("\n" if facts else "")
