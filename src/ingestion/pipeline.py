"""Orchestrate SBB download, cleaning, normalization, and FrameX export."""

from __future__ import annotations

import argparse
from pathlib import Path

from .download import fetch_records
from .facts import connection_facts, station_facts
from .normalize import Connection, Station


STATION_DATASET = "haltestelle-haltekante"
CONNECTION_DATASET = "direktverbindungen"
STATION_FIELDS = ["sloid", "number", "designationofficial", "localityname", "meansoftransport", "geopos_haltestelle"]
CONNECTION_FIELDS = ["id", "name", "start_station_name", "end_station_name", "vias"]
STATION_WHERE = 'meansoftransport like "%TRAIN%" OR meansoftransport like "%RACK_RAILWAY%"'


def build_framex(*, station_limit: int | None = None, connection_limit: int | None = None) -> str:
    raw_stations = fetch_records(STATION_DATASET, STATION_FIELDS, limit=station_limit, where=STATION_WHERE)
    stations = [station for record in raw_stations if (station := Station.from_record(record)) is not None]
    raw_connections = fetch_records(CONNECTION_DATASET, CONNECTION_FIELDS, limit=connection_limit)
    connections = [connection for record in raw_connections if (connection := Connection.from_record(record)) is not None]
    facts = ["world open."]
    for station in stations:
        facts.extend(station_facts(station))
    for connection in connections:
        facts.extend(connection_facts(connection, stations))
    return "\n".join(facts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="output .fx file")
    parser.add_argument("--station-limit", type=int, help="maximum station records to fetch")
    parser.add_argument("--connection-limit", type=int, help="maximum connection records to fetch")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        build_framex(station_limit=args.station_limit, connection_limit=args.connection_limit),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())