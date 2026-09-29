"""Positive WiFi evidence from the SBB Wifi@Station inventory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import warnings

from .identity import station_identifier, uic_code

DATASET_ID = "wifistation"
ORDER_BY = "bpuic"


@dataclass(frozen=True)
class WifiStation:
    uic: str
    location: str | None

    @property
    def identifier(self) -> str:
        return station_identifier(self.uic)


def normalize_record(record: dict) -> WifiStation | None:
    uic = record.get("bpuic")
    if uic is None or (isinstance(uic, str) and not uic.strip()):
        return None
    location = record.get("standort")
    if location is not None:
        if not isinstance(location, str):
            raise ValueError("standort must be text")
        location = " ".join(location.split()) or None
    return WifiStation(uic_code(uic, "bpuic"), location)


def normalize_records(records: Iterable[dict]) -> list[WifiStation]:
    points: dict[str, WifiStation] = {}
    for index, record in enumerate(records):
        try:
            point = normalize_record(record)
            if point is None:
                warnings.warn(f"Skipping WiFi record {index}: missing bpuic; cannot join by station identity",
                              stacklevel=2)
                continue
            # Multiple access points at one UIC are the same positive evidence.
            points.setdefault(point.identifier, point)
        except ValueError as exc:
            raise ValueError(f"WiFi record {index} (bpuic={record.get('bpuic')!r}): {exc}") from exc
    return list(points.values())


def emit_records(points: Iterable[WifiStation]) -> str:
    """Enrich existing identities; absence never creates a false WiFi fact.

    Inventory presence is the evidence: the API has no hasWifi boolean. Do not
    overwrite the authoritative DiDok designation with an inventory label.
    """
    return "".join(f"{point.identifier}[hasWifi -> true].\n" for point in points)
