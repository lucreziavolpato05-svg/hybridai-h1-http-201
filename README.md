# Https201 — Derive From Knowledge

## Team

| Member | Role |
| --- | --- |
| Wee Siang | Developer |
| Ethan | Developer |
| Lucrezia Volpato | Domain Expert |
| Egor Levashenko | Auditor |

## Project overview

Https201 is a knowledge-based Swiss rail reasoning system. It downloads and
caches selected SBB Open Data datasets, normalizes each source into base F-logic
facts, and combines them with `ontology.fx` in FrameX. The ontology, rather than
application code, derives facts such as long platforms, train/tram interchanges,
and WiFi-equipped stations. Once the local fact files have been prepared, all
queries run offline against the local ontology and facts.

Eight sources are integrated: platform lengths, DiDok service points, WiFi, train
events, waiting halls, passenger frequencies, line memberships, and sector boards.
Raw API snapshots are cached locally and excluded from Git.

## Coding agents and models

The team used **Claude** and **Codex** as coding agents/models for implementation
and documentation support. Team members review the resulting code, ontology,
tests, and documentation before accepting changes.

## AI-assisted development

Tool: OpenAI Codex in VS Code.
Model: **MODEL_NAME_TO_FILL_IN_BEFORE_SUBMISSION** (exact model not yet confirmed).
The team's existing Claude/Codex declaration above is preserved. Fill in the exact
model from the development tool before submission; do not infer it from a brand name.

## Architecture and symbolic reasoning

```text
SBB Open Data -> connector.py -> data/raw/<dataset>/ JSON snapshots
              -> explicit dataset adapter -> data/<dataset>.fx BASE facts
ontology.fx + all eight fact files -> one FrameX bulk load
                                  -> DERIVED facts -> offline queries/explanations
```

`src/main.py` delegates to `query.py`. `src/framex.py` is the supplied local
subprocess client. Python normalizes source data and orders event calls; FrameX
performs all derived reasoning. After preparation, neither query nor acceptance
execution needs an internet connection or an LLM.

Base classes include StopPoint, Platform, SectorBoard, WaitingHall, Line, Journey,
and StopEvent. Rules derive LongPlatform (>320 m), Junction (two distinct lines),
Interchange (train + tram), busyIn(year) (>20,000 DTV), LongDistanceStation,
WellEquippedStation, actual stops, non-stop links, one-change links, and BigHub.
For example, a platform's `structuralLengthM` is a base fact; `LongPlatform` is
inferred. A train's cancellation/pass-through flags and `nextStop` are base facts;
`actuallyStops` and `nonStopTo` are inferred.

The canonical ontology uses **`world open.`**: missing information is UNKNOWN.
The WiFi inventory asserts only positive availability. No row never means
`hasWifi -> false`; official question 1.7 correctly returns UNKNOWN.

All adapters join on **`station_<full UIC/BPUIC>`**, never station names. DiDok
owns canonical designations. Platform compatibility properties `station`, `number`,
and `structuralLengthM` are preserved. Only explicitly typed `LegacyNamedStation`
fixtures use the legacy name-to-designation alias, avoiding spelling conflicts.
Passenger years are consistently **strings**, e.g. `observedFrequency("2024")`.

## Datasets and snapshot

Source links below identify the exact SBB dataset. Counts describe the cached
snapshot, not constants enforced by ingestion.

