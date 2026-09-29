"""Load local ontology and facts, then query/explain using FrameX only."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from framex import Client

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FACTS = [ROOT / "data" / name for name in ("platforms.fx", "service_points.fx", "wifi.fx")]
DEMOS = {
    "chur-wifi": '?- ?S:StopPoint[designation -> "Chur"; hasWifi -> true].',
    "zurich-platforms": '?- ?S:StopPoint[designation -> "Zürich HB"] AND ?P:Platform[atStopPoint -> ?S; platformNumber -> ?Number; platformLength -> ?Length].',
    "bern-long-platforms": '?- ?S:StopPoint[designation -> "Bern"] AND ?P:LongPlatform[atStopPoint -> ?S; platformNumber -> ?Number; platformLength -> ?Length].',
    "ticino-wifi": '?- ?S:StopPoint[inCanton -> canton_ti; hasWifi -> true; designation -> ?Name].',
    "open-world-wifi": '?- ?S:LongDistanceStation AND NOT ?S[hasWifi -> true].',
}


def load_knowledge(client: Client, ontology: Path, facts: list[Path]) -> dict:
    """Stage one combined program so ontology rules see all datasets together."""
    source = "\n".join(path.read_text(encoding="utf-8") for path in [ontology, *facts])
    return client.load_program(source=source)


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
        "violation_count": len(violations),
        "first_10_violations": violations[:10],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default="framex")
    parser.add_argument("--ontology", type=Path, default=ROOT / "ontology.fx")
    parser.add_argument("--facts", type=Path, nargs="+", default=DEFAULT_FACTS)
    parser.add_argument("--query", action="append", default=[], help="F-logic query; repeatable")
    parser.add_argument("--demo", choices=tuple(DEMOS), action="append", default=[])
    parser.add_argument("--explain", action="append", default=[], help="ground fact to explain; repeatable")
    parser.add_argument("--validate", action="store_true", help="summarize ontology constraint diagnostics")
    args = parser.parse_args(argv)
    demos = args.demo or ([] if args.query or args.explain else list(DEMOS))
    try:
        with Client(binary=args.binary, retain_transcript=False) as client:
            print("loaded: " + json.dumps(load_knowledge(client, args.ontology, args.facts)))
            if args.validate:
                print("validation: " + json.dumps(validation_summary(client.validate()), ensure_ascii=False))
            for name in demos:
                print(f"\n{name}")
                print_result(DEMOS[name], client.query(DEMOS[name]))
            for query in args.query:
                print_result(query, client.query(query))
            for fact in args.explain:
                print(f"explain: {fact}")
                explanation = client.explain(fact)
                print(explanation if isinstance(explanation, str) else json.dumps(explanation, ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Query failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
