"""Prepare dataset-specific base-fact files for offline FrameX reasoning."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import didok, wifi
from .connector import DEFAULT_RAW_DIR, fetch_dataset_records, fetch_records
from .emiter import emit_records as emit_platforms
from .ingest import non_negative
from .normalizer import normalize_records as normalize_platforms


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", choices=("platforms", "didok", "wifi"),
                        default=["platforms", "didok", "wifi"])
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
            if dataset == "platforms":
                raw = fetch_records(**options)
                records = normalize_platforms(raw)
                source, filename = emit_platforms(records), "platforms.fx"
            elif dataset == "didok":
                raw = fetch_dataset_records(didok.DATASET_ID, order_by=didok.ORDER_BY,
                                            where=didok.WHERE, **options)
                records = didok.normalize_records(raw, as_of=args.as_of)
                source, filename = didok.emit_records(records), "service_points.fx"
                source = f"// DiDok validity date: {args.as_of.isoformat()}\n" + source
            else:
                raw = fetch_dataset_records(wifi.DATASET_ID, order_by=wifi.ORDER_BY, **options)
                records = wifi.normalize_records(raw)
                source, filename = wifi.emit_records(records), "wifi.fx"
            output = args.output_dir / filename
            output.write_text("world open.\n" + source, encoding="utf-8")
            print(f"{dataset}: {len(raw)} raw rows -> {len(records)} normalized records -> {output}")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
