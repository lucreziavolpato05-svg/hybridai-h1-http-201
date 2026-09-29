# FrameX Integration and Evaluation

## Which documentation to use

The repository's [src/framex.py](../src/framex.py) is the authoritative Python
integration contract. It is the client written for this FrameX binary; do not
install or import the unrelated PyPI package named `framex`.

The [SBB data pipeline guide](data-pipeline.md) is the authoritative contract
for the facts produced by ingestion. The FrameX binary itself provides the
language-level checks through `framex --help`, `framex check`, `framex validate`,
`framex report`, and `framex test`.

## Loading facts and ontology

Use `load_program` for generated data because it stages large input in chunks.
`load` is intended for small source strings. Load the generated facts and the
team ontology into the same session before querying:

```python
from pathlib import Path

from framex import Client

facts = Path("data/generated_facts.fx").read_text(encoding="utf-8")
ontology = Path("ontology.fx").read_text(encoding="utf-8")

with Client() as client:
    client.load_program(source=facts + "\n" + ontology)
    print(client.validate())
    print(client.stats())
    print(client.query("?- ?X:Station."))
```

When the combined source is larger than memory or the ontology is updated
separately, load the facts first and use `client.add(source=ontology)` for the
small ontology/rule file.

## Open-world policy

The generated SBB graph starts with `world open.`. This is intentional: an
absent record usually means that the API response, filter, or snapshot did not
contain it; it does not prove that the fact is false.

Use closed assumptions only where the source contract explicitly guarantees
completeness, for example “this snapshot contains every direct connection in
the selected dataset.” Represent that scope in the ontology with an explicit
snapshot/completeness fact and write rules that depend on that fact. Do not
infer a negative station, route, or property merely because ingestion did not
emit it.

`Client.world("closed")` changes the assumption for the entire FrameX session;
it is not a per-predicate switch. Keep the main SBB session open-world. If a
closed-world comparison is useful, run it in a separate session and label its
results accordingly.

Evaluation should distinguish these outcomes:

- `true`: the fact is asserted or derived.
- `false`: a scoped, justified closed assumption supports the negative result.
- `unknown`: the open-world data does not establish either side.

## Data correctness checks

Run the ingestion with a bounded sample first:

```powershell
$env:PYTHONPATH = "src"
python -m ingestion.pipeline data/generated_facts.fx --station-limit 100 --connection-limit 36
framex check data/generated_facts.fx
framex validate data/generated_facts.fx
framex report data/generated_facts.fx
```

Check all of the following before trusting the result:

1. The API response count is plausible and the output has non-zero `Station`
   and `DirectConnection` facts.
2. Every emitted station has a stable DIDOK-based identifier when the source
   provides one, a non-empty name, and valid coordinates when available.
3. Every station has `TRAIN` or `RACK_RAILWAY` in its source transport modes.
4. Every `startStation`, `endStation`, and `viaStation` reference is an
   unquoted FrameX object identifier, not a string literal.
5. The generated file passes `framex check` and `framex validate`.
6. The FrameX `stats()` result is recorded for the sample and full dataset so
   accidental data-volume changes are visible in review.

## Reasoning correctness checks

Use known-answer queries whose answers can be checked against the source data:

```python
with Client() as client:
    client.load_program(source=facts + "\n" + ontology)

    # Base-fact existence
    assert client.query("?- station_8503000:Station.")["status"] == "true"

    # Inspect why a fact is present or absent
    print(client.explain("station_8503000:Station"))
    print(client.why_not("station_9999999:Station"))

    # Inspect the derived graph and resource usage
    print(client.stats())
```

Add the team's actual ontology rule queries as FrameX expectations and run:

```powershell
framex test --rule-coverage ontology-and-expectations.fx
```

For a failed answer, compare `query`, `explain`, `why_not`, and `provenance`
before changing ingestion. This distinguishes bad source data from an ontology
or rule problem.

## Reproducibility

Record the dataset IDs, API query filters, fetch date, generated fact count,
FrameX version, and `stats()` output with each evaluation. The SBB API is live,
so a later run can legitimately contain different records. Keep generated
facts out of Git unless the team deliberately wants a frozen fixture for tests.