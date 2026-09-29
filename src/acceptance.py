"""Execute all 18 official questions against one offline FrameX session."""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter

from query import load_knowledge, open_client, runtime_arguments, validation_summary

# Reference expectations are regression checks only. Answers always come from
# FrameX; no reference entity is emitted into the knowledge base.
QUESTIONS = [
    ("1.1", "Chur WiFi", '?- ?S:StopPoint[designation -> "Chur"; hasWifi -> true].'),
    ("1.2", "Zurich HB platforms", '?- ?S:StopPoint[designation -> "Zürich HB"] AND ?P:Platform[atStopPoint -> ?S; platformNumber -> ?Number; platformLength -> ?Length].'),
    ("1.3", "Graubunden waiting halls", '?- ?S:StopPoint[inCanton -> canton_gr; hasWaitingHall -> true; designation -> ?Name].'),
    ("1.4", "Actual Bern categories", '?- ?S:StopPoint[designation -> "Bern"; servedByCategory -> ?Category].'),
    ("1.5", "2024 DTV over 50000", '?- ?S:StopPoint[designation -> ?Name; observedFrequency("2024") -> ?DTV] AND ?DTV > 50000.'),
    ("1.6", "Non-stop from Bern", '?- ?S:StopPoint[designation -> "Bern"; nonStopTo -> ?Destination] AND ?Destination:StopPoint[designation -> ?Name].'),
    ("1.7", "Long-distance without WiFi (open world)", '?- ?S:LongDistanceStation AND NOT ?S[hasWifi -> true].'),
    ("2.1", "Ticino WiFi", '?- ?S:StopPoint[inCanton -> canton_ti; hasWifi -> true; designation -> ?Name].'),
    ("2.2", "Bern platforms over 320 m", '?- ?S:StopPoint[designation -> "Bern"] AND ?P:LongPlatform[atStopPoint -> ?S; platformNumber -> ?Number; platformLength -> ?Length].'),
    ("2.3", "Zurich HB track 3 sectors", '?- ?S:StopPoint[designation -> "Zürich HB"] AND ?B:SectorBoard[atStopPoint -> ?S; trackNumber -> "3"; sectorFront -> ?Sector].'),
    ("2.4", "Bern canton planned new waiting halls", '?- ?S:StopPoint[inCanton -> canton_be; designation -> ?Name] AND ?H:WaitingHall[atStopPoint -> ?S; status -> "PROJEKTIERT NEU"].'),
    ("2.5", "Zurich canton waiting halls planned for demolition", '?- ?S:StopPoint[inCanton -> canton_zh; designation -> ?Name] AND ?H:WaitingHall[atStopPoint -> ?S; status -> "PROJEKTIERT ABBRUCH"].'),
    ("2.6", "Line 900 DTV in 2024", '?- ?L:Line[label -> "900"] AND ?S:StopPoint[servedByLine -> ?L; designation -> ?Name; observedFrequency("2024") -> ?DTV].'),
    ("3.1", "Graubunden junctions and lines", '?- ?S:Junction[inCanton -> canton_gr; designation -> ?Name; servedByLine -> ?L] AND ?L:Line[label -> ?Line].'),
    ("3.2", "Busy in 2025 but not in 2018", '?- ?S:StopPoint[designation -> ?Name; busyIn("2025") -> true; observedFrequency("2025") -> ?Now; observedFrequency("2018") -> ?Before] AND ?Before <= 20000.'),
    ("3.3", "Non-stop long-distance destinations from Zurich HB", '?- ?S:StopPoint[designation -> "Zürich HB"; nonStopToLongDistance -> ?Destination] AND ?Destination:LongDistanceStation[designation -> ?Name].'),
    ("3.4", "Actual TGV stations", '?- ?S:StopPoint[designation -> ?Name; servedByCategory -> "TGV"].'),
    ("3.5", "Train/tram interchanges", '?- ?S:Interchange[designation -> ?Name].'),
]

LIVE_IDS = {"1.4", "1.6", "3.3", "3.4"}
REFERENCE_DAY = "2026-09-27"


def value(term):
    """Decode FrameX literal renderings for comparisons, retaining object IDs."""
    if not isinstance(term, str):
        return term
    try:
        return json.loads(term)
    except ValueError:
        return term


def projection(result, *keys):
    return {tuple(value(row[key]) for key in keys) for row in result.get("bindings", [])}


