# Fact-safe refund assistant (Hybrid AI, Hackathon 2)

## Team

| Member | Role |
| --- | --- |
| Egor Levashenko | Developer |
| Ethan | Developer |
| Wee Siang | Domain Expert |
| Lucrezia Volpato, Ethan | Auditor |

A passenger describes a delayed SBB train journey in their own words. A language
model (GPT-5 mini) reads the words and phrases questions; a FrameX control program
decides what to ask, what counts and what follows; a FrameX knowledge base built
from SBB data of **Saturday 7 November 2026** measures the delay at the destination.
**The rules keep the last word:** every station, time, train, delay, percentage and
amount in an answer comes from the knowledge base or the policy, never from the
model. Whatever the rules cannot settle goes to SBB customer service.

**Coding tools used:** Claude Code (Claude Opus 5.5; subagents on Claude Opus and
Sonnet), OpenAI Codex (gpt-6.1-sol, gpt-6.1-terra, default model).
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
On Windows the engine build needs Visual Studio Build Tools with the "Desktop
development with C++" workload (MSVC linker and Windows SDK), and must run from
PowerShell or cmd, not Git Bash (Git Bash's `link` command shadows the MSVC linker).
See [Windows setup](#windows) below.

## Run

```bash
uv run python src/chat/app.py                        # chat + workflow view, http://127.0.0.1:7860
REFUND_BACKEND=demo uv run python src/chat/app.py    # UI only: scripted [DEMO] replies, no model or engine
```
```powershell
uv run python src/chat/app.py
$env:REFUND_BACKEND="demo"; uv run python src/chat/app.py
```

The app runs the FrameX refund pipeline (`refund.chat_backend:RefundBackend`) by
default. In the chat, **Enter** sends and **Shift+Enter** adds a new line. When the
rules ask for the ticket price or a train, a form appears under the question (a
number box, or the offered trains as buttons plus "Not sure / describe it"). A form
answer reaches the rules as a receipt without a model call, and the rules validate
it (the asked slot, an offered train, a positive price); typed answers go through
the P1 sensor. Model answers are cached in
`.model-answers/` for offline replay; record new ones with
`uv run python scripts/record_demo.py --live`. On Windows, record with
`PYTHONUTF8=1` (PowerShell: `$env:PYTHONUTF8="1"`): FrameX writes the files in the
system encoding, and a cp1252 file does not replay on macOS or Linux. Design details:
[docs/refund-assistant.md](docs/refund-assistant.md).

## How it works

| Step | Pattern | Who | What crosses the boundary |
|---|---|---|---|
| 1. Passenger writes in their own words | – | passenger | free text, stored as an escaped literal |
| 2. Read origin, destination, date, time, price, each with a verbatim quote | **P1 Model as Sensor** | model → rules | proposed slots + quotes; a slot counts only if its quote is in the passenger's text (the price must also occur in its quote) |
| 3. Decide what is missing and ask for it (max 2 questions per fact); list the trains and ask which one | **P5 Rules Steer the Model** | rules → model → passenger | the slot the rules chose; the model only words the question; trains and times come from the KB |
| 4. Resolve station names, measure the delay at the destination | – | rules → KB | `_station` (name → stop ID), `_measure` (`RefundCase`/`DelayCheck` in `46-refunds.fx`, REAL times only) |
| 5. Apply the refund policy | – | rules → policy | `_policy` (`src/refund/policy.py`): status, %, amount, paid out |
| 6. Write the answer from the receipts | **P12 Model Selects, Rules Write** | rules | a rule-authored template filled only with KB and policy values |
| 7. Optional rephrasing | **P3 Model as Translator** | rules → model → rules | accepted only if it keeps the decision word and exactly the same numbers; otherwise the rule text is sent |
| 8. Hand on what the rules cannot settle | **P7 Division by Competence** | rules → SBB customer service | other day, unknown station after 2 questions, no train, not measurable, a failed tool |

### Refund policy (Sheet 2)

| Delay at the destination | Refund | Status |
|---|---|---|
| under 60 min | none; the answer names the 60 min threshold | `notEntitled` |
| 60 min or more | 25 % of the ticket price | `entitled` |
| 120 min or more | 50 % of the ticket price | `entitled` |
| refund under CHF 5 | not paid out; the answer names the CHF 5 minimum | `entitled` |

Amounts are rounded to the cent, half up, before the CHF 5 minimum is applied
(CHF 4.995 is paid as CHF 5.00). The delay is measured at the passenger's
destination ([46-refunds.fx](fx/46-refunds.fx)): planned arrival = earliest
scheduled arrival from the planned departure, direct or with one change (cancelled
trains count); actual arrival = earliest arrival the trains that really ran made
possible, REAL times only. A missed connection or cancelled train counts until the
next train really arrives. No REAL arrival and no cancellation, or no actual
arrival: no verdict, hand-over to customer service. The delay the passenger states
is never used.

## The five invariants

| Invariant | Where it is kept | Test that proves it |
|---|---|---|
| 1 Model text is data | passenger text enters as an escaped literal; model rows are proposals the rules accept or refuse; KB requests use resolved stop IDs only | `test_refund_flow.py::test_passenger_text_is_escaped_as_a_literal` · `::test_prompt_injection_cannot_set_policy_or_reply` · `::test_p3_changed_fact_is_rejected_and_rule_text_used` |
| 2 Every model answer is a dated observation | GPT-5 mini calls go through FrameX's `_llm`, stored with date, model and prompt in `.model-answers/`; the flow tests replay recorded answers without an API call | `test_refund_flow.py` (runs from recorded answers) · `::test_rule_text_is_default_without_phrasing_fixture` |
| 3 Rules decide | `refund.fx` chooses every step; the verdict is the `_policy` receipt; the UI shows the reply unchanged | `test_refund_policy.py` · `test_refund_flow.py::test_policy_thresholds` · `test_refunds.py` · `test_chat_ui.py::test_reply_is_shown_exactly_as_the_backend_wrote_it` |
| 4 Evidence decides acceptance | a slot counts only if its quote is in the passenger's text; the price must occur in its quote; a train choice must be one of the offered departures; stations resolve to exactly one stop | `test_refund_flow.py::test_fabricated_quote_is_rejected` · `::test_price_number_must_occur_in_its_quote` · `::test_choice_must_match_last_offered_departures` · `test_refund_slots.py` (date/time quote check) |
| 5 Failures stay distinct | a failed tool, model error or timeout becomes `failed` or a hand-over, never "no refund" | `test_refund_flow.py::test_failed_policy_receipt_never_becomes_a_verdict` · `::test_engine_failure_returns_failed_status` · `test_chat_ui.py::test_any_backend_failure_becomes_failed_never_a_verdict` |

## Tests

```bash
uv run pytest -q                                   # everything (needs the FrameX 0.5.0 engine)
uv run pytest -q tests/test_refund_flow.py tests/test_refund_kb.py tests/test_refunds.py   # pipeline + KB
uv run pytest -q tests/test_refund_policy.py tests/test_refund_chat_backend.py tests/test_refund_slots.py tests/test_chat_ui.py tests/test_chat_form.py tests/test_chat_diagram.py   # no engine or model
uv run pytest -v tests/test_refund_acceptance.py   # end to end through the chat seam (live model)
```

| File | Checks |
|---|---|
| `tests/test_refund_flow.py` | the whole conversation on recorded model answers: asking, thresholds, minimum payout, other day, unmeasurable, two trains, injection, fabricated quotes, two attempts then hand-on, failures, P3 checks |
| `tests/test_refund_kb.py` | station lookup, departure window, choice, the KB adapters |
| `tests/test_refunds.py` | delay at the destination: late train, missed connection, cancellation, on time, missing REAL time |
| `tests/test_refund_policy.py` | 59/60/119/120 min, 25 %/50 %, CHF 5.00 and just under (rounded half up), no refund is never paid |
| `tests/test_refund_chat_backend.py` | one conversation per browser tab; failures become `failed` |
| `tests/test_refund_slots.py` | `_slotCheck`: a normalised date or time must be what the passenger's quote says, read without a model |
| `tests/test_chat_ui.py`, `test_chat_form.py`, `test_chat_diagram.py` | the chat shows verdicts unchanged, renders forms, never shows a failure as a refusal; the workflow diagram |
| `tests/test_refund_acceptance.py` | auditor's end-to-end spec: missing facts asked, other day / unknown station → no verdict, claimed delay and injection ignored, every number in a verdict traced to rules or KB |

## Submission zip

Code + README only: no `.venv`, `.env`, caches or `__MACOSX`. `fx/` (84 MB, the
07.11.2026 snapshot) is the knowledge base the system runs on, and
`.model-answers/` holds the recorded model answers for replay. A zip of exactly
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
| `src/refund/` | FrameX refund pipeline: control program `fx/refund.fx`, host, KB adapter, policy, chat backend |
| `src/cli/` | Commands, REPL, progress, and answer formatting |
| `src/data/` | SBB API access |
| `src/ontology/` | Rules, mappings, identities, and fact generation |
| `src/runtime/` | Engine sessions, source loading, validation, refund policy |
| `fx/` | The knowledge base: rules + SBB facts of 07.11.2026 |
| `tests/` | Unit, regression, acceptance, and opt-in snapshot tests |
| `scripts/` | Engine install, Windows dev shell, sample prompt runs |
| `docs/` | User and developer guides |
