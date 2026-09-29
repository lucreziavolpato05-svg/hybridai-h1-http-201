# SBB platform ingestion

This document covers the preserved platform-only API. For all eight datasets,
bulk loading, official queries and current verification, use the root
[README](../README.md) and [verification.md](verification.md).

## Source and modules

The first dataset is [Stop: platform length (body)](https://data.sbb.ch/explore/dataset/perron/),
identifier `perron`. Requests use
`https://data.sbb.ch/api/explore/v2.1/catalog/datasets/perron/records`.

| Module / folder | Responsibility |
| --- | --- |
| `src/ingestion/connector.py` | Fetch pages of up to 100 records, ordered by `fid`; cache a complete download. |
| `data/raw/perron/` | Raw records with source URL, fetch time, requested limit, and API total count. |
| `src/ingestion/normalizer.py` | Clean whitespace, validate identifiers/numbers/coordinates, parse access flags, deduplicate records. |
| `src/ingestion/emiter.py` | Render typed records as F-logic facts, escaping strings and emitting object references. |
| `src/ingestion/ingest.py` | CLI, generated `.fx` output, and incremental `client.add(source=...)` calls. |
| `src/framex.py` | Existing transport to the FrameX executable. |

The filename `emiter.py` follows the requested layout. `__init__.py` marks the
ingestion package. Cleaning lives in `normalizer.py`, and all API access and
caching live in `connector.py`. The ingestion layer emits base facts; reasoning
rules belong to the caller's ontology. Use `python -m ingestion.ingest` for the
platform-only flow. The additional DiDok and WiFi adapters, shared connector,
and combined query harness are documented in [reasoning-demo.md](reasoning-demo.md).

## Running

From the repository root, using PowerShell:

```powershell
$env:PYTHONPATH = "src"
uv run --python 3.12 -m ingestion.ingest --limit 10 --dry-run
uv run --python 3.12 -m ingestion.ingest --binary "C:\Users\Levashenko\bin\framex.exe" --query '?- ?P[structuralLengthM -> ?Length].'
```

Omit `--limit` to retrieve all records. `--dry-run` downloads, caches, normalizes,
and writes `data/platforms.fx` without requiring the engine. `--output` and
`--raw-dir` override the output and cache locations. The CLI opens a new FrameX
session, loads `world open.`, adds the facts, prints engine statistics, runs an
optional `--query`, then closes the session. The `.fx` file and raw cache persist;
the in-memory engine session does not.

To add the dataset to an existing session with your own ontology:

```python
from framex import Client
from ingestion.connector import fetch_records
from ingestion.normalizer import normalize_records
from ingestion.ingest import ingest_platforms

platforms = normalize_records(fetch_records())
with Client(binary="framex", retain_transcript=False) as client:
    client.load("world open.")  # Load your ontology/rules here.
    ingest_platforms(client, platforms)
    print(client.query("?- ?P:Platform."))
    print(client.query("?- ?P[station -> ?S; structuralLengthM -> ?Length]."))
```

`ingest_platforms` never calls `load`, so it preserves an existing program.
It batches complete fact lines below FrameX's 1 MiB request limit, accounting
for JSON escaping. Adds are incremental: if a later batch fails, preceding
batches remain applied, and no automatic mutation retry occurs. Adding refreshed
records to an existing session does **not** remove old values or deleted records;
start a fresh session or explicitly retract old source facts when replacing data.
See the [FrameX client documentation](https://unisg-ics-dsnlp.github.io/FrameX-Doc/python/client.html).

## Cache behavior

`all.json` holds a full snapshot; `limit_10.json`, for example, holds a sample.
A sample cannot be mistaken for the complete dataset. Cached runs need no network
access. `--refresh` forces downloading; there is no automatic expiry. Snapshots
are atomically replaced only after the download completes, and failed refreshes
leave the old file intact. Invalid cache files fail with a `--refresh` instruction.
The connector rejects incomplete responses and changing totals. Ordered pagination
is not a transactional API snapshot, so upstream edits during a download can still
affect rows. The records endpoint's 10,000-row window is sufficient for `perron`;
larger datasets would require an export connector.

`fetch_dataset_records(dataset_id, *, order_by=None, where=None, ...)` shares this
download/cache logic across adapters. Generic cache filenames include a hash of
the filter and ordering to prevent reusing a different request's snapshot.
`fetch_records(...)` remains the platform wrapper; existing `perron/all.json`
and `perron/limit_<n>.json` caches remain compatible.

All original record fields remain in the cache. Normalization failures include
the row index and `fid`; they do not silently drop records. Identical duplicate
installations collapse into one record, while conflicting records with the same
FID fail validation. Missing optional values produce no fact, preserving the
distinction between unknown, zero, and false.

## Field mapping

Each installation becomes `platform_<fid>:Platform`. A known UIC creates a
`station_<bpuic>:Station` linked through `station`; otherwise the fallback is
`station_didok_<dst_id>`. Without either identifier, stop details remain on the
platform and no station reference is invented. Identifiers and platform numbers
are strings, preserving leading zeros and labels such as `1/2`.

| SBB field | F-logic property |
| --- | --- |
| `fid` | Platform ID and `sourceId` |
| `p_nr`, `perrontyp` | `number`, `platformType` |
| `p_lange` | `structuralLengthM` |
| `linie`, `km` | `line`, `lineKm` |
| `perronflach_brutto_m2`, `perronflach_netto_m2` | `grossAreaM2`, `netAreaM2` |
| `z_schienenfrei` | `railFreeAccess` boolean (`ja` / `nein`) |
| `dok_pfm` | `region` |
| `geopos.lat`, `geopos.lon` | Platform `latitude`, `longitude` |
| `bps_name`, `bps` | Station `name`, `abbreviation` |
| `bpuic`, `dst_id`, `lod` | Station `uic`, `didokCode`, `lod` |

Every platform also has `sourceDataset -> "perron"`. The short `dst_id` is kept
separate from the full UIC. Platform coordinates are not asserted as station
coordinates. SBB defines `p_lange` as structural length; it may differ from the
length usable for boarding. `railFreeAccess` means reaching the platform without
crossing tracks; it does not establish wheelchair access. All platform types are
retained, including service platforms; presence does not imply public access.

Example facts:

```text
platform_35288249:Platform.
platform_35288249[number -> "1/2"].
platform_35288249[structuralLengthM -> 323.0].
platform_35288249[railFreeAccess -> true].
station_8506013:Station.
platform_35288249[station -> station_8506013].
station_8506013[name -> "Aadorf"].
```

## Verification

Offline tests cover pagination, cache reuse/refresh/failure, normalization,
escaping, batch byte limits, and the incremental client interface:

```powershell
$env:PYTHONPATH = "src"
uv run --python 3.12 -m unittest discover -s tests -v
```
