# Offline reasoning over platforms, DiDok, and WiFi

> Historical three-source integration notes. The completed eight-source system,
> commands and verified results are documented in [README](../README.md) and
> [verification.md](verification.md). `main.py` now delegates to the real query
> application; all eight files are loaded by default. DiDok owns designation,
> resolving the spelling conflict described in these older notes. Current full
> validation has zero violations and 68 unknown required-field checks. Train
> export support and the remaining adapters are implemented.

## Architecture and scope

```text
SBB API -> connector.py -> raw JSON snapshots
  perron -> normalizer.py + emiter.py -> data/platforms.fx
  DiDok  -> didok.py                  -> data/service_points.fx
  WiFi   -> wifi.py                   -> data/wifi.fx

ontology.fx + generated base facts -> query.py -> FrameX derived facts/queries/explanations
```

`ingestion.prepare` orchestrates file generation. The existing platform-only
`ingestion.ingest` and its `client.add` interface remain unchanged. `main.py`
and the repository's `framex.py` transport are unchanged. There is no universal
normalizer or ontology generator. Only the download/cache layer and full-UIC
identity helper are shared. `query.py` reads local files and calls FrameX;
it does not import the ingestion pipeline or make network requests.

All programs use `world open.`. Missing evidence remains unknown. Derived classes
and properties are computed by the existing ontology, not by Python.

## Source contracts inspected on 2026-09-29