| Preparation name / source | Emitted evidence | Normalized records |
| --- | --- | ---: |
| `platforms` / [perron](https://data.sbb.ch/explore/dataset/perron/) | Physical platforms, structural length | 1,570 |
| `service_points` / [DiDok](https://data.sbb.ch/explore/dataset/dienststellen-gemass-opentransportdataswiss/) | Active Swiss passenger rail stops, canton, modes, designation | 1,773 |
| `wifi` / [wifistation](https://data.sbb.ch/explore/dataset/wifistation/) | Positive WiFi evidence | 73 |
| `stop_events` / [ist-daten-sbb](https://data.sbb.ch/explore/dataset/ist-daten-sbb/) | Dated journeys, flags, categories, chronological nextStop | 69,798 |
| `waiting_halls` / [haltestelle-wartehallen](https://data.sbb.ch/explore/dataset/haltestelle-wartehallen/) | Installation identity, station, exact status | 939 |
| `passengers` / [passagierfrequenz](https://data.sbb.ch/explore/dataset/passagierfrequenz/) | DTV (`dtv_tjm_tgm`), including 2018/2024/2025 | 5,724 |
| `lines` / [linie-mit-betriebspunkten](https://data.sbb.ch/explore/dataset/linie-mit-betriebspunkten/) | Station memberships and source line-number labels | 923 |
| `sector_boards` / [sektortafel](https://data.sbb.ch/explore/dataset/sektortafel/) | Source FID, customer track number, front sector | 5,364 |

Line memberships are filtered from 1,892 infrastructure operation points through
the scoped DiDok station set, excluding freight/signal markers. The source's
`linie` field supplies official numeric line labels (including 900); no separate
route-network import is needed for the requested queries.

Train facts cover **28 September 2026**, whereas the reference sheet uses
27 September. `--as-of` controls DiDok validity only; it does not retrieve an
old API snapshot. Reusing the generated facts/cache preserves these results.
`--refresh` downloads the then-current data, so train answers can change daily.
Full trains use the JSON export endpoint, with before/after count verification,
rather than silently truncating at the records endpoint's 10,000-row ceiling.

## Installation

Use Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Obtain the FrameX binary from your course/FrameX-Workbench distribution, following
[FrameX's local setup instructions](https://unisg-ics-dsnlp.github.io/FrameX-Doc/python/installation.html).
This project was verified with **FrameX 0.4.3**. The engine is separate from the
Python environment; do not install the unrelated PyPI package named `framex`.

Run every command below from the **repository root**, not `src/`:

```powershell
uv sync
$env:PYTHONPATH = "src"
$env:FRAMEX_BINARY = "C:\Users\Levashenko\bin\framex.exe" # use your own installation path
```

Alternatively put `framex` on PATH or pass `--binary <path>`. The query/main and
acceptance commands honor `FRAMEX_BINARY`. On macOS/Linux use `export PYTHONPATH=src`
and `export FRAMEX_BINARY=/path/to/framex`. No third-party Python dependencies
are needed. Do not run `uv init` again in this existing project.

## Prepare or reuse local facts

```powershell
# Reuse snapshots when present; download only missing sources.
uv run -m ingestion.prepare --as-of 2026-09-29 --report docs/preparation-results.json

# Prepare selected sources (didok remains an alias for service_points).
uv run -m ingestion.prepare --datasets waiting_halls passengers lines sector_boards

# Explicitly replace the previous-day train snapshot when desired.
uv run -m ingestion.prepare --datasets stop_events --refresh
```

All adapters share `data/raw/` but have separate request-specific caches. Use
`--raw-dir` and `--output-dir` to change locations. `--limit` is available for
other datasets; train preparation refuses it because partial journeys can create
false non-stop links. The legacy platform-only `ingestion.ingest` command and
its incremental `client.add` API remain available; see [data-pipeline.md](docs/data-pipeline.md).
Refreshing cache does not retract facts from an existing engine session. Start
a fresh combined query session after regenerating files.

The submission ZIP includes the eight generated fact files for a reproducible,
offline demo. Preparation is optional when those files already exist. Ignore
rules prevent new generated artifacts being accidentally added; several fact
files were already tracked by the team and are deliberately retained.

## Demo, queries, validation and explanations

```powershell
# Real SBB application; loads all eight datasets and runs the built-in demos.
uv run src/main.py --stats

# Submit an arbitrary query. Repeat --query to reuse one loaded session.
uv run -m query --query '?- station_8509000[hasWifi -> true].'

# Validate the full world and demonstrate open-world negation.
uv run -m query --validate --stats --demo open-world-wifi

# Show actual engine proofs from this snapshot.
uv run -m query --explain 'platform_35292761:LongPlatform' --explain 'station_8509000:Junction' --explain 'station_8500010:LongDistanceStation' --explain 'station_8507000[nonStopTo -> station_8500218]'
```

Queries use `?-`, variables prefixed by `?`, and a final period. Objects are
unquoted; literal names and years are double-quoted within the PowerShell string.
`--facts <files...>` and `--ontology <file>` select alternative local inputs.
The default full load takes about a minute on the tested workstation. Multiple
queries in one invocation avoid repeated initialization.

The application uses a measured `--max-proofs 1000000` budget and a configurable
`--request-timeout 180` seconds per request. The 64 MiB response allowance permits
full validation. See [scalability.md](docs/scalability.md) for the reproduced
failure, ablation checks, memory observation, and rationale. No rules or
constraints were removed to avoid the original proof-limit failure.

## Tests and official acceptance

```powershell
uv run -m unittest discover -s tests -v
uv run -m unittest discover -s tests/integration -v
uv run -m acceptance --output docs/acceptance-results.json
```

Unit tests are offline and need no engine. Integration tests use synthetic facts
and require FrameX; without it they report SKIPPED, not passed. Acceptance uses
the complete local snapshot and one engine session. It checks all 18 questions,
source-event witnesses, same-journey chronological links, cancellation and
pass-through behavior, typed years, validation, and four actual explanations.
A runtime failure or semantic failure returns a nonzero exit code.

Latest complete acceptance: **18/18 supported; 13 PASS, 5 LIVE-DATA DIFFERENCE,
0 FAIL, 0 NOT IMPLEMENTED**. Four differences are train questions on a newer day.
Question 1.3 returns Chur and Maienfeld: Landquart's source halls are
`PROJEKTIERT ABBRUCH`, whereas `hasWaitingHall` requires `BESTEHEND`.
Reference answers are comparison expectations only, never facts or returned
answers. Questions without a supplied exact historical answer are checked for
execution and current evidence; this is not a claim of exact historical equality.

See [verification.md](docs/verification.md) for the 18-row coverage table,
[acceptance-results.json](docs/acceptance-results.json) for every actual binding,
proof and runtime check, and [preparation-results.json](docs/preparation-results.json)
for per-dataset preparation timings and byte sizes.

## Performance and limitations

The final full world contains **860,536 facts** and 69,798 events. A measured
acceptance load took **50.97 seconds**; the 18 question evaluations took roughly
**0.4-6.2 ms each**. Generated facts occupy about **40.5 MiB**. Cached preparation
takes about **2 seconds**, including 1.79 seconds for trains. These are local
measurements; cold network download time was not remeasured. The diagnostic
engine working set reached approximately 2.25 GB.

- Zero reported validation violations does not certify completeness under an
  open world. Missing required source values remain UNKNOWN and are reported.
- Six WiFi records lack a joinable BPUIC; they are reported and omitted.
- 56 train rows have invalid operating-day schedules. Links for 10 uncertain
  journeys are withheld to prevent invented non-stop legs. Unknown flags never
  become false. Foreign calls remain event-chain barriers.
- Scheduled timestamps determine within-journey order. This is observed-service
  reasoning, not a real-time journey planner or a guarantee of future service.
- Platform length means structural length, not necessarily usable boarding length.
- Waiting-hall source rows lack an installation ID; a deterministic content hash
  identifies each row. Changing content can change that ID on refresh.
- The exact coding-model declaration remains a manual pre-submission action.

## Clean submission ZIP

```powershell
uv run -m package_submission
```

This creates and integrity-checks `dist/sbb-framex-submission.zip`, including code,
tests, ontology, docs and the eight fact snapshots. It excludes `.git`, virtual
environments, raw caches, bytecode, temporary files, and the separately installed
engine. The working repository is preserved. Fill the model declaration before
creating the final archive for submission.
