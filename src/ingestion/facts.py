"""Render normalized SBB records as FrameX base facts."""

from __future__ import annotations

import json

from .normalize import Connection, Station


def property_fact(subject: str, name: str, value: str | int | float) -> str:
    rendered = json.dumps(value, ensure_ascii=False) if isinstance(value, str) else str(value)
    return f"{subject}[{name} -> {rendered}]."


def reference_fact(subject: str, name: str, target: str) -> str:
    return f"{subject}[{name} -> {target}]."


def station_facts(station: Station) -> list[str]:
    facts = [f"{station.identifier}:Station.", property_fact(station.identifier, "name", station.name)]
    properties = (
        ("locality", station.locality),
        ("didok", station.didok),
        ("latitude", station.latitude),
        ("longitude", station.longitude),
    )
    for name, value in properties:
        if value is not None:
            facts.append(property_fact(station.identifier, name, value))
    for mode in station.modes:
        facts.append(property_fact(station.identifier, "mode", mode))
    return facts


def connection_facts(connection: Connection, stations: list[Station]) -> list[str]:
    facts = [f"{connection.identifier}:DirectConnection.", property_fact(connection.identifier, "name", connection.name)]
    by_name = {station.name: station.identifier for station in stations}
    by_didok = {station.didok: station.identifier for station in stations if station.didok}
    for property_name, station_name in (("startStation", connection.start), ("endStation", connection.end)):
        station_id = by_name.get(station_name)
        if station_id:
            facts.append(reference_fact(connection.identifier, property_name, station_id))
    for station_name, didok in connection.vias:
        station_id = by_didok.get(didok) or by_name.get(station_name)
        if station_id:
            facts.append(reference_fact(connection.identifier, "viaStation", station_id))
    return facts