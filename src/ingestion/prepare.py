"""Prepare dataset-specific base-fact files for offline FrameX reasoning."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import didok, lines, passengers, sector_boards, stop_events, waiting_halls, wifi
from .connector import DEFAULT_RAW_DIR, fetch_dataset_export, fetch_dataset_records, fetch_records
from .emiter import emit_records as emit_platforms
from .ingest import non_negative
from .normalizer import normalize_records as normalize_platforms


@dataclass(frozen=True)
class PreparedDataset:
    """One independently cached source and its generated local fact file."""

    source_id: str
    filename: str
    fetch: Callable[..., list[dict]]
    transform: Callable[..., tuple[str, int]]
    needs_station_scope: bool = False


def _platform_facts(raw: list[dict], _: date) -> tuple[str, int]:
    records = normalize_platforms(raw)
    return emit_platforms(records), len(records)


def _service_point_facts(raw: list[dict], as_of: date) -> tuple[str, int]:
    records = didok.normalize_records(raw, as_of=as_of)
    source = f"// DiDok validity date: {as_of.isoformat()}\n" + didok.emit_records(records)
    return source, len(records)


def _wifi_facts(raw: list[dict], _: date) -> tuple[str, int]:
    records = wifi.normalize_records(raw)
    return wifi.emit_records(records), len(records)


def _fetch_platforms(**options: object) -> list[dict]:
    return fetch_records(**options)


def _fetch_service_points(**options: object) -> list[dict]:
    return fetch_dataset_records(didok.DATASET_ID, order_by=didok.ORDER_BY,
                                 where=didok.WHERE, **options)


def _fetch_wifi(**options: object) -> list[dict]:
    return fetch_dataset_records(wifi.DATASET_ID, order_by=wifi.ORDER_BY, **options)


def _fetch_stop_events(**options: object) -> list[dict]:
    if options.pop("limit", None) is not None:
        raise ValueError("stop_events requires complete journeys; omit --limit")
    return fetch_dataset_export(stop_events.DATASET_ID, where=stop_events.WHERE, **options)


def _stop_event_facts(raw: list[dict], _: date, *, swiss_uics: set[str]) -> tuple[str, int]:
    records = stop_events.normalize_records(raw)
    days = ", ".join(sorted({event.operating_day for event in records}))
    source = f"// Source: {stop_events.DATASET_ID}; operating days: {days}\n"
    return source + stop_events.emit_records(records, swiss_uics=swiss_uics), len(records)


def _fetch_waiting_halls(**options: object) -> list[dict]:
    return fetch_dataset_records(waiting_halls.DATASET_ID, order_by="bpuic, km", **options)


def _waiting_hall_facts(raw: list[dict], _: date) -> tuple[str, int]:
    records = waiting_halls.normalize_records(raw)
    return waiting_halls.emit_records(records), len(records)


def _fetch_passengers(**options: object) -> list[dict]:
    return fetch_dataset_records(passengers.DATASET_ID, order_by="uic, jahr_annee_anno", **options)


def _passenger_facts(raw: list[dict], _: date) -> tuple[str, int]:
    records = passengers.normalize_records(raw)
    return passengers.emit_records(records), len(records)


def _fetch_lines(**options: object) -> list[dict]:
    return fetch_dataset_records(lines.DATASET_ID, order_by="linie, km, bpuic", **options)


def _line_facts(raw: list[dict], _: date) -> tuple[str, int]:
    records = lines.normalize_records(raw)
    return lines.emit_records(records), len(records)


def _fetch_sector_boards(**options: object) -> list[dict]:
    return fetch_dataset_records(sector_boards.DATASET_ID, order_by="fid", **options)


def _sector_board_facts(raw: list[dict], _: date) -> tuple[str, int]:
    records = sector_boards.normalize_records(raw)
    return sector_boards.emit_records(records), len(records)


# Each adapter shares data/raw/ through DEFAULT_RAW_DIR, but owns its request
# filter, normalizer, and emitted facts. Add a future dataset here, rather than
# adding another CLI branch.
DATASETS = {
    "platforms": PreparedDataset("perron", "platforms.fx", _fetch_platforms, _platform_facts),
    "service_points": PreparedDataset(didok.DATASET_ID, "service_points.fx",
                                       _fetch_service_points, _service_point_facts),
    "wifi": PreparedDataset(wifi.DATASET_ID, "wifi.fx", _fetch_wifi, _wifi_facts),
    "stop_events": PreparedDataset(stop_events.DATASET_ID, "stop_events.fx",
                                   _fetch_stop_events, _stop_event_facts, True),
    "waiting_halls": PreparedDataset(waiting_halls.DATASET_ID, "waiting_halls.fx", _fetch_waiting_halls, _waiting_hall_facts),
    "passengers": PreparedDataset(passengers.DATASET_ID, "passengers.fx", _fetch_passengers, _passenger_facts),
    "lines": PreparedDataset(lines.DATASET_ID, "lines.fx", _fetch_lines, _line_facts),
    "sector_boards": PreparedDataset(sector_boards.DATASET_ID, "sector_boards.fx", _fetch_sector_boards, _sector_board_facts),
}
DATASET_ALIASES = {"didok": "service_points"}


def dataset_name(value: str) -> str:
    """Parse a CLI dataset name, keeping the old DiDok spelling usable."""
    normalized = value.strip().lower().replace("-", "_")
    canonical = DATASET_ALIASES.get(normalized, normalized)
    if canonical not in DATASETS:
        choices = ", ".join(DATASETS)
        raise argparse.ArgumentTypeError(f"unknown dataset {value!r}; choose one of: {choices}")
    return canonical


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", type=dataset_name, metavar="DATASET",
                        default=list(DATASETS),
                        help="one or more of: " + ", ".join(DATASETS) + " (default: all)")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RAW_DIR.parent)
    parser.add_argument("--limit", type=non_negative, help="raw sample limit per dataset (default: all)")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today(),
                        help="DiDok validity date, YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)
    options = {"raw_dir": args.raw_dir, "limit": args.limit, "refresh": args.refresh}
    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        swiss_uics = None
        for dataset in dict.fromkeys(args.datasets):
            definition = DATASETS[dataset]
            raw = definition.fetch(**options)
            context = {}
            if definition.needs_station_scope:
                if swiss_uics is None:
                    scope = _fetch_service_points(raw_dir=args.raw_dir, limit=None, refresh=False)
                    swiss_uics = {point.uic for point in didok.normalize_records(scope, as_of=args.as_of)}
                context["swiss_uics"] = swiss_uics
            source, normalized_count = definition.transform(raw, args.as_of, **context)
            output = args.output_dir / definition.filename
            output.write_text("world open.\n" + source, encoding="utf-8")
            print(f"{dataset}: {len(raw)} raw rows -> {normalized_count} normalized records -> {output}")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
