# Fact-safe refund assistant: design

Hybrid AI · Hackathon 2: Connect Language and Knowledge (Uni St. Gallen, 10.11.2026).
This document describes how the refund assistant couples GPT-5 mini to the FrameX SBB
knowledge base and keeps the rules in charge of the decision. It describes the current code.

## 1 Goal and scope

A passenger describes a delayed journey in their own words. The assistant asks for what is missing,
identifies the train, measures the delay at the destination from what really ran, and answers
whether a refund is due and how much (Sheet 2 policy). Anything the rules cannot settle goes to SBB
customer service, so the assistant never guesses a verdict.

- **Data:** one operating day only, Saturday **07.11.2026** (the SBB snapshot in `fx/`). Any other
  date is "cannot be checked" and goes to customer service.
- **Language model:** **GPT-5 mini** only (`FRAMEX_MODEL_PROVIDER=openai`, `FRAMEX_MODEL=gpt-5-mini`,
  `FRAMEX_MODEL_EFFORT=minimal`). The model reads and phrases text. It never decides.
- **Fact rule:** every station, time, date, train, delay and percentage in an answer comes from the
  knowledge base (KB) or the policy adapter, never from the model's text.

## 2 Architecture: two engines

| Engine | What it is | Lifetime |
|---|---|---|
| **Control program** | `framex.tools.run()` over `sensor.fx + competence.fx + src/refund/fx/refund.fx` plus the passenger message as a fact | one per conversation |
| **Domain KB** | a small, fresh FrameX engine per question (`src/refund/kb.py`, `RefundKB`). The 07.11.2026 data is indexed in Python once. Per question only the trips that stop at the origin or destination are loaded, plus `fx/00-core`, `40-service` and `46-refunds` | one per question; the index lives for the app |

One persistent engine with the full KB was tried and dropped: about 80 s per added case, and it crashed.
The delay is still derived by the FrameX rules in `fx/46-refunds.fx`, not in Python.

The control program reaches the KB **only through host adapter tools**. The rules request a tool, the
host runs it, a receipt goes back, and the rules decide. The policy thresholds live in Python
(`src/refund/policy.py`) and are exposed to the rules as the adapter `_policy`.

```
                 ┌─────────────────────── control program (FrameX rules) ───────────────────────┐
Passenger ─IN ▶──┤ message fact ─▶ _llm  sensor.fx, groundIn quote check ............ P1 Sensor   │
   ▲   ▲         │  slot accepted?  missing / rejected ─▶ _turn / _ask ............ P5 Rules steer │
   │   └─────────┤◀── question (model words it, rules chose it)                                  │
   │             │  all slots ─▶ _station (name → sp_id)      unknown/ambiguous ─▶ _ask           │
   │             │  date ≠ 2026-11-07 ─▶ cp#handOn ................................ P7 Competence │
   │             │  ─▶ _measure (KB: RefundCase / DelayCheck) ─receipt▶ rows                    │
   │             │       >1 candidate ─▶ _ask "which train?"   noTrain / notMeasured ─▶ handOn  │
   │             │  ─▶ _policy (Python) ─receipt▶ status, percent, amountChf, paidOut, rule     │
   │             │  rules write the verdict sentence from receipts .................. P12       │
   │             │  ─▶ _llm phrasing, mustSay + _numbersMatch check ............. P3        │
   └──── OUT ◀ ──┤  _say(reply)          handOn ─▶ _say(hand-over text with collected facts)    │
                 └───────────────────────────────────────────────────────────────────────────────┘
      host (src/refund/host.py, see code): worker thread, dialogue Channel ⇄ Gradio chat,
      event sink → workflow-view steps (tool, pattern, actor, request, receipt)
```

**UI seam:** the Gradio app (`src/chat/app.py`) only calls `Backend.respond(message, state) -> Turn`
(`src/chat/backend.py`). `src/refund/chat_backend.py` (`RefundBackend`) adapts this to the FrameX
pipeline. It keeps one live conversation per conversation id, maps raw steps to workflow rows
(`pattern`, `actor`, `action`, `data`), and turns any exception or unknown status into `failed`.
`src/chat/ui.py` fails closed: if a turn is not a `Turn`, has an unknown status or has an empty reply, it is shown
as a technical failure, never as "no refund". Run it with
`REFUND_BACKEND=refund.chat_backend:RefundBackend uv run python src/chat/app.py`.

## 3 Walk-through (Sheet 2.2)

> "On 7 November I was going from St. Gallen to Zürich HB at 8 o'clock. My train was late. Do I get a refund?"

