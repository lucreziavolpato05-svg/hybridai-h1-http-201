# Project instructions and working handoff

These instructions apply to the whole repository. Keep this file current using
the end-of-run procedure below. Explicit user instructions take precedence.

## Start here

1. Read this file, then inspect `git status --short`, `git diff`, and recent
   commits. Uncommitted work may belong to teammates; do not assume HEAD describes
   the current implementation.
2. Read the modules and tests affected by the task, plus
   [reasoning-demo.md](docs/reasoning-demo.md) for current integration details.
   For ingestion/ontology work, also read [ontology.fx](ontology.fx),
   [ontology-handoff.md](docs/ontology-handoff.md), and
   [data-pipeline.md](docs/data-pipeline.md).
3. Before code or ontology changes, run the existing unit suite and relevant
   integration tests to establish a baseline. Distinguish pre-existing failures
   from failures introduced by the change.
4. Recheck changed files before editing: multiple teammates may be working
   concurrently. Prefer small patches and isolated dataset adapters.

## Collaboration rules

- Do not reset, revert, delete, rename, or broadly rewrite unrelated work.
- Do not overwrite teammate changes, including untracked files and handoff notes.
- Preserve working interfaces unless the requested task requires a change.
- Do not commit or push unless explicitly asked.
- Keep generated fact files and raw caches out of commits. Do not remove local
  snapshots just to clean the working tree.
- Inspect the live API schema before adding a dataset; do not guess field names.
  Use cached data and synthetic fixtures for normal tests.
- Report unresolved data/ontology problems honestly. Passing tests does not mean
  all live data passes ontology validation.

## Semantic contract

This is an HSG Hybrid AI Hackathon reasoning system, not only a database lookup:

```text
SBB API -> download/cache -> dataset-specific normalization -> BASE F-logic facts
        -> existing ontology + declarative rules -> DERIVED facts -> queries/explanations
```

- `ontology.fx` is the single canonical ontology. Extend it minimally; do not
  create a competing ontology or move derived reasoning into Python.
- Keep `world open.`. Missing evidence means UNKNOWN, never automatically false.
  In particular, missing WiFi rows must not produce `hasWifi -> false`.
- Once local facts are prepared, answering queries must use FrameX only: no LLM,
  internet, or external lookup during query execution.
- Use `station_<full UIC/BPUIC>` across datasets. DiDok `number`, WiFi `bpuic`,
  and platform `bpuic` join to the same object. Never join by display name or guess
  a full UIC from a short DiDok code. Preserve the existing platform fallback
  behavior unless deliberately changing that interface.
- Preserve platform properties `station`, `number`, and `structuralLengthM`.
  Existing ontology rules derive `atStopPoint`, `platformNumber`, and
  `platformLength`. Structural length is not necessarily usable boarding length.
- Normalize each dataset explicitly. Do not introduce a universal JSON-to-facts
  mapper, universal normalizer, or ontology generator.
- Do not hardcode expected station answers. Named stations in demo queries are
  query inputs; results must come from facts and rules.
- Method arguments are typed: `2025` and `"2025"` are different values. Both work
  in the tested FrameX binary; prefer numeric years for future frequency data.

## Code map

| Location | Responsibility |
| --- | --- |
| `src/ingestion/connector.py` | Generic `fetch_dataset_records`; compatible platform `fetch_records` wrapper; request-specific cache |
| `src/ingestion/normalizer.py`, `emiter.py` | Existing platform adapter; retain the `emiter.py` spelling/interface |
| `src/ingestion/ingest.py` | Platform CLI and incremental `ingest_platforms(client, ...)` using `client.add` |
| `src/ingestion/didok.py` | Swiss passenger-rail DiDok normalization and base-fact emission |
| `src/ingestion/wifi.py` | Positive WiFi inventory evidence; warns/skips missing BPUIC |
| `src/ingestion/identity.py` | Full-UIC validation and shared station identifier |
| `src/ingestion/prepare.py` | Prepare the three datasets as local fact files |
| `src/query.py` | Offline combined loading, demos, arbitrary queries, explanations, validation summary |
| `src/framex.py` | Canonical local subprocess client; do not install the unrelated PyPI `framex` package |
| `src/main.py` | Small existing example; keep it free of large dataset-specific orchestration |
| `tests/test_*.py` | Offline unit tests, no engine required |
| `tests/integration/test_ontology.py` | Separate synthetic offline tests requiring the real engine |