def evaluate(identifier, result, operating_days):
    """Classify successful execution separately from historical differences."""
    rows = result.get("bindings", [])
    if identifier == "1.7":
        return ("PASS", "UNKNOWN: absence of WiFi evidence is not negative evidence") if result["status"] == "unknown" else ("FAIL", "Expected UNKNOWN for positive-only WiFi inventory")
    if result["status"] != "bindings" or not rows:
        return "FAIL", "Expected witnessed answers; inspect missing source evidence"
    if identifier in LIVE_IDS and operating_days != [REFERENCE_DAY]:
        return "LIVE-DATA DIFFERENCE", "Source day differs from 27 September reference; current witnesses checked"
    expected_names = {
        "1.3": {"Chur", "Landquart", "Maienfeld"},
        "2.1": {"Bellinzona", "Locarno", "Lugano"},
        "3.1": {"Chur", "Landquart"},
    }
    if identifier in expected_names and {value(row["Name"]) for row in rows} != expected_names[identifier]:
        return "LIVE-DATA DIFFERENCE", "Current inventory differs from supplied reference names"
    if identifier == "1.2" and sorted(float(value(row["Length"])) for row in rows) != [418, 424, 425, 425, 426, 426, 427, 428, 433]:
        return "LIVE-DATA DIFFERENCE", "Current platform lengths/count differ from reference"
    if identifier == "2.2" and len({row["P"] for row in rows}) != 7:
        return "LIVE-DATA DIFFERENCE", "Current long-platform count differs from reference seven"
    return "PASS", "FrameX returned source-backed answers"


def semantic_checks(client):
    """Check full-world invariants, not only whether demo queries return rows."""
    absent = {
        "no_cross_journey_edges": '?- ?E[nextStop -> ?N; journey -> ?J] AND ?N[journey -> ?K] AND ?J != ?K.',
        "no_cancelled_actual_stops": '?- ?E[cancelled -> true; actuallyStops -> true].',
        "no_pass_through_actual_stops": '?- ?E[passesThrough -> true; actuallyStops -> true].',
        "no_multiple_successors": '?- ?E[nextStop -> ?A; nextStop -> ?B] AND ?A != ?B.',
        "no_negative_wifi_assertions": '?- ?S[hasWifi -> false].',
    }
    checks = {name: client.query(query)["status"] == "unknown" for name, query in absent.items()}
    actual = client.query('?- ?E:StopEvent[actuallyStops -> true].')
    evidence = client.query('?- ?E:StopEvent[cancelled -> false; passesThrough -> false].')
    checks["actual_stops_equal_explicit_flags"] = projection(actual, "E") == projection(evidence, "E") and bool(actual.get("bindings"))
    edges = client.query('?- ?E[nextStop -> ?N; scheduledAt -> ?Before] AND ?N[scheduledAt -> ?After].')
    checks["chronological_edges"] = bool(edges.get("bindings")) and all(value(row["Before"]) < value(row["After"]) for row in edges.get("bindings", []))
    next_actual = projection(client.query('?- ?E[nextActualStop -> ?N].'), "E", "N")
    for flag in ("cancelled", "passesThrough"):
        expected = projection(client.query(f'?- ?E[nextStop -> ?M] AND ?M[{flag} -> true; nextActualStop -> ?N].'), "E", "N")
        checks[f"skip_{flag}_intermediates"] = expected <= next_actual
    for year in ("2018", "2024", "2025"):
        checks[f"frequency_{year}_present"] = bool(client.query(f'?- ?S[observedFrequency("{year}") -> ?V].').get("bindings"))
    return checks, len(actual.get("bindings", []))


