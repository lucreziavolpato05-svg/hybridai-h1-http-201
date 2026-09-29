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

The initial sources are platform lengths, DiDok service points, and Wifi@Station.
Their raw API snapshots are cached locally but deliberately excluded from Git.

## Coding agents and models

The team used **Claude** and **Codex** as coding agents/models for implementation
and documentation support. Team members review the resulting code, ontology,
tests, and documentation before accepting changes.

## Reproduce the results

From this project directory, install the Python environment and make the FrameX
executable available on `PATH` (or set `FRAMEX_BINARY` to its path):

```powershell
uv sync
$env:PYTHONPATH = "src"
$env:FRAMEX_BINARY = "C:\path\to\framex.exe" # omit when framex is on PATH
```

Prepare the local facts once, then run the offline demos and test suites:

```powershell
# Downloads only missing raw snapshots; later runs reuse data/raw/.
uv run --python 3.12 -m ingestion.prepare --as-of 2026-09-29

# Loads ontology.fx plus the generated local fact files; makes no API requests.
uv run --python 3.12 -m query

# Verify the implementation.
uv run --python 3.12 -m unittest discover -s tests -v
uv run --python 3.12 -m unittest discover -s tests/integration -v
```

On macOS/Linux, use `PYTHONPATH=src` (and, if needed,
`FRAMEX_BINARY=/path/to/framex`) before the corresponding command. The `--as-of`
option filters DiDok validity; it does not recreate an earlier API snapshot. For
identical live results, retain and reuse the same local `data/raw/` snapshots.

## AI-assisted development

Tool: OpenAI Codex in VS Code.
Model: **MODEL_NAME_TO_FILL_IN_BEFORE_SUBMISSION** (exact model not yet confirmed).

Before you start coding, your team needs to create a shared repository and set up the Python development environment. 🚀

We will use: 
- **GitHub** for collaboration and version control
- **Python 3.12**
- **uv** for Python, virtual environments and package management to ensure reproducibility

> [!IMPORTANT]
> Only one person per team should fork the repository. Everyone else will be invited to that fork.

## Getting started
### 1. Fork the Repository
One team member should create the team's fork.

1. Open the Hackathon repository on GitHub.
2. Click Fork in the top-right corner.
3. Select your GitHub account as the owner.
4. Change the name from hybridai-h1-Template to hybridai-h1-GROUPNAME. (GROUPNAME is obviously the name of your group and not literaly GROUPNAME)
5. Click Create fork.

You now have a copy of the Hackathon repository under your GitHub account.

This will be your team repository.

### 2. Ivite your Team
The person who created the fork should now give the rest of the team access.

Open your fork on GitHub and go to:
- Settings → Collaborators → Add people

### 3. Install uv
You can find a full uv installation guide in the official uv documentation: [docs.astral.sh](https://docs.astral.sh/uv/getting-started/installation/)

Check that uv is installed with: 
```bash
uv --version
```

### 4. Set Up the Project
1. Clone your teams Project - if not already done
2. Initialize the project and set the python version to at least 3.12: 

``` bash
uv init --bare --python 3.12
```

3. Now run `uv sync` to create the virtual environment
4. To run the main.py file using uv you can simply `uv run src/main.py` from the root directory of the repository.
5. To install new python packages for example *numpy* do it with `uv add numpy`

### 5. You are all set
Your codebase is prepared for the hackahton! ⛏️

## SBB to FrameX data flow

Start with SBB's [Stop: platform length (body)](https://data.sbb.ch/explore/dataset/perron/)
dataset (`perron`). The pipeline uses Python's standard library and the existing
[FrameX client](https://unisg-ics-dsnlp.github.io/FrameX-Doc/python/client.html):

```text
SBB API -> connector.py -> data/raw/perron/ (JSON cache)
                       -> normalizer.py -> emiter.py -> ingest.py -> client.add
                                                    -> data/platforms.fx
```

From the repository root in PowerShell, download, cache, and generate F-logic
without starting the engine:

```powershell
$env:PYTHONPATH = "src"
uv run --python 3.12 -m ingestion.ingest --dry-run
```

Run the complete pipeline and query the loaded platforms:

```powershell
uv run --python 3.12 -m ingestion.ingest --binary "C:\Users\Levashenko\bin\framex.exe" --query '?- ?P:Platform.'
```

You can omit `--binary` when `framex` is on PATH. On macOS/Linux, prefix the
command with `PYTHONPATH=src` instead of setting `$env:PYTHONPATH`.

Use `--limit 10` for a sample and `--refresh` to replace the cached snapshot with
fresh API data. By default the whole dataset is downloaded and subsequent runs
reuse its cache. `data/raw/` snapshots and `data/platforms.fx` are ignored by Git.
Platform length is **structural length**, not necessarily usable boarding length;
rail-free access does not imply wheelchair accessibility.

See [the pipeline documentation](docs/data-pipeline.md) for field mappings,
Python integration, cache behavior, and tests. `python -m ingestion.ingest`
remains the platform-only entry point.

## Combined ontology demo

The shared preparation command downloads and caches the three initial sources:
platforms (`perron`), service points (DiDok), and Wifi@Station. They all use one
local raw-data root, `data/raw/`, with an isolated subdirectory per API dataset.
The first command below downloads only snapshots missing from that cache and
generates local fact files. Later runs reuse those snapshots, so they do not call
the APIs. The raw snapshots and generated `.fx` files are intentionally ignored
by Git; every developer runs this setup locally once.

```powershell
$env:PYTHONPATH = "src"
$env:Path += ";C:\Users\Levashenko\bin"
uv run --python 3.12 -m ingestion.prepare --as-of 2026-09-29
```

To prepare only selected sources, pass their canonical names. `didok` remains an
accepted alias for `service_points`.

```powershell
uv run --python 3.12 -m ingestion.prepare --datasets platforms service_points wifi
uv run --python 3.12 -m ingestion.prepare --datasets wifi
```

Use `--refresh` only when you deliberately want to replace cached raw snapshots.
`--raw-dir <folder>` moves the shared local cache for all selected sources, and
`--output-dir <folder>` moves the three generated fact files.

## Test your own query

Once preparation has produced `data/platforms.fx`, `data/service_points.fx`, and
`data/wifi.fx`, `query` loads those local files together with `ontology.fx`; it
never fetches from SBB. Run the built-in demonstrations first if helpful:

```powershell
uv run --python 3.12 -m query
```

Then pass your own F-logic query with `--query`. A query starts with `?-`, uses
variables prefixed by `?`, and ends with a period. For example:

```powershell
# List locally loaded stop points and their names.
uv run --python 3.12 -m query --query '?- ?Station:StopPoint[designation -> ?Name].'

# Find platforms at Bern whose ontology-derived length is greater than 320 m.
uv run --python 3.12 -m query --query '?- ?Station:StopPoint[designation -> "Bern"] AND ?Platform:LongPlatform[atStopPoint -> ?Station; platformNumber -> ?Number; platformLength -> ?Length].'

# Find stations in Ticino that have positive WiFi evidence.
uv run --python 3.12 -m query --query '?- ?Station:StopPoint[inCanton -> canton_ti; hasWifi -> true; designation -> ?Name].'
```

The output shows the engine status and variable bindings. In this open-world
ontology, `unknown` means the local facts do not establish the statement; it is
not the same as `false`. Repeat `--query` to test several expressions in one
run, or add `--explain 'platform_35292761:LongPlatform'` to inspect a derived
fact's proof.

See [reasoning and dataset integration](docs/reasoning-demo.md) for the field
mappings, additional queries, tests, and known source-data limitations.
