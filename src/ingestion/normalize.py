"""Stable internal records for SBB stations and direct connections."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .clean import parse_vias, passenger_rail, text


def identifier(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_")
    return normalized or "unknown"


def station_identifier(number, sloid) -> str | None:
    source = number if number is not None else sloid
    return f"station_{identifier(str(source))}" if source else None


@dataclass(frozen=True)
class Station:
    identifier: str
    name: str
    locality: str | None = None
    didok: str | None = None
    modes: tuple[str, ...] = ()
    latitude: float | None = None
    longitude: float | None = None

    @classmethod
    def from_record(cls, record: dict) -> "Station | None":
        if not passenger_rail(record):
            return None
        name = text(record.get("designationofficial"))
        station_id = station_identifier(record.get("number"), record.get("sloid"))
        if not name or not station_id:
            return None
        point = record.get("geopos_haltestelle") or {}
        modes = tuple(part for part in (text(record.get("meansoftransport")) or "").split("|") if part)
        return cls(
            identifier=station_id,
            name=name,
            locality=text(record.get("localityname")),
            didok=str(record["number"]) if record.get("number") is not None else None,
            modes=modes,
            latitude=point.get("lat"),
            longitude=point.get("lon"),
        )


@dataclass(frozen=True)
class Connection:
    identifier: str
    name: str
    start: str
    end: str
    vias: tuple[tuple[str, str | None], ...] = ()

    @classmethod
    def from_record(cls, record: dict) -> "Connection | None":
        start = text(record.get("start_station_name"))
        end = text(record.get("end_station_name"))
        if not record.get("id") or not start or not end:
            return None
        vias = tuple(
            (text(item.get("station_name")), str(item["didok"]) if item.get("didok") else None)
            for item in parse_vias(record.get("vias"))
            if text(item.get("station_name"))
        )
        return cls(
            identifier=f"connection_{identifier(str(record['id']))}",
            name=text(record.get("name")) or str(record["id"]),
            start=start,
            end=end,
            vias=vias,
        )