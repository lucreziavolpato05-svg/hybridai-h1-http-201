# Team Takeover Checklist

> This is the earlier integration checklist. For the completed eight-dataset
> system, current tests, proof-budget diagnosis and next steps, read the root
> [AGENTS.md](../AGENTS.md) and [verification.md](verification.md) first.

Read this before extending the API ingestion or pushing the next integration.

## Current state

- `ontology.fx` contains the shared ontology and derived FrameX rules.
- `docs/ontology-handoff.md` defines the API-to-ontology fact contract.
- `src/framex.py` is the repository's canonical Python client for the FrameX binary.
- The current API implementation supports platforms, scoped Swiss passenger-rail DiDok service points, and positive Wifi@Station evidence.
- The remaining reference-query datasets still need ingestion: waiting rooms, sector boards, departure/arrival events, passenger frequencies, lines, and route network data.
- [reasoning-demo.md](reasoning-demo.md) records offline demo commands, ontology tests, missing WiFi IDs, and functional name conflicts between sources.
- Generated files under `data/` are ignored and must not be committed as source changes.

## Non-negotiable fact contract

Use stable full UIC/BPUIC identifiers, matching the existing platform pipeline:

```text
station_8503000:StopPoint.
station_8503000[designation -> "Zürich HB"].
```

Use these canonical facts for the remaining datasets:

```text
station_8503000[inCanton -> canton_zh].
station_8503000[servesMode -> mode_train].
station_8503000[hasWifi -> true].

platform_1:Platform.
platform_1[atStopPoint -> station_8503000].
platform_1[platformNumber -> "10/11"].
platform_1[platformLength -> 425.0].

waitinghall_1:WaitingHall.
waitinghall_1[atStopPoint -> station_8503000].
waitinghall_1[status -> "BESTEHEND"].

station_8503000[observedFrequency(2024) -> 410700.0].
line_900:Line.
line_900[label -> "900"].
station_8503000[servedByLine -> line_900].

event_1:StopEvent.
event_1[atStopPoint -> station_8503000].
event_1[category -> "IC"].
event_1[cancelled -> false].
event_1[passesThrough -> false].
event_1[nextStop -> event_2].
```

Object references must be unquoted. Quote names, categories, statuses, and
platform numbers. Lengths, passenger counts, and years must be numeric. In this
FrameX version, integration tests confirm both numeric and string method arguments
work, but facts and queries must use the same type. Prefer numeric years for
future passenger-frequency ingestion.

The existing `perron` emitter uses `station`, `number`, and
`structuralLengthM`. `ontology.fx` contains aliases for those fields, so do not
remove the aliases unless the emitter is deliberately migrated to the canonical
names.

## Reasoning policy

- Keep the combined program `world open.`.
- Missing SBB records mean unknown, not false.
- Do not emit negative facts merely because a dataset has no row.
- Query 1.7 is expected to return `unknown` for missing WiFi.
- Treat the previous-day event dataset as a dated snapshot; record its operating
  date and do not compare it blindly with another day.
- Do not change ontology rules to compensate for missing API facts. Fix the
  ingestion mapping first.

## Validation before push

From the repository root:

```powershell
$env:PYTHONPATH = "src"
uv run --python 3.12 -m ingestion.ingest --limit 100 --refresh --dry-run
framex check ontology.fx data/platforms.fx
framex validate ontology.fx data/platforms.fx
framex run ontology.fx data/platforms.fx --stats
uv run --python 3.12 -m unittest discover -s tests -v
```

For every newly supported dataset, add at least one known-answer query and
compare its entities and values with the supplied reference answers. Do not
require generated internal IDs to match the reference system; station identity,
values, and query semantics must match.

## Files and ownership

- API download, caching, normalization: `src/ingestion/`
- Ontology and rules: `ontology.fx`
- FrameX transport: `src/framex.py`
- Data/API contract: `docs/ontology-handoff.md`
- Evaluation semantics: `docs/framex-integration.md`
- This takeover checklist: `docs/team-handoff.md`

Avoid rewriting another teammate's module during integration. Coordinate field
name or identifier changes through `docs/ontology-handoff.md` first.

## Commit and push

Review the diff and ensure no raw cache or generated data is staged:

```powershell
git status --short
git diff --check
git add ontology.fx docs/ docs/team-handoff.md src/
git diff --cached --stat
git commit -m "Integrate SBB ontology handoff"
git push
```
