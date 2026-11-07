# Swiss rail FrameX knowledge base

A FrameX ontology built from public datasets on [data.sbb.ch](https://data.sbb.ch).
Python maps source records into facts; FrameX rules derive facilities, service
categories, non-stop connections, and dated journeys. Missing evidence remains
unknown under an open world.

## Quick start

Requires Python 3.10+, [uv](https://docs.astral.sh/uv/), and Rust
([rustup](https://rustup.rs)) to build the FrameX engine. Run commands from the
repository root:

```bash
uv sync
sh scripts/install-engine.sh
uv run python src/main.py --init
uv run python src/main.py --repl
```

`uv sync` installs the FrameX Python client from
[framex-core](https://gitlab.com/ds-unisg/framex-core). The install script builds
the engine from the same commit into `.venv/bin/framex`, so no global install is
needed. To move to a newer FrameX, change the `rev` in `pyproject.toml`
(`[tool.uv.sources]`), then rerun both commands.

Initialization downloads source data and writes the knowledge base to `fx/`.
The REPL loads it once and reuses the session. For a single query:

```bash
uv run python src/main.py --query '?- sp_8509000[hasWifi -> ?W].'
```

Run local tests with `uv run pytest -q`. Full-snapshot checks are opt-in;
see the development guide for setup.

## Documentation

| Guide | Contents |
|---|---|
| [Usage](docs/usage.md) | Builds, queries, REPL, journeys, and Python sessions |
| [Ontology](docs/ontology.md) | Semantics, identities, mappings, and extensions |
| [Data](docs/data.md) | Dataset discovery, API options, and source-data quirks |
| [Development](docs/development.md) | Architecture, loading, publication, and testing |
| [FrameX core](https://gitlab.com/ds-unisg/framex-core) | Engine and Python client sources |

## Repository layout

| Path | Purpose |
|---|---|
| `src/main.py` | CLI entry point |
| `src/cli/` | Commands, REPL, progress, and answer formatting |
| `src/data/` | SBB API access |
| `src/ontology/` | Rules, mappings, identities, and fact generation |
| `src/runtime/` | Engine sessions, source loading, and validation |
| `tests/` | Regression tests and opt-in snapshot checks |
| `docs/` | User and developer guides |
| `scripts/install-engine.sh` | Builds the FrameX engine into `.venv/bin` |
