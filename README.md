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

### Windows

Building the engine needs Rust with the MSVC toolchain and Visual Studio Build
Tools ("Desktop development with C++"); run the install script from Git Bash.
`cargo install` writes `.venv\bin\framex.exe`, next to (not inside)
`.venv\Scripts`; the engine lookup checks both. For each new PowerShell session:

```powershell
cd C:\path\to\hybridai-team-h2
. .\scripts\dev.ps1
```

The script leaves any other active venv, runs `uv sync --locked`, activates
`.venv`, and puts the pinned engine first on `PATH` and in `FRAMEX_BINARY`, so
an older global `framex` is never used. It warns if the engine was built from a
different commit than `pyproject.toml` pins. `tzdata` is a dependency because
Windows has no system time-zone database for `Europe/Zurich`.

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

## Refund chat (Hackathon 2)

Gradio chat for the fact-safe refund assistant, with a workflow view of every
step (pattern, actor, what crossed the boundary):

```bash
uv run python src/chat/app.py                              # demo backend, no model
REFUND_BACKEND=module:attr uv run python src/chat/app.py   # the real pipeline
```

The UI calls one seam, `Backend.respond(message, state) -> Turn`
(`src/chat/backend.py`). It never decides or edits a verdict: it shows the
backend's reply unchanged, and any exception, unknown status or empty reply is
shown as a technical failure handed on to customer service, never as "no refund".

Tests:

```bash
uv run pytest tests/test_chat_ui.py                       # UI logic, no engine needed
REFUND_BACKEND=module:attr uv run pytest tests/test_refund_acceptance.py -v
uv run python scripts/try_prompts.py                      # sample conversations + trace
```

`test_refund_acceptance.py` is the auditor's specification and fails until the
pipeline is connected. Its known cases (`tests/data/refund_cases.json`) come from
the rules alone (`46-refunds.fx` on FrameX 0.5.0), never from the model.

Coding tools used: Claude Code (Claude Opus 5.5). Language model in the system: GPT-5 mini.