The old `download.py`, `clean.py`, `normalize.py`, `facts.py`, `pipeline.py`, and
`src/sbb_data.py` were retired. Do not restore a second ingestion pipeline.

## Commands

Run from the repository root with Python 3.12 and `uv`. No third-party Python
dependencies are currently needed. On this workstation FrameX was verified at
`C:\Users\Levashenko\bin\framex.exe`; other machines should use their own path.

```powershell
$env:PYTHONPATH = "src"
$env:Path += ";C:\Users\Levashenko\bin"

# Offline unit tests.
uv run --python 3.12 -m unittest discover -s tests -v

# Separate offline integration tests. Skipped without an engine on PATH or this variable.
$env:FRAMEX_BINARY = "C:\Users\Levashenko\bin\framex.exe"
uv run --python 3.12 -m unittest discover -s tests/integration -v

# Prepare facts: uses cache when present; otherwise downloads missing snapshots.
uv run --python 3.12 -m ingestion.prepare

# Query local files only; optionally print validation diagnostics or explanations.
uv run --python 3.12 -m query
uv run --python 3.12 -m query --validate --demo open-world-wifi
uv run --python 3.12 -m query --explain 'platform_35292761:LongPlatform'

git diff --check
```

Preparation accepts `--datasets` (`platforms`, `service_points`, and `wifi`;
`didok` remains an alias), `--limit`, `--refresh`, and `--as-of YYYY-MM-DD`.
The default validity date is today; `--as-of` filters DiDok validity, not the API's
historical state. A small sample may omit named demo stations. The query CLI
accepts `--binary`, `--ontology`, `--facts`, and repeatable `--query`/`--demo`/
`--explain`. The example explanation ID is from the inspected snapshot.

Raw snapshots live under `data/raw/`. Generated outputs are `data/platforms.fx`,
`data/service_points.fx`, and `data/wifi.fx`. These files are ignored by Git.
If the sandbox blocks network or temporary test-directory access, request the
required execution permission; do not weaken tests or bypass restrictions.

## Current progress

Last updated: **2026-09-29**. Counts below are observations from the inspected
snapshots and previous verification, not expected constants for future tests.

- Implemented: platforms (`perron`), scoped Swiss passenger-rail DiDok
  (`dienststellen-gemass-opentransportdataswiss`), and WiFi (`wifistation`).
- Verified snapshot: 1,570 platforms, 1,773 DiDok points, 73 joinable WiFi stations
  out of 79 inventory rows. Six missing-BPUIC rows are reported and skipped.
- Ontology fixes: cancelled intermediate events can be skipped in non-stop
  chains; IC, IR, EC, ICE, TGV, NJ, RJX category seeds are present.
- Last code verification: **42 unit tests and 14 real-engine integration tests
  passed** on 2026-09-29.
  Tests cover joins, thresholds, cancellation, missing values, positive-only
  WiFi, open-world negation, and rule explanations.
- Live query coverage: Chur WiFi, Zürich HB platforms/lengths, Bern long platforms,
  Ticino/WiFi joins, and train/tram Interchange. Open-world WiFi behavior is tested.
- Remaining adapters: waiting rooms, sector boards, dated train-stop events,
  passenger frequencies, line operation points, and route identity mappings.
- Recommended next feature: dated StopEvent ingestion to unlock actual categories,
  TGV service, LongDistanceStation and non-stop destinations. Keep event identity
  and `nextStop` ordering scoped to one journey and operating date.

### Known issues and limits

- **Live validation is not clean.** Platform and DiDok station spellings differ,
  including accents. The existing name-to-designation compatibility rule yields
  298 functional-designation violation facts in the inspected snapshot; seven
  schema checks are unresolved. Do not silently remove names or constraints to
  hide this. A coordinated authoritative-name policy is still needed.
