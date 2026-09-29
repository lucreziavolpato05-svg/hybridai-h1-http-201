"""Load local ontology and facts, then query/explain using FrameX only."""

from __future__ import annotations

import argparse
import json
import os
import sys
from time import perf_counter
from collections import Counter
from pathlib import Path

from framex import Client

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FACTS = [ROOT / "data" / name for name in (
    "platforms.fx", "service_points.fx", "wifi.fx", "stop_events.fx",
    "waiting_halls.fx", "passengers.fx", "lines.fx", "sector_boards.fx",
)]
# Full scoped snapshot: 277,896 rule firings, 13 rounds; see docs/scalability.md.
DEFAULT_MAX_PROOFS = 1_000_000
DEMOS = {
    "chur-wifi": '?- ?S:StopPoint[designation -> "Chur"; hasWifi -> true].',
    "zurich-platforms": '?- ?S:StopPoint[designation -> "Zürich HB"] AND ?P:Platform[atStopPoint -> ?S; platformNumber -> ?Number; platformLength -> ?Length].',
    "bern-long-platforms": '?- ?S:StopPoint[designation -> "Bern"] AND ?P:LongPlatform[atStopPoint -> ?S; platformNumber -> ?Number; platformLength -> ?Length].',
    "ticino-wifi": '?- ?S:StopPoint[inCanton -> canton_ti; hasWifi -> true; designation -> ?Name].',
    "open-world-wifi": '?- ?S:LongDistanceStation AND NOT ?S[hasWifi -> true].',
}


def load_knowledge(client: Client, ontology: Path, facts: list[Path], **limits) -> dict:
    """Stage one combined program so ontology rules see all datasets together."""
    source = "\n".join(path.read_text(encoding="utf-8") for path in [ontology, *facts])
    return client.load_program(source=source, **limits)


def runtime_arguments(parser: argparse.ArgumentParser) -> None:
    """Shared application/acceptance runtime controls; transport stays unchanged."""
    parser.add_argument("--binary", default=os.environ.get("FRAMEX_BINARY") or "framex")
    parser.add_argument("--ontology", type=Path, default=ROOT / "ontology.fx")
    parser.add_argument("--facts", type=Path, nargs="+", default=DEFAULT_FACTS)
    parser.add_argument("--max-proofs", type=int, default=DEFAULT_MAX_PROOFS,
                        help="bulk inference proof budget (default: 1000000)")
    parser.add_argument("--request-timeout", type=float, default=180,
                        help="seconds per engine request (default: 180)")


def open_client(args) -> Client:
    # Full validation includes one schema check per event and exceeds 8 MiB.
    return Client(binary=args.binary, request_timeout=args.request_timeout,
                  max_response_bytes=64 * 1024 * 1024, retain_transcript=False)


def print_result(query: str, result: dict) -> None:
    print(query)
    print(f"status: {result['status']}")
    # A missing bindings key is normal for true/false/unknown ground results.
    print("bindings: " + json.dumps(result.get("bindings", []), ensure_ascii=False))


def validation_summary(result: dict) -> dict:
    """Keep large schema reports readable without hiding unresolved checks."""
    violations = result.get("violations", [])
    return {
        "constraint_checks": dict(Counter(row["status"] for row in result.get("constraint_checks", []))),
        "schema_checks": dict(Counter(row["status"] for row in result.get("schema_checks", []))),
        "unknown_schemas": dict(Counter(row.get("schema", "unspecified") for row in result.get("schema_checks", [])
                                        if row["status"] == "unknown")),
        "violation_count": len(violations),
        "first_10_violations": violations[:10],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    runtime_arguments(parser)
    parser.add_argument("--query", action="append", default=[], help="F-logic query; repeatable")
    parser.add_argument("--demo", choices=tuple(DEMOS), action="append", default=[])
    parser.add_argument("--explain", action="append", default=[], help="ground fact to explain; repeatable")
    parser.add_argument("--validate", action="store_true", help="summarize ontology constraint diagnostics")
    parser.add_argument("--stats", action="store_true", help="print engine inference statistics and load time")
    args = parser.parse_args(argv)
    demos = args.demo or ([] if args.query or args.explain else list(DEMOS))
    try:
        with open_client(args) as client:
            started = perf_counter()
            print("loaded: " + json.dumps(load_knowledge(client, args.ontology, args.facts,
                                                       max_proofs=args.max_proofs)), flush=True)
            if args.stats:
                print("stats: " + json.dumps({"load_seconds": perf_counter() - started, **client.stats()}))
            violations = 0
            if args.validate:
                summary = validation_summary(client.validate())
                violations = summary["violation_count"]
                print("validation: " + json.dumps(summary, ensure_ascii=False))
            for name in demos:
                print(f"\n{name}")
                print_result(DEMOS[name], client.query(DEMOS[name]))
            for query in args.query:
                print_result(query, client.query(query))
            for fact in args.explain:
                print(f"explain: {fact}")
                explanation = client.explain(fact)
                print(explanation if isinstance(explanation, str) else json.dumps(explanation, ensure_ascii=False, indent=2))
            if violations:
                return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Query failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
