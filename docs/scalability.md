# Full train snapshot: diagnosis and runtime limits

Verified with the locally installed FrameX 0.4.3 executable on 29 September 2026.
No engine source was available locally. The public Python documentation did not
specify numeric defaults for the new bulk-load inference limits; the installed
CLI help and `src/framex.py` expose `max_rounds`, `max_facts`, `max_matches`, and
`max_proofs`. The exact numeric engine default is therefore not asserted here.

## Reproduction before the runtime fix

From the root with `PYTHONPATH=src`, the previous application command was:

```powershell
uv run -m query --binary C:\Users\Levashenko\bin\framex.exe --facts data/platforms.fx data/service_points.fx data/wifi.fx data/stop_events.fx --demo chur-wifi
```

It failed with:

```text
InferenceError: proof limit reached; simplify alternatives or raise --max-proofs
```

The error came from inference during `load_commit`, after staging/parsing and
before querying, explaining, or validating. Loading is atomic: no partial world
was published. The current application supplies the measured budget below, so
that same command now succeeds. To reproduce engine defaults with current code:

```powershell
@'
from pathlib import Path
from framex import Client
from query import load_knowledge
with Client(request_timeout=180, retain_transcript=False) as client:
    load_knowledge(client, Path("ontology.fx"), [Path("data") / n for n in
        ("platforms.fx", "service_points.fx", "wifi.fx", "stop_events.fx")])
'@ | uv run python -
```

This diagnostic uses `framex` on PATH; supply `binary=...` if necessary.
`load_knowledge` deliberately retains its no-limit default for library callers.

## Measurements and cause

The train file contains 641,396 asserted facts: 69,798 events and 5,781 journeys,
including 63,930 `nextStop` edges. Audit found zero cross-journey edges, zero
multiple successors, and zero nonchronological edges. Complete export caching
avoids the records endpoint's 10,000-row ceiling. Identical calls are deduplicated.

Controlled diagnostics used the complete cached snapshot, without changing the
canonical ontology:

| Experiment | Observed outcome |
| --- | --- |
| Train base facts, no ontology | 641,396 facts loaded in 5.41 s; zero rule firings |
| All source facts, only `actuallyStops` rule | 68,416 derived facts/firings; 2 rounds; 14.98 s total |
| Full ontology except `oneChangeTo`, default limits | Proof-limit error after 12.22 s |
| Full ontology, default limits | Proof-limit error after 24.87 s |
| Full ontology, `max_proofs=1_000_000` | Fixed point: 279,250 firings, 153,136 derived facts, 13 rounds |

The successful diagnostic loaded all eight sources into 862,372 facts in 94.22 s
under concurrent work; a subsequent acceptance run took 52.68 s. This is a
finite proof-volume limit, not a parser/input-size error or an unbounded event
chain. Removing `oneChangeTo` alone does not solve it. Alternative trains supply
multiple legitimate witnesses for the same station category or non-stop link.
No derived semantics were moved to Python and no ontology rules were removed.

Further source inspection identified non-passenger infrastructure operation
points among line memberships. Preparation now joins these to the same scoped
DiDok station set as train events: 923 of 1,892 memberships remain. This prevents
freight/junction markers becoming station Junctions, independently of the proof
budget fix. Final counts/timings after this correction are in
[acceptance-results.json](acceptance-results.json).

## Runtime configuration

The application and acceptance runner use:

- `--max-proofs 1000000`: finite, configurable budget verified on this snapshot.
- `--request-timeout 180`: seconds per engine request, including bulk inference.
- 64 MiB response allowance: the full per-object validation report exceeds the
  client's default 8 MiB. The underlying transport/client is unchanged.
- One staged bulk transaction, inference once, transcript retention disabled.

The engine was observed around 2.25 GB peak working set during the diagnostic.
This is an approximate observation, not a continuously sampled memory benchmark.
Future larger snapshots may require remeasurement; do not assume these settings
fit unlimited history. Failure still propagates rather than returning partial
answers. `query --validate` exits nonzero on actual reported violations.

## Conservative source treatment

56 source rows have schedules outside their operating day/following midnight.
They are reported and omitted. Links for 10 uncertain journeys are withheld so
discarded calls cannot create false non-stop legs. Foreign/out-of-scope events
remain chain barriers but receive no Swiss `atStopPoint` link. Conflicting
duplicates are omitted entirely instead of choosing arbitrary cancellation flags.
Scheduled source-local timestamps determine order; forecast delays do not.

All official answers, event consistency checks, operating dates, input hashes,
engine statistics, and four unedited engine explanations are recorded by the
acceptance runner. Its answers use FrameX only after loading local files.