def train_witnesses(client, results):
    """Compare train answers to explicit event evidence in the same FrameX world."""
    bern = client.query('?- ?S:StopPoint[designation -> "Bern"] AND ?E:StopEvent[atStopPoint -> ?S; category -> ?Category; cancelled -> false; passesThrough -> false].')
    tgv = client.query('?- ?S:StopPoint[designation -> ?Name] AND ?E:StopEvent[atStopPoint -> ?S; category -> "TGV"; cancelled -> false; passesThrough -> false].')
    checks = {
        "Bern_categories_have_actual_event_witnesses": projection(bern, "Category") == projection(results["1.4"], "Category"),
        "TGV_stations_have_actual_event_witnesses": projection(tgv, "S") == projection(results["3.4"], "S"),
    }
    for identifier, origin, extra in (("1.6", "Bern", ""), ("3.3", "Zürich HB", " AND ?Destination:LongDistanceStation")):
        q = ('?- ?S:StopPoint[designation -> ' + json.dumps(origin, ensure_ascii=False) + ']'
             ' AND ?E:StopEvent[atStopPoint -> ?S; journey -> ?J; cancelled -> false; passesThrough -> false; nextActualStop -> ?N]'
             ' AND ?N:StopEvent[journey -> ?J; atStopPoint -> ?Destination; cancelled -> false; passesThrough -> false]'
             ' AND ?Destination:StopPoint[designation -> ?Name]' + extra + '.')
        checks[f"{identifier}_same_journey_actual_stop_witnesses"] = projection(client.query(q), "Destination") == projection(results[identifier], "Destination")
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    runtime_arguments(parser)
    parser.add_argument("--output", type=Path, default=Path("docs/acceptance-results.json"))
    args = parser.parse_args(argv)
    report = {"queries": [], "fact_file_bytes": {p.name: p.stat().st_size for p in args.facts if p.exists()},
              "sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in [args.ontology, *args.facts] if p.exists()},
              "max_proofs": args.max_proofs, "request_timeout": args.request_timeout}
    try:
        with open_client(args) as client:
            started = perf_counter()
            report["load"] = load_knowledge(client, args.ontology, args.facts, max_proofs=args.max_proofs)
            report["load_seconds"] = perf_counter() - started
            report["stats"] = client.stats()
            print(f'Loaded {report["load"]} in {report["load_seconds"]:.2f}s', flush=True)
            report["validation"] = validation_summary(client.validate())
            report["operating_days"] = sorted(value(row["Day"]) for row in client.query('?- ?J:Journey[operatingDay -> ?Day].').get("bindings", []))
            report["operating_days"] = sorted(set(report["operating_days"]))
            results = {}
            for identifier, title, query in QUESTIONS:
                started = perf_counter()
                result = client.query(query)
                elapsed = (perf_counter() - started) * 1000
                results[identifier] = result
                status, detail = evaluate(identifier, result, report["operating_days"])
                report["queries"].append(dict(id=identifier, title=title, query=query, status=status,
                                               detail=detail, query_ms=elapsed, result=result))
                print(f'{identifier}: {status} ({len(result.get("bindings", []))} rows, {elapsed:.2f}ms)', flush=True)
            report["semantic_checks"], report["actual_stops"] = semantic_checks(client)
            report["semantic_checks"].update(train_witnesses(client, results))
            report["event_count"] = len(client.query('?- ?E:StopEvent.').get("bindings", []))
            explanations = [
                results["2.2"]["bindings"][0]["P"] + ":LongPlatform",
                results["3.1"]["bindings"][0]["S"] + ":Junction",
                results["3.3"]["bindings"][0]["Destination"] + ":LongDistanceStation",
                results["1.6"]["bindings"][0]["S"] + "[nonStopTo -> " + results["1.6"]["bindings"][0]["Destination"] + "]",
            ]
            report["explanations"] = {fact: client.explain(fact) for fact in explanations}
            for fact, explanation in report["explanations"].items():
                report["semantic_checks"]["explanation:" + fact] = (
                    isinstance(explanation, str) and "Derived by rule" in explanation and "Asserted fact" in explanation)
            if not all(report["semantic_checks"].values()):
                for row in report["queries"]:
                    if row["id"] in LIVE_IDS:
                        row.update(status="FAIL", detail="See failed semantic checks")
            report["summary"] = dict(Counter(row["status"] for row in report["queries"]))
            report["passed"] = (report["validation"]["violation_count"] == 0
                                and all(report["semantic_checks"].values())
                                and not any(row["status"] in {"FAIL", "NOT IMPLEMENTED"} for row in report["queries"]))
    except (OSError, ValueError, RuntimeError, KeyError, IndexError) as exc:
        report.update(passed=False, error=str(exc))
        print(f"Acceptance failed: {exc}", file=sys.stderr)
    executed = {row["id"] for row in report["queries"]}
    for identifier, title, query in QUESTIONS:
        if identifier not in executed:
            report["queries"].append(dict(id=identifier, title=title, query=query, status="FAIL",
                                           detail="Not executed: " + report.get("error", "runtime failure")))
    report["summary"] = {status: sum(row["status"] == status for row in report["queries"])
                         for status in ("PASS", "LIVE-DATA DIFFERENCE", "FAIL", "NOT IMPLEMENTED")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report.get("summary", {})) + f"; passed={report['passed']}; report={args.output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