- `query --validate` reports diagnostics; its exit code is not a guarantee of
  clean validation. Use `client.validate()` for the complete report.
- Live StopEvent data is not yet ingested. Non-stop/category/long-distance rules
  are covered with synthetic facts. The live negative-WiFi demo also lacks
  long-distance membership evidence; the synthetic test checks a known member.
- Generic download supports the records endpoint's 10,000-row window and fails
  rather than silently truncating larger results. The scoped DiDok filter fits;
  the full unfiltered dataset would require export support or a narrower scope.
- `client.add` is additive; refreshing a cache does not retract old session facts.
  Use a fresh combined session when replacing snapshots.

## Required end-of-run update

After **every user-requested repository work session**, before the final response:

1. Re-read this file and current git status to preserve concurrent teammate edits.
2. Update `Current progress` and `Known issues and limits` when the implementation,
   verification evidence, supported queries, or next step changed.
3. Append a concise dated entry to `Run log` with: task, files/behavior changed,
   checks actually run and their results, remaining issues, and next step.
4. Distinguish checks run in this session from earlier evidence. For documentation-
   only work, check the diff and links/commands as appropriate and state that
   executable tests were not rerun. Never imply skipped tests passed.
5. Keep entries short and factual. Do not include secrets, raw datasets, or full
   tool transcripts. Do not rewrite or discard another agent's log entries.
6. Mention the progress update in the final response. If the user explicitly
   requested read-only work or no edits, honor that and report the pending update
   instead of modifying this file.

Here, a run means an agent work session, not every shell command or invocation of
the ingestion app. This is a required handoff procedure, not a background hook.

## Run log

### 2026-09-29 — Ontology validation and DiDok/WiFi integration (prior session)

- Added typed DiDok/WiFi adapters, reusable connector, shared UIC identity,
  preparation and offline query harness. Preserved the platform API and client.
- Added seven category seeds and one cancelled-event skip rule to `ontology.fx`.
- Verification: 40 unit tests and 14 real-engine integration tests passed; live
  preparation, five demos, and a derived-rule explanation worked. Documentation
  and cache ignores were updated; no commits were made.
- Open: missing WiFi IDs, source-name constraint conflicts, and remaining adapters.
  Next feature: dated StopEvent ingestion.

### 2026-09-29 — Agent handoff and progress-update procedure

- Added root `AGENTS.md` with collaboration rules, semantic contracts, code map,
  commands, current evidence, known issues, and the mandatory end-of-run update.
- Checked current git status/history and the existing integration guide; preserved
  all pre-existing uncommitted changes. Documentation-only change: executable
  tests were not rerun; the 40/14 counts above belong to the prior session.
- Verification: reviewed the new file, local link targets, and whitespace checks.
  Open issues and the recommended next feature remain unchanged.

### 2026-09-29 — Configurable initial dataset preparation and query guide

- Replaced the preparation CLI's dataset branches with a registry for platforms,
  service points, and WiFi. All selected sources share `data/raw/`; their caches
  are reused unless `--refresh` is requested. `service_points` is the canonical
  CLI name and `didok` remains a compatible alias.
- Expanded README with one-time local setup/cache behavior and copyable custom
  F-logic query examples. Updated the reasoning guide's canonical dataset name.
- Verification this session: `PYTHONPATH=src uv run --python 3.12 -m unittest
  discover -s tests -v` passed **42 tests** and the separate integration suite
  passed **14 real-engine tests**; `python -m ingestion.prepare --help` shows
  the canonical dataset choices; `git diff --check` passed. No live API request
  was run.
- Open: the existing live source-name validation conflicts and remaining adapters.
  Next feature remains dated StopEvent ingestion.

### 2026-09-29 — Team and reproduction README details

- Added the Https201 team name, member roles, project overview, coding-agent
  disclosure, and a concise reproducible setup/run sequence to the README.
- Documentation-only update: reviewed the Markdown sections and commands and ran
  `git diff --check`; executable tests were not rerun. Live snapshots remain
  necessary for identical live-data results because `--as-of` is not a historical
  API snapshot selector.
- Open: the existing live source-name validation conflicts and remaining adapters.
  Next feature remains dated StopEvent ingestion.
