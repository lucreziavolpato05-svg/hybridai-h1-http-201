# SBB Data Pipeline

## Ownership

The ingestion layer owns downloading, missing-field handling, stable IDs,
passenger-rail filtering, and base-fact serialization. It does not own ontology
classes beyond the base `Station` and `DirectConnection` facts, and it does not
define reasoning rules.

## Modules

- `src/ingestion/download.py`: paginated SBB Explore API access.
- `src/ingestion/clean.py`: whitespace cleanup, transport filtering, and `vias` parsing.
- `src/ingestion/normalize.py`: stable station and connection records.
- `src/ingestion/facts.py`: FrameX fact serialization.
- `src/ingestion/pipeline.py`: orchestration and CLI.
- `src/framex.py`: standard-library FrameX transport client.

## Data contract

The exporter emits `world open.`, `Station` facts, `DirectConnection` facts,
station properties, and object-reference properties such as `startStation`,
`endStation`, and `viaStation`. Object references are unquoted so ontology
rules can join them directly.

The station source is `haltestelle-haltekante`, filtered server-side to records
whose transport modes include `TRAIN` or `RACK_RAILWAY`. Direct connections
come from `direktverbindungen`; its semicolon-delimited JSON `vias` field is
parsed defensively and matched by DIDOK when available.