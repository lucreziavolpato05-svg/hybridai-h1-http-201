"""Fetch SBB platforms, emit F-logic, and ingest it with client.add(source=...)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from framex import Client, FrameXError

from .connector import DEFAULT_RAW_DIR, fetch_records
from .emiter import emit_records
from .normalizer import Platform, normalize_records

DEFAULT_OUTPUT = DEFAULT_RAW_DIR.parent / "platforms.fx"


def source_batches(source: str, *, max_bytes: int = 500_000) -> Iterable[str]:
    """Split at statement lines, allowing for JSON escaping and request overhead."""
    if not 128 <= max_bytes <= 900_000:
        raise ValueError("max_bytes must be between 128 and 900000")
    lines: list[str] = []
    size = 128  # JSON command envelope and request ID allowance.
    for line in source.splitlines(keepends=True):
        line_size = len(json.dumps(line, ensure_ascii=False).encode("utf-8")) - 2
        if line_size + 128 > max_bytes:
            raise ValueError("A single fact exceeds the FrameX batch size")
        if size + line_size > max_bytes:
            yield "".join(lines)
            lines, size = [], 128
        lines.append(line)
        size += line_size
    if lines:
        yield "".join(lines)


def ingest_platforms(client: Client, platforms: Iterable[Platform]) -> int:
    """Append facts to an existing session without loading/replacing its program.

    Adds are incremental, not atomic across batches. On an engine error, stop
    without retrying; earlier successful batches remain in the caller's session.
    """
    batches = list(source_batches(emit_records(platforms)))
    for source in batches:
        client.add(source=source)
    return len(batches)


def non_negative(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=non_negative, help="maximum raw records (default: all)")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--refresh", action="store_true", help="replace cached snapshot from the API")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true", help="cache and emit without starting FrameX")
    parser.add_argument("--binary", default="framex", help="FrameX executable path")
    parser.add_argument("--query", help="optional F-logic query to run after ingestion")
    args = parser.parse_args(argv)
    if args.dry_run and args.query:
        parser.error("--query requires a FrameX session; remove --dry-run")
    try:
        records = fetch_records(limit=args.limit, raw_dir=args.raw_dir, refresh=args.refresh)
        platforms = normalize_records(records)
        source = emit_records(platforms)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("world open.\n" + source, encoding="utf-8")
        print(f"Prepared {len(platforms)} platforms from {len(records)} raw records: {args.output}")
        if not args.dry_run:
            with Client(binary=args.binary, retain_transcript=False) as client:
                client.load("world open.")
                batches = ingest_platforms(client, platforms)
                print(f"Added platforms in {batches} batches: {json.dumps(client.stats(), ensure_ascii=False)}")
                if args.query:
                    print(json.dumps(client.query(args.query), ensure_ascii=False))
    except (OSError, ValueError, RuntimeError, FrameXError) as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
