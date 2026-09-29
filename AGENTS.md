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
  in the tested FrameX binary; use string years in the final acceptance contract, e.g. `observedFrequency("2024")`.

## Code map

| Location | Responsibility |
| --- | --- |
| `src/ingestion/connector.py` | Generic `fetch_dataset_records`; compatible platform `fetch_records` wrapper; request-specific cache |
| `src/ingestion/normalizer.py`, `emiter.py` | Existing platform adapter; retain the `emiter.py` spelling/interface |
| `src/ingestion/ingest.py` | Platform CLI and incremental `ingest_platforms(client, ...)` using `client.add` |
| `src/ingestion/didok.py` | Swiss passenger-rail DiDok normalization and base-fact emission |
| `src/ingestion/wifi.py` | Positive WiFi inventory evidence; warns/skips missing BPUIC |
| `src/ingestion/stop_events.py` | Complete dated journeys; chronological base edges; conservative handling of unsafe calls |
| `src/ingestion/waiting_halls.py`, `passengers.py`, `lines.py`, `sector_boards.py` | Explicit remaining source adapters; string year DTV; source line-number labels |
| `src/acceptance.py` | All 18 official queries, semantic checks, four real explanations, performance/validation JSON |
| `src/package_submission.py` | Allowlisted, integrity-checked offline ZIP |
| `src/ingestion/identity.py` | Full-UIC validation and shared station identifier |
| `src/ingestion/prepare.py` | Prepare eight datasets; scope train/line station links through DiDok; optional JSON timing report |
| `src/query.py` | Offline combined loading, demos, arbitrary queries, explanations, validation summary |
| `src/framex.py` | Canonical local subprocess client; do not install the unrelated PyPI `framex` package |
| `src/main.py` | Thin entry point delegating to the real SBB query application |
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

Preparation accepts `--datasets` (`platforms`, `service_points`, `wifi`,
`stop_events`, `waiting_halls`, `passengers`, `lines`, `sector_boards`; `didok`
remains an alias), `--limit` (not for trains), `--refresh`, `--report`, and
`--as-of YYYY-MM-DD`.
The default validity date is today; `--as-of` filters DiDok validity, not the API's
historical state. A small sample may omit named demo stations. The query CLI
accepts `--binary`, `--ontology`, `--facts`, and repeatable `--query`/`--demo`/
`--explain`, plus `--stats`, `--max-proofs` (default 1,000,000), and
`--request-timeout` (default 180 seconds). `FRAMEX_BINARY` is honored.
The example explanation ID is from the inspected snapshot. Run `uv run -m
acceptance` for the complete regression and `uv run -m package_submission` for
an offline ZIP.

Raw snapshots live under `data/raw/`. Generated outputs are `data/platforms.fx`,
`data/service_points.fx`, `data/wifi.fx`, and five matching adapter outputs.
Ignore rules cover generated files; already-tracked teammate snapshots are
retained. The ZIP deliberately includes all eight `.fx` files for offline use.
If the sandbox blocks network or temporary test-directory access, request the
required execution permission; do not weaken tests or bypass restrictions.

## Current progress

Last updated: **2026-09-29**. Full evidence is in
[verification.md](docs/verification.md), [acceptance-results.json](docs/acceptance-results.json),
and [scalability.md](docs/scalability.md). Counts are snapshot observations.

- Eight adapters are implemented and prepared from cache: 1,570 platforms,
  1,773 DiDok stops, 73 WiFi stations, 69,798 train events, 939 waiting halls,
  5,724 DTV observations, 923 scoped line memberships and 5,364 sector boards.
- Trains cover **2026-09-28**: 5,781 journeys, 63,930 chronological links,
  68,416 actual stops. No cross-journey or multiple-successor edges were found.
- The proof-limit issue was reproduced during bulk inference. Base-only and
  single-rule diagnostics pass; the full world reaches a fixed point with a
  finite configurable 1,000,000-proof budget. Transport remains unchanged.
- Full world: **860,536 facts**, **152,575 derived facts**, **277,896 rule firings**,
  **13 rounds**. Acceptance load **50.97 s**; query evaluations **0.42-6.18 ms**.
- Final verification in this session: **67 unit tests and 17 engine integration
  tests passed**. `uv sync`, main/demo, arbitrary query, stats, explanation,
  complete validation and acceptance all ran successfully.
- Official coverage: **18/18 supported; 13 PASS, 5 LIVE-DATA DIFFERENCE, zero
  FAIL / NOT IMPLEMENTED**. Four differences are train-source date changes.
  Graubunden waiting halls differ because Landquart's halls are planned for
  demolition rather than BESTEHEND. No historical answers were inserted.
- Four actual engine explanations trace LongPlatform, Junction,
  LongDistanceStation and nonStopTo to rules and asserted facts.
- Source-name conflicts are resolved: DiDok owns designation; only explicitly
  typed LegacyNamedStation fixtures derive it from legacy names.
- Line ingestion scopes operation points through DiDok, preventing freight or
  infrastructure markers from becoming station Junctions.
- Next work: fill the README model declaration before submission. For Hackathon 2,
  prefer versioned snapshot manifests and explicit temporal provenance.

### Known issues and limits

- **Zero reported violations**, but **68 unknown required-field checks** remain:
  seven missing platform lengths and 61 canonical station names. Seven constraint
  bodies are UNKNOWN in open-world validation, not certified globally consistent.
- Six WiFi rows lack BPUIC. 56 train rows have invalid schedules; links for 10
  uncertain journeys are withheld, so missing calls cannot create false legs.
  Missing flags remain unknown; foreign calls remain chain barriers.
- Train order is scheduled source-local order, not a real-time routing guarantee.
  Passenger years are strings (`"2024"`); numeric arguments are different terms.
- `query --validate` now exits nonzero for reported violations. Full validation
  needs more than the client's default 8 MiB response cap; application sessions
  use 64 MiB. Full load needs about a minute and roughly 2.25 GB observed engine
  working set; do not assume the budget fits unlimited historical data.
- Bulk source exports support full trains beyond 10,000 rows; ordinary record
  pagination still refuses silent truncation. Cached preparation was measured;
  cold network download duration was not remeasured in the final session.
- `client.add` is additive. Replace snapshots in a fresh combined session.
- Exact coding-model name is not verified. Preserve
  `MODEL_NAME_TO_FILL_IN_BEFORE_SUBMISSION` until the team supplies it.

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

### 2026-09-29 - Full Hackathon 1 finalization and scalability verification

- Inspected clean HEAD `80433e5`, repository code/docs/tests and all eight caches.
  Baseline was 53 unit tests with one obsolete three-source orchestration failure,
  plus 15 passing engine tests. Reproduced the default proof-limit failure and
  used base-only/rule-ablation diagnostics before selecting a bounded budget.
- Added configurable full-world runtime limits, FRAMEX_BINARY support, validation
  failure exit status, dataset timings, 18-query acceptance, proof checks and ZIP
  packaging. Fixed arbitrary conflicting-event selection and scoped infrastructure
  line points through DiDok. Preserved all ontology rules and the platform API.
- Final checks: 67 unit and 17 engine integration tests pass; setup/main/query/
  explanation/stats/validation work. Full acceptance is 13 PASS + 5 live-data
  differences, no failures, zero validation violations. Required missing fields
  remain visible as 68 UNKNOWN checks. Whitespace validation passed.
- Updated README and historical handoff pointers; generated reproducible JSON
  evidence. No commits, pushes or resets. Model declaration remains manual;
  recreate the clean ZIP after filling it. Next: snapshot/version provenance for
  Hackathon 2. The final archive includes local generated facts, not raw caches.
