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

The ingestion boundary is kept separate from the ontology and reasoning rules:

```text
SBB API -> src/ingestion/download.py
				-> src/ingestion/clean.py
				-> src/ingestion/normalize.py
				-> src/ingestion/facts.py
				-> data/generated_facts.fx
```

Generate a small development dataset from the SBB API:

```bash
PYTHONPATH=src python -m ingestion.pipeline data/generated_facts.fx \
	--station-limit 100 --connection-limit 36
```

The generated file is loaded alongside the team's ontology and rules:

```python
from framex import Client

with Client() as client:
		client.load_program(path="data/generated_facts.fx")
		print(client.query("?- ?X:Station."))
		print(client.stats())
```

Use no limits for the full available station and direct-connection datasets. The
generated `.fx` file is ignored by Git; commit the ingestion source, not its
downloaded output.
