# Final verification: 29 September 2026

The implemented Hackathon 1 system is operational. All 18 official questions
execute on the complete local snapshot; no query is unimplemented. Before final
submission, the team must fill the exact coding-model declaration in README.
No commit or push was performed by the finalization session.

## Evidence from this run

- Baseline: 53 unit tests, one pre-existing failure in the obsolete three-source
  default-preparation test; 15 integration tests passed. That unit test also
  lacked an export mock and accidentally called the network. It now verifies
  all eight sources, shared cache use, and an offline export mock.
- Final: **67 offline unit tests and 17 real-engine integration tests passed**.
- `uv sync` completed with Python 3.12 and no third-party dependencies.
- All eight datasets were prepared from existing cached snapshots. Cold network
  ingestion was not rebenchmarked. Preparation reports raw/normalized counts,
  sizes, and elapsed times in [preparation-results.json](preparation-results.json).
- Full acceptance: **13 PASS, 5 LIVE-DATA DIFFERENCE, 0 FAIL, 0 NOT IMPLEMENTED**.
- Validation: **zero violations**, 91,386 satisfied schema checks, 68 unknown
  required-field checks (7 platform lengths, 61 canonical station designations).
  Seven constraint bodies remain UNKNOWN under open-world semantics; absence of
  a violation is not a global completeness/consistency certificate.
- Every full-world semantic check passed: exact actual-stop flags, no cancelled
  or passing actual stops, chronological links, same journey, one successor,
  cancellation/pass-through skipping, all three passenger years, positive-only
  WiFi, and source-event witnesses for the four train questions.
- Four engine explanations include both `Derived by rule` and `Asserted fact`:
  LongPlatform, Junction, LongDistanceStation, and nonStopTo. Full unedited texts
  are embedded in [acceptance-results.json](acceptance-results.json).
- Main/demo entry point, arbitrary query, validation, stats and explanation
  executed together successfully. `git diff --check` passed.

## Official acceptance results

PASS means the actual query executed and met the encoded current-evidence/reference
checks. LIVE-DATA DIFFERENCE also requires successful execution. Four train cases
are labeled for the source-date difference, not an assertion that every answer
changed. Reference constants are used only for regression comparison. See the JSON
report for queries, all bindings, input SHA-256 hashes and individual check results.

| ID | Question | Status | Binding rows |
| --- | --- | --- | ---: |
| 1.1 | Chur WiFi | PASS | 1 |
| 1.2 | Zurich HB platforms | PASS | 9 |
| 1.3 | Graubunden waiting halls | LIVE-DATA DIFFERENCE | 2 |
| 1.4 | Actual Bern categories | LIVE-DATA DIFFERENCE | 4 |
| 1.5 | 2024 DTV over 50000 | PASS | 12 |
| 1.6 | Non-stop from Bern | LIVE-DATA DIFFERENCE | 9 |
| 1.7 | Long-distance without WiFi (open world) | PASS | 0 |
| 2.1 | Ticino WiFi | PASS | 3 |
| 2.2 | Bern platforms over 320 m | PASS | 7 |
| 2.3 | Zurich HB track 3 sectors | PASS | 7 |
| 2.4 | Bern canton planned new waiting halls | PASS | 11 |
| 2.5 | Zurich canton waiting halls planned for demolition | PASS | 8 |
| 2.6 | Line 900 DTV in 2024 | PASS | 4 |
| 3.1 | Graubunden junctions and lines | PASS | 5 |
| 3.2 | Busy in 2025 but not in 2018 | PASS | 6 |
| 3.3 | Non-stop long-distance destinations from Zurich HB | LIVE-DATA DIFFERENCE | 19 |
| 3.4 | Actual TGV stations | LIVE-DATA DIFFERENCE | 5 |
| 3.5 | Train/tram interchanges | PASS | 6 |

Question 1.7 returns **UNKNOWN**, with no bindings; this is its intended result,
not evidence that there are zero stations without WiFi. Long-distance membership
is populated, so the check is not vacuously passing on an empty class.

Question 1.3 returns Chur and Maienfeld. In the cached source Landquart has two
`PROJEKTIERT ABBRUCH` halls and no `BESTEHEND` hall. The canonical rule requires
`BESTEHEND`; no status or reference answer was fabricated. Sedrun SMF inventory
rows are outside the scoped passenger-station set. The train source covers
2026-09-28, while the supplied reference date is 2026-09-27.

## Performance

- Full initialization/load: **50.97 s**; main smoke run: **50.19 s**.
- Total materialized facts: **860,536**, including **152,575 derived facts**.
- Inference: **277,896 rule firings**, **13 rounds**, fixed point reached.
- Events: **69,798**; actual stops: **68,416**; journeys: **5,781**.
- Query latency across the 18 cases: **0.42-6.18 ms**, one measurement each.
- Generated facts: **42,437,066 bytes (40.47 MiB)**.
- Cached preparation: about 2 seconds; trains about 1.79 seconds.
- Approximate observed engine working set during diagnostics: 2.25 GB.

These figures describe this workstation and snapshot, not a throughput guarantee.
See [scalability.md](scalability.md) for the original error and measured fix.

## Reproduce the final smoke run

```powershell
$env:PYTHONPATH = "src"
$env:FRAMEX_BINARY = "C:\Users\Levashenko\bin\framex.exe"
uv sync
uv run -m unittest discover -s tests -v
uv run -m unittest discover -s tests/integration -v
uv run -m acceptance
uv run src/main.py --stats --validate --demo chur-wifi --query '?- station_8509000:StopPoint.' --explain 'platform_35292761:LongPlatform'
uv run -m package_submission
```

The sandboxed session used `UV_CACHE_DIR=.uv-cache` for uv's cache location.
The ZIP includes offline fact snapshots; raw API caches and the engine executable
are excluded. Obtain FrameX via the course/Workbench distribution and set your own
binary path if different. Update the model declaration and recreate the archive
before submitting it.

## Remaining limits and next hackathon

56 invalid-schedule source rows are reported and omitted; links for 10 uncertain
journeys are withheld. Six WiFi rows lack BPUIC. Unknown source fields are never
replaced by guessed values. Scheduled order is not a real-time travel guarantee.
Full cache refreshes are separate snapshots, not historical query support.

For Hackathon 2, start with immutable, versioned snapshot manifests and explicit
source/as-of provenance for every dataset. This provides a sound base for temporal
questions and prevents unintentionally mixing operating days on future refreshes.
