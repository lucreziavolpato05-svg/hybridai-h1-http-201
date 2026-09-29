"""Prepare dataset-specific base-fact files for offline FrameX reasoning."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import didok, wifi
from .connector import DEFAULT_RAW_DIR, fetch_dataset_records, fetch_records
from .emiter import emit_records as emit_platforms
from .ingest import non_negative
from .normalizer import normalize_records as normalize_platforms


@dataclass(frozen=True)
class PreparedDataset:
    """One independently cached source and its generated local fact file."""

    source_id: str
    filename: str
    fetch: Callable[..., list[dict]]
    transform: Callable[[list[dict], date], tuple[str, int]]


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


# Each adapter shares data/raw/ through DEFAULT_RAW_DIR, but owns its request
# filter, normalizer, and emitted facts. Add a future dataset here, rather than
# adding another CLI branch.
DATASETS = {
    "platforms": PreparedDataset("perron", "platforms.fx", _fetch_platforms, _platform_facts),
    "service_points": PreparedDataset(didok.DATASET_ID, "service_points.fx",
                                       _fetch_service_points, _service_point_facts),
    "wifi": PreparedDataset(wifi.DATASET_ID, "wifi.fx", _fetch_wifi, _wifi_facts),
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
                        help="one or more of: platforms, service_points, wifi (default: all)")
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
        for dataset in dict.fromkeys(args.datasets):
            definition = DATASETS[dataset]
            raw = definition.fetch(**options)
            source, normalized_count = definition.transform(raw, args.as_of)
            output = args.output_dir / definition.filename
            output.write_text("world open.\n" + source, encoding="utf-8")
            print(f"{dataset}: {len(raw)} raw rows -> {normalized_count} normalized records -> {output}")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
