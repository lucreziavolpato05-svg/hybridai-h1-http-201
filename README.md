# Fact-safe refund assistant (Hybrid AI, Hackathon 2)

A passenger describes a delayed SBB train journey in their own words. A language
model (GPT-5 mini) turns the words into checked facts and questions; a FrameX
knowledge base built from SBB data of **Saturday 7 November 2026** measures the
delay at the destination; the refund rules decide. **The rules keep the last
word:** every station, time, train, delay, percentage and amount in an answer
comes from the knowledge base or the rules, never from the model. Whatever the
rules cannot settle goes to SBB customer service.

**Coding tools used:** Claude Code (Claude Opus 5.5).
**Language model in the system:** GPT-5 mini (`gpt-5-mini`), the only model used.

## Install

Requires Python 3.10+, [uv](https://docs.astral.sh/uv/), and Rust
([rustup](https://rustup.rs)) to build the FrameX engine. From the repository root:

```bash
uv sync                          # Python packages, incl. the FrameX client and Gradio
sh scripts/install-engine.sh     # builds FrameX 0.5.0 (pinned rev) into .venv/bin
cp .env.example .env             # then put the API key into .env (never commit it)
```

The knowledge base for 07.11.2026 is already in `fx/`; no `--init` is needed.
On Windows see [Windows setup](#windows) below.

## Run

```bash
uv run python src/chat/app.py    # chat + workflow view on http://127.0.0.1:7860
```

In the chat, **Enter** sends and **Shift+Enter** adds a new line. Without
`REFUND_BACKEND` the app runs a labelled demo backend (`[DEMO]` replies, no model,
no verdicts). The real pipeline is selected with `REFUND_BACKEND=module:attr`
(see `src/chat/backend.py`).

The real pipeline: `REFUND_BACKEND=refund.chat_backend:RefundBackend` (see below).

### Refund pipeline (FrameX)

Run (bash; PowerShell below):

```bash
REFUND_BACKEND=refund.chat_backend:RefundBackend uv run python src/chat/app.py
```
```powershell
$env:REFUND_BACKEND="refund.chat_backend:RefundBackend"; uv run python src/chat/app.py
```

- `.env` with `OPENAI_API_KEY` (never committed).
- Model answers are cached in `.model-answers/` for offline replay; record new ones with `uv run python scripts/record_demo.py --live`.
- Tests: `uv run pytest -q tests/test_refund_flow.py tests/test_refund_chat_backend.py tests/test_refund_policy.py tests/test_refund_kb.py`
- P1 Sensor: the model extracts slots, accepted only if the quote is in the passenger's text.
- P3 Translator: the model phrases the rule verdict; accepted only if the decision word and the numbers match.
- P5 Rules steer: the rules decide what to ask, the model words it (max 2 per fact).
- P7 Competence: what the rules cannot settle is handed on to SBB customer service.
- P12 Rules write: the verdict sentence comes from KB and policy receipts.

Details: [docs/refund-assistant.md](docs/refund-assistant.md).

Tools & models: coding agents Claude Code (Claude Opus 5.5; subagents on Claude Opus and Sonnet), OpenAI Codex (gpt-6.1-sol, gpt-6.1-terra, default model); in-system language model GPT-5 mini.


## How it works

| Step | Pattern | Who | What crosses the boundary |
|---|---|---|---|
| 1. Passenger writes in their own words | – | passenger | free text |
| 2. Extract origin, destination, day, time, price, each with a verbatim quote | **P1 Model as Sensor** | model → rules | proposed slots + quotes; rules accept only quotes found in the message and stations that match exactly one stop |
| 3. Decide what is missing and ask for it; list the trains around the stated time and ask which one | **P5 Rules Steer the Model** | rules → model → passenger | the missing slot / the candidate trains (times from the KB) |
| 4. Turn the accepted facts into a checked request to the knowledge base | **P3 Model as Translator** | rules → KB | a `RefundCase` and `DelayCheck` built from validated identifiers only |
| 5. Measure the delay at the destination | – | knowledge base | `46-refunds.fx`: planned vs actual arrival, REAL times only |
| 6. Apply the refund policy | – | rules | `decide()` → status, %, amount |
| 7. Write the answer | – | rules | `render()` from the verdict; the model writes no figure |
| 8. Hand on what the rules cannot settle | **P7 Division by Competence** | rules → SBB customer service | not measurable, other day, unknown station, model failure |

P6 Critique and Repair accompanies P1: a rejected extraction is retried once,
then the rules ask the passenger.

### Refund policy (Sheet 2)

| Delay at the destination | Refund | Status |
|---|---|---|
| under 60 min | none; the answer names the 60 min threshold | `notEntitled` |
| 60 min or more | 25 % of the ticket price | `entitled` |
| 120 min or more | 50 % of the ticket price | `entitled` |
| refund under CHF 5 | not paid out; the answer names the CHF 5 minimum | `entitled` |

The delay is measured at the passenger's destination
([46-refunds.fx](fx/46-refunds.fx)): planned arrival = earliest scheduled arrival
from the planned departure, direct or with one change (cancelled trains count);
actual arrival = earliest arrival the trains that really ran made possible, REAL
times only. A missed connection or cancelled train counts until the next train
really arrives. No REAL arrival and no cancellation, or no actual arrival: no
verdict, hand-over to customer service. The delay the passenger states is never used.

## The five invariants

| Invariant | Where it is kept | Test that proves it |
|---|---|---|
| 1 Model text is data | model output only fills slots that rules validate; KB requests are built from validated station IDs, never from model text | `test_refund_acceptance.py::test_prompt_injection_does_not_change_the_verdict` · ⏳ mock-model test: model writes a figure |
| 2 Every model answer is a dated observation | GPT-5 mini calls go through `framex.tools.model`, stored with date, model and prompt in `.model-answers/` and replayed | ⏳ replay test (no API call) |
| 3 Rules decide | `decide()` in `src/runtime/refund_policy.py` + `46-refunds.fx`; the UI shows the reply unchanged | `test_refunds.py` · ⏳ `test_refund_policy.py` · `test_chat_ui.py::test_reply_is_shown_exactly_as_the_backend_wrote_it` · `test_refund_acceptance.py::test_claimed_delay_does_not_change_the_verdict` |
| 4 Evidence decides acceptance | quotes must occur in the passenger's message; a station must match exactly one stop, otherwise the rules ask | `test_refund_acceptance.py::test_unknown_station_never_gets_a_verdict` · ⏳ mock-model test: quote not in message |
| 5 Failures stay distinct | a model timeout or API error becomes `failed` / hand-over, never "no refund" | `test_chat_ui.py::test_any_backend_failure_becomes_failed_never_a_verdict` · `test_refund_acceptance.py::test_model_failure_is_failed_or_handed_on_never_no_refund` |

⏳ = test still to be written; remove the mark once it exists and passes.

## Tests

```bash
uv run pytest -q                                          # everything
uv run pytest tests/test_refunds.py                       # delay rules (needs the engine)
uv run pytest tests/test_chat_ui.py                       # chat logic, no engine or model
REFUND_BACKEND=module:attr uv run pytest tests/test_refund_acceptance.py -v
uv run python scripts/try_prompts.py                      # 10 sample conversations + trace
```

| File | Checks |
|---|---|
| `tests/test_refunds.py` | delay at the destination: late train, missed connection, cancellation, on time, missing REAL time, departure window |
| `tests/test_refund_policy.py` ⏳ | thresholds 59/60/119/120 min, 25 %/50 %, CHF 5.00 and just under, both thresholds named |
| `tests/test_chat_ui.py` | the chat shows verdicts unchanged; failures never shown as a refusal |
| `tests/test_refund_acceptance.py` | end to end: asks for what is missing, two trains → asks, other day / unknown station → no verdict, claimed delay and prompt injection ignored, every number in a verdict traced to the rules or KB |
| `tests/data/refund_cases.json` | real cases from the 07.11 snapshot, derived by the rules alone (no model) |

`test_refund_acceptance.py` fails until the pipeline is connected through
`REFUND_BACKEND`; it was written before the first model call.

## Submission zip

Code + README only: no `.venv`, `.env`, caches or `__MACOSX`. `fx/` (84 MB, the
07.11.2026 snapshot) is the knowledge base the system runs on. A zip of exactly
the tracked files:

```bash
git archive --format=zip -o hackathon2.zip HEAD
```

---

# Swiss rail FrameX knowledge base

A FrameX ontology built from public datasets on [data.sbb.ch](https://data.sbb.ch).
Python maps source records into facts; FrameX rules derive facilities, service
categories, non-stop connections, and dated journeys. Missing evidence remains
unknown under an open world.

## Quick start

```bash
uv sync
sh scripts/install-engine.sh
uv run python src/main.py --init     # only to rebuild fx/ from the SBB API
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

The REPL loads the knowledge base once and reuses the session. For a single query:

```bash
uv run python src/main.py --query '?- sp_8509000[hasWifi -> ?W].'
```

Full-snapshot checks are opt-in; see the development guide for setup.

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
| `src/chat/` | Gradio chat, workflow view, and the backend seam |
| `src/cli/` | Commands, REPL, progress, and answer formatting |
| `src/data/` | SBB API access |
| `src/ontology/` | Rules, mappings, identities, and fact generation |
| `src/runtime/` | Engine sessions, source loading, validation, refund policy |
| `fx/` | The knowledge base: rules + SBB facts of 07.11.2026 |
| `tests/` | Unit, regression, acceptance, and opt-in snapshot tests |
| `scripts/` | Engine install, Windows dev shell, sample prompt runs |
| `docs/` | User and developer guides |