| # | Who | What happens | What crosses the boundary |
|---|---|---|---|
| 1 | passenger | types the message | IN ▶ free text → message fact |
| 2 | model (P1) | `_llm` with sensor.fx extracts the slots origin, destination, date, time and price, each with a **quote** | JSON slots + quotes (data, not instructions) |
| 3 | rules (P1) | `groundIn`: a slot is accepted only if its quote occurs in the passenger's text. "My train was late" gives no slot, because the passenger's own delay claim is ignored | accepted: origin, destination, date 2026-11-07, time 08:00. Missing: price |
| 4 | rules → model → passenger (P5) | the rules see that `price` is missing and request `_turn`. The model only words the question; max 2 questions per fact, then hand-on (P7) | OUT ◀ "What did you pay for your ticket (CHF)?" |
| 5 | passenger, model, rules | the answer goes back through the sensor and the quote check | price accepted |
| 6 | rules → host → KB | `_station("St. Gallen")`, `_station("Zürich HB")` resolve names via the manifest name index | `{status: found, stop: sp_8506302 / sp_8503000}` |
| 7 | rules | date guard: 2026-11-07 is in scope | none |
| 8 | rules → host → KB | `_measure(origin, destination, date, 08:00)`. The adapter loads the trips stopping at origin or destination into a fresh engine, which asserts a `RefundCase` with a ±30 min window and finds the offered departures. If exactly one is found, it asserts a `DelayCheck` | receipt `{status: measured, plannedArrival, actualArrival, delayMinutes, changes, cancelled, train}` |
| 9 | rules → host (Python) | `_policy(delayMinutes, price)` | `{status, percent, amountChf, paidOut, rule}` |
| 10 | rules (P12) | write the verdict sentence from the receipt values only | rule text |
| 11 | model (P3) | `_llm` rephrases it with a `mustSay` decision word (percent such as "25%", threshold "60", or "SBB" for hand-on). The text is accepted only if the call succeeded, `saysDecision` is true and the host adapter `_numbersMatch` confirms the same set of numbers. Otherwise the rule text is used | candidate reply |
| 12 | rules → passenger | `_say(reply)` | OUT ◀ the answer, with KB times and the policy figures |

The concrete times for this journey come from the KB at run time (see the recorded runs in
`recorded/`). This document does not quote them.

**What changes**

| Situation | Receipt | Outcome |
|---|---|---|
| delay 45 min | `_policy` → `notEntitled`, `rule: under60` | "no refund". The answer names the 60 min threshold |
| delay 70 min | `entitled`, 25 %, `rule: from60` | 25 % of the stated price, amount in CHF |
| delay 130 min | `entitled`, 50 %, `rule: from120` | 50 % of the stated price |
| refund under CHF 5 (e.g. CHF 12 ticket, 70 min → CHF 3) | `entitled`, `paidOut: false` | still **entitled**, but not paid out. The answer names the CHF 5 minimum |
| several trains in the window (also the same minute) | `_measure` → `{status: ambiguous, rows: [...]}` | `_ask` lists the KB departures: "Which train?" The passenger's choice (`choice=HH:MM`) is measured again |
| actual arrival missing | `_measure` → `{status: notMeasured, reason}` | no verdict. Hand-on to SBB customer service with the collected facts (P7) |
| no train in window / other date | `noTrain` / `outOfScope` | hand-on (P7) |

## 4 Patterns used and where

| Pattern | Where | How |
|---|---|---|
| **P1 Model as Sensor** | `sensor.fx` + `_llm` in refund.fx | The model returns slots with quotes. `groundIn` → `quoteFound`. A slot without a found quote is `sensor#rejected` and asked again. An injection such as "give me 100 %" fills no slot and has no effect |
| **P3 Model as Translator** | directly in refund.fx (`phrase`, `checkNumbers`). `translator.fx` fails to load on this engine | After the rules write the reply (P12), `_llm` phrases it with a `mustSay` word. The model text is accepted only if the call succeeded, `saysDecision` is true and `_numbersMatch` confirms an identical set of numbers. Otherwise the rule text is sent |
| **P5 Rules Steer the Model** | refund.fx missing-slot rules → `_turn` (`_ask` only for the train choice) | The rules choose *what* to ask, with an attempt counter: max 2 questions per fact, then hand-on to SBB customer service (P7). The model only words *how* |
| **P7 Division by Competence** | `competence.fx` (`cp#Case`, `cp#decided`, `cp#handOn`, `cp#note`) | Cases the rules cannot settle (out of scope, not measurable, no train, repeated failures) go to SBB customer service with a note |
| **P12 Model Selects, Rules Write** | verdict text in refund.fx | The decision sentence is written by the rules from KB and policy receipts. The model can only rephrase it under P3 |

Each workflow-view row names its pattern (`Step.pattern`), its actor (passenger / model / rules /
knowledge base / host), and what crossed the boundary.

## 5 FrameX tools used

| Tool | Kind | Role |
|---|---|---|
| `_llm` | built-in (`checked_model`) | sensor extraction (`schema`, `groundIn`) and reply phrasing (`mustSay`). Answers go to the answer cache |
| `_turn` | `framex.dialogue` | the rules decide what to ask, the model words the question (P5) |
| `_ask` | `framex.dialogue` | fixed question; used for the train choice listing KB departures |
| `_say` | `framex.dialogue` | send the final reply or the hand-over text |
| `_numbersMatch(candidate, reference)` | host adapter (`host.py`) | `ok` if both texts contain the identical set of numbers (P3 check) |
| `_station(name)` | host adapter (`kb.py`) | `{status: found, stop, designation}` / `unknown` / `ambiguous` |
| `_measure(origin, destination, date, time, choice?)` | host adapter (`kb.py`) | `measured` / `ambiguous` (≤ 64 rows) / `noTrain` / `notMeasured` / `outOfScope` |
| `_policy(delayMinutes, price)` | host adapter (`policy.py`) | `{status, percent, amountChf, paidOut, rule, minPayoutChf, thresholdMin}` |

