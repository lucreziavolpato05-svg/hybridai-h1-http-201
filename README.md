# Hackathon 1 - Derive From Knowledge

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
Python integration, cache behavior, and tests. `python -m ingestion.ingest` is
the ingestion entry point; the supported dataset is currently `perron`.