- [DiDok service points](https://data.sbb.ch/explore/dataset/dienststellen-gemass-opentransportdataswiss/):
  full UIC is `number`, name is `designationofficial`, canton is
  `cantonabbreviation`, modes are pipe-separated `meansoftransport` tokens.
  `numbershort` is **not** the station identity. `stoppoint` is text `true`/`false`.
- [Wifi@Station](https://data.sbb.ch/explore/dataset/wifistation/): `bpuic` is the
  full UIC; `standort` is an inventory label. Row presence supplies positive WiFi
  evidence. There is no availability boolean to infer or negate.

The live schema endpoints are `/api/explore/v2.1/catalog/datasets/<dataset-id>`;
records use the `/records` suffix. The dataset IDs are
`dienststellen-gemass-opentransportdataswiss` and `wifistation`.

The DiDok adapter explicitly selects Swiss (`isocountrycode = "CH"`) stop points
with `TRAIN` or `RACK_RAILWAY` in `meansoftransport`. It preserves other positive
modes on those same records, including `TRAM`; it does not merge nearby tram
stops by name or geography. `validfrom` and `validto`, when supplied, are checked
against `--as-of`. Missing country/stop/mode evidence does not establish scope.
Missing optional names/cantons produce no fact; malformed identifiers, cantons,
dates, or unsupported mode tokens produce a contextual error. No broad bus-only,
foreign, or freight-only service-point import is performed.

All three datasets join on `station_<full UIC/BPUIC>`. DiDok emits `StopPoint`,
`designation`, `inCanton`, and `servesMode`, with Canton/Mode objects. WiFi emits
only `station_<UIC>[hasWifi -> true]`, leaving authoritative naming to DiDok.
Platform properties retain the original names and use the ontology's existing
compatibility rules. The existing short-DiDok fallback on platforms is unchanged;
new adapters never fabricate a full UIC from a short number.

## Commands (PowerShell, repository root)

```powershell
$env:PYTHONPATH = "src"
$env:Path += ";C:\Users\Levashenko\bin"

# Download/cache and prepare all three fact files (default --as-of is today).
uv run --python 3.12 -m ingestion.prepare --as-of 2026-09-29

# Force new API snapshots, or prepare only the new adapters.
uv run --python 3.12 -m ingestion.prepare --datasets service_points wifi --refresh --as-of 2026-09-29

# Run all five demo queries entirely offline, using the existing ontology.
uv run --python 3.12 -m query

# Select one demo, or submit any compositional F-logic query.
uv run --python 3.12 -m query --demo ticino-wifi
uv run --python 3.12 -m query --query '?- ?S:Interchange[designation -> ?Name].'

# Explain a derived fact from the downloaded snapshot.
uv run --python 3.12 -m query --explain 'platform_35292761:LongPlatform'

# Inspect a concise summary of constraint/schema diagnostics.
uv run --python 3.12 -m query --validate --demo open-world-wifi
```

Use `--binary <path>` if FrameX is not on PATH. `--ontology <path>` and
`--facts <file1> <file2> ...` select alternative local inputs. `--query`, `--demo`,
and `--explain` can be repeated. The CLI prints status and bindings separately;
an `unknown` result is not converted to false or an empty-answer claim.

`--limit N` on preparation is a raw sample limit **per dataset**, so small samples
may not contain any named demo stations. Omit it for the full scoped datasets.
DiDok normalization may further exclude dated/out-of-scope rows. Files are
generated independently; if one adapter fails, previously generated files remain.
The cache includes fetch time, request filters/order, limit, and total count.
`--as-of` filters DiDok validity intervals; it does not recreate a historical API
snapshot. Files and caches are ignored by Git.

## Ontology validation

Synthetic offline integration tests cover platform compatibility and the strict
320 m threshold; `busyIn(year)`; distinct-line junctions; train/tram interchanges;
actual-stop/category derivation; adjacent, pass-through, cancelled and mixed
event chains; long-distance categories; and missing/negated WiFi evidence.
They also exercise all three dataset adapters together and inspect a derived
platform explanation from the real engine.

The pre-change tests reproduced two ontology gaps. The changes are limited to
one additional recursive rule skipping positively cancelled intermediate events
and seven declarative LongDistanceCategory seeds: IC, IR, EC, ICE, TGV, NJ, RJX.
Unknown intermediate events are still not skipped, and an actual intervening
stop still prevents a direct non-stop link. No station-specific answers are seeded.

Both string years (`"2025"`) and numeric years (`2025`) work in the installed
FrameX engine. They are different values: facts and queries must agree on type.
Use numeric years consistently in future passenger-frequency ingestion.

```powershell
$env:PYTHONPATH = "src"

# Unit tests: no network and no engine needed.
uv run --python 3.12 -m unittest discover -s tests -v

# Separate synthetic integration tests: no network, real FrameX required.
$env:FRAMEX_BINARY = "C:\Users\Levashenko\bin\framex.exe"
uv run --python 3.12 -m unittest discover -s tests/integration -v
```

Integration tests use `FRAMEX_BINARY` or search PATH; without either they report
skips. The normal unit discovery command does not descend into the separate
integration directory.

## Observed live results and limitations

The inspected snapshots produced 1,570 platforms, 1,773 scoped DiDok service
points and 73 joinable WiFi stations from 79 inventory rows. Six WiFi rows lack
BPUIC: the adapter warns and skips them, retaining the untouched cache. It does
not guess an identity from the inventory name. Missing or skipped evidence cannot
justify `hasWifi -> false`.

The five demos returned: positive Chur WiFi evidence; 9 Zürich HB platform/length
rows; 7 Bern LongPlatform rows; 3 Ticino stations with WiFi; and `unknown` for
the open-world WiFi query. The source also supports 6 derived train/tram
interchanges in the scoped snapshot. These are observations, not test fixtures
or hardcoded answers.

Full validation is **not clean**: the platform source sometimes omits accents
(e.g. `Zurich HB`) while DiDok supplies `Zürich HB`. The existing compatibility
rule maps platform station names to `designation`, so loading both sources
produces 298 functional-designation violation facts in this snapshot. Seven
schema checks are also unresolved. The harness reports these diagnostics;
`--validate` is informational, not a clean-validation exit-code assertion.
`client.validate()` exposes the full report. No names or constraints were
silently removed to mask these conflicts. Resolving authoritative names across
sources needs a coordinated ingestion/ontology policy.

There are no live StopEvent facts yet. The long-distance/negative-WiFi demo is
therefore also limited by missing event evidence; the synthetic test separately
proves `unknown` for an explicitly known LongDistanceStation with no WiFi fact.

## Query coverage and next work

Supported with live data: Chur WiFi, Zürich HB platforms/lengths, Ticino/WiFi
joins, Bern long platforms, positive mode/canton queries, and train/tram
Interchange. Open-world WiFi behavior is covered by both queries and synthetic
tests. Junction, busyIn, actual-stop categories, long-distance membership and
non-stop chains are tested but await their real source adapters.

Missing datasets: waiting rooms, sector boards, dated target/actual train-stop
events, passenger frequencies, line operation points, and any required route
network identity mappings. The single next highest-value step is dated
StopEvent ingestion: it unlocks actual categories, TGV service, long-distance
stations, and non-stop destinations using the already-tested rules. Preserve
journey/date identity and build `nextStop` only within one ordered journey.