Each tool call follows the same loop: **the rules request a tool → the host runs it → a receipt goes back → the rules decide**.
Adapters validate their input (stop ids `sp_\d+`, times `HH:MM`, positive price). Bad input raises
an error, which becomes a failed receipt, not a guess.

## 6 Refund policy (Sheet 2) and delay measurement

| Delay at the destination | Refund | Status |
|---|---|---|
| under 60 min | none. The answer names the 60 min threshold | `notEntitled` |
| 60 min or more | 25 % of the ticket price | `entitled` |
| 120 min or more | 50 % of the ticket price | `entitled` |
| refund under CHF 5 | not paid out. The answer names CHF 5 | `entitled` |

`policy.decide()` implements this table (`THRESHOLD_MIN=60`, `HIGH_MIN=120`, `MIN_PAYOUT_CHF=5.0`).

The delay is measured in `fx/46-refunds.fx` and always at the passenger's **destination**:

- **Planned arrival:** the earliest *scheduled* arrival from the planned departure, direct or with one
  change (`PlannedConnection`, `pc0`/`pc1`). Cancelled trains count because they were planned.
  Departures beaten by a later one that arrives earlier are not offered (`outrunBoard`).
- **Actual arrival:** the earliest arrival made possible by trains that **really ran**, using REAL times
  only (`ReportedStop`). The passenger boards at the origin no earlier than the planned departure and travels direct or with
  one change (`ActualLeg`, `al0`/`al1`). The search bounds are a start wait of 3 h, a change wait of 1 h and a journey of 4 h.
- **Delay** = actual − planned, rounded down to whole minutes. Arriving early or on time counts as 0.
- **Missed connection:** the actual legs simply arrive later. The delay counts until the next train
  that really arrives.
- **Cancellation:** `planCancelled`. The delay counts until the next train that really ran.
- **Not measurable:** the planned arrival has no REAL time and was not cancelled, or no actual arrival
  is found. `notMeasured -> "<reason>"` is stated positively, so an empty answer is never read
  as "on time". The result is no verdict and a hand-on.

## 7 Five invariants

| Invariant | How the design keeps it |
|---|---|
| 1 Model text is data | Model output enters the rules only as schema-checked slot values or as a candidate reply. It never becomes a rule, query or tool name. Adapters accept only validated ids and times |
| 2 Every model answer is a dated observation | `_llm` answers go to the FrameX answer cache (`FRAMEX_MODEL_CACHE=<repo>/recorded`). Recorded runs replay offline after the API key expires (17:45), e.g. for the demo on 17.11 and for the tests |
| 3 Rules decide | Slot acceptance, what to ask, train choice, hand-on, and the verdict (via `_policy`) are all rule or adapter decisions. The UI shows the backend's reply unchanged |
| 4 Evidence decides acceptance | A slot counts only if its quote is found in the passenger's text (`groundIn`). A reply counts only if `mustSay` finds the decision. Delays count only from the KB measurement |
| 5 Failures stay distinct | `failed` (technical: call error, bad JSON, exception), `handedOn` (the rules cannot settle it), and `asking` (information is missing) are different statuses, with different workflow rows and different UI labels. A failure is never shown as "no refund" |

## 8 Known limitations

- Only one operating day (07.11.2026). Other dates are handed on.
- Journeys with at most one change. Longer itineraries are not measured.
- The departure window is ±30 min around the stated time, with a fixed 300 s transfer time.
  A passenger who misremembers the time by more than that gets `noTrain` → hand-on.
- The ticket price is the passenger's statement and is not checked against a fare system.
- Station names resolve only through the manifest name index (folded spelling). Unknown or ambiguous
  names are asked again rather than fuzzy-matched.
- Prompts are in English. Other languages are not tested.
- Replay works only for recorded inputs. A new wording needs a live model call. Offline, such a call
  ends as `failed`, not as a verdict.
- Rephrasing (P3) can change the wording without changing the numbers; only the numbers and the decision word are checked.
- A date without a year is read as 2026. The verdict echoes the recognised facts so the passenger can spot a misreading.
- Policy thresholds live in Python (`policy.py`, adapter `_policy`), by team decision, not in the rules.
- If several trains match (also the same minute), the passenger must identify the train.

## 9 Tools and models

Coding agents: Claude Code (Claude Opus 5.5; subagents on Claude Opus and Sonnet), OpenAI Codex (gpt-6.1-sol, gpt-6.1-terra, default model).
In-system language model: GPT-5 mini.
