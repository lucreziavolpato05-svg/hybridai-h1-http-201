"""Queue bridge for the refund rules. FrameX owns the conversation and decisions.

Each conversation has one tools.run worker and its own dialogue functions/channel.
Python transports requests and receipts; it neither extracts travel facts nor
implements the compensation policy.
"""

from __future__ import annotations

import math
import os
import queue
import re
import threading
import types
from importlib.resources import files
from pathlib import Path

from framex import dialogue, tools
from runtime import query

_ROOT = Path(__file__).resolve().parents[2]
_ENV_LOADED: set[Path] = set()
_ENV_LOCK = threading.Lock()
_STOP = object()
TURN_TIMEOUT = 180.0
IDLE_SECONDS = 900
_FINAL = {"entitled", "notEntitled", "handedOn", "failed"}


def _load_env(path: Path) -> None:
    """Read a simple KEY=VALUE file once, preserving the caller's environment."""
    path = path.resolve()
    with _ENV_LOCK:
        if path in _ENV_LOADED:
            return
        if path.is_file():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, sep, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key.startswith("export "):
                    key = key[7:].strip()
                if not sep or not key or not key.replace("_", "a").isalnum():
                    continue
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                os.environ.setdefault(key, value)
        _ENV_LOADED.add(path)


def _source(text: str) -> str:
    policies = files("framex").joinpath("policies")
    # translator.fx is not loaded (this engine rejects its parameterised
    # requests); refund.fx implements a minimal P3 Model as Translator itself.
    libraries = [policies.joinpath(name).read_text(encoding="utf-8")
                 for name in ("sensor.fx", "competence.fx")]
    program = Path(__file__).with_name("fx").joinpath("refund.fx").read_text(encoding="utf-8")
    # Use FrameX's own literal encoder; passenger text can never become code.
    message = f'"r0"[sensor#text -> {tools.literal(text)}].'
    return "\n".join([*libraries, program, message])


# The dialogue model words rule-chosen questions; it must not drift into another
# language (e.g. German station names) unless the passenger explicitly asks.
_ENGLISH = (" Always write the utterance in English, even if names, the question or the "
            "conversation contain other languages; use another language only if the person "
            "explicitly asked for that language.")


def _dialogue_tools(channel: dialogue.Channel) -> dict:
    """Bind library functions to a private namespace, without swapping CHANNEL.

    Helpers such as conversation()/phrase() must see the same private namespace
    as turn()/ask(). Cloning their globals preserves the actual library code
    while allowing two browser tabs to wait for input at the same time.
    """
    namespace = dict(vars(dialogue), CHANNEL=channel, PHRASE=dialogue.PHRASE + _ENGLISH)
    for name, value in vars(dialogue).items():
        if isinstance(value, types.FunctionType) and value.__globals__ is vars(dialogue):
            bound = types.FunctionType(value.__code__, namespace, value.__name__,
                                       value.__defaults__, value.__closure__)
            bound.__kwdefaults__ = value.__kwdefaults__
            namespace[name] = bound
    return {name: namespace[fn.__name__] for name, fn in dialogue.TOOLS.items()}


def _format(parameters: dict) -> tuple[dict, dict]:
    """Mechanical interpolation of a rule-authored template, with no decisions.

    FrameX concat accepts strings only, so this small adapter formats numerical
    receipt fields (including CHF to two decimals). Templates live in refund.fx.
    """
    template = parameters["template"]
    values = {key: value for key, value in parameters.items()
              if key not in {"template", "decisionTemplate", "prefixTemplate"}}
    output = {"text": template.format_map(values)}
    if "decisionTemplate" in parameters:
        # The rule-authored decision word that a P3 phrasing must contain.
        output["decision"] = parameters["decisionTemplate"].format_map(values)
    if "prefixTemplate" in parameters:
        output["prefix"] = parameters["prefixTemplate"].format_map(values)
    return output, {"mode": "rule template; no model"}


_NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")


def _numbers_match(parameters: dict) -> tuple[dict, dict]:
    """Lexical P3 measurement: does the candidate keep exactly the rule numbers?

    ok is true only when the candidate's set of number tokens (CHF amounts,
    times, percentages, minutes, dates) equals the rule text's set: no number is
    added, changed or dropped. A rule-authored prefix must also remain verbatim
    at the start of the candidate. The rules decide what to do with these facts.
    """
    candidate, reference = parameters["candidate"], parameters["reference"]
    if not isinstance(candidate, str) or not isinstance(reference, str):
        raise ValueError("candidate and reference must be texts")
    found, expected = set(_NUMBER.findall(candidate)), set(_NUMBER.findall(reference))
    prefix_matches = candidate.startswith(parameters.get("requiredPrefix", ""))
    return ({"ok": found == expected and prefix_matches, "prefixMatches": prefix_matches,
             "added": "; ".join(sorted(found - expected)),
             "dropped": "; ".join(sorted(expected - found))},
            {"mode": "lexical number check; no model"})


def _step(actor="host", tool="", pattern="", summary="", request=None,
          receipt=None, ok=True) -> dict:
    return {"actor": actor, "tool": tool, "pattern": pattern, "summary": summary,
            "request": request or {}, "receipt": receipt or {}, "ok": ok}


class _Closed(RuntimeError):
    pass


def _form_answer(form) -> dict | None:
    """A well-formed UI form answer {slot, value}, or None (then the text is sensed).

    Only the transport shape is checked here: whether the slot was asked and
    whether the value is admissible is decided by the rules in refund.fx.
    """
    if not isinstance(form, dict):
        return None
    slot, value = form.get("slot"), form.get("value")
    if not isinstance(slot, str) or isinstance(value, bool):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if not isinstance(value, (str, int, float)):
        return None
    return {"slot": slot, "value": value}


class _Channel(dialogue.Channel):
    def __init__(self, owner):
        super().__init__(read=owner._read)
        self.owner = owner

    def say(self, text):
        with self.owner._lock:
            if self.owner._cancelled.is_set():
                raise _Closed("conversation closed")
            self.transcript.append({"speaker": "bot", "text": text})
            self.owner._output.append(text)


class Conversation:
    """A browser tab's worker, queues and complete public ``trace`` list.

    Instances are created by RefundBot.turn; pass the returned instance back on
    the next turn. A finished instance is retained for inspection, never reused.
    """

    def __init__(self, bot: RefundBot, text: str):
        self.bot = bot
        self.trace: list[dict] = []
        self._lock = threading.RLock()
        with self._lock:
            self.status = "asking"
            self.done = False
        self.inbound: queue.Queue = queue.Queue()
        self._notifications: queue.Queue = queue.Queue()
        self._turn_lock = threading.Lock()
        self._cancelled = threading.Event()
        self._output: list[str] = []
        self._pending: tuple[str, dict] | None = None
        self._form: dict | None = None
        self._rows: list = []
        self.channel = _Channel(self)
        self.channel.transcript.append({"speaker": "user", "text": text})
        self.worker = threading.Thread(target=self._run, args=(text,), daemon=True,
                                       name="refund-framex")

    def _append(self, step):
        with self._lock:
            self.trace.append(step)

    def _read(self, prompt=""):
        if self._cancelled.is_set():
            raise _Closed("conversation closed")
        tool, request = self._pending or ("_ask", {})
        self._append(_step("model" if tool == "_turn" else "rules", tool, "P5 Rules steer",
                           request.get("question", "Waiting for passenger input"), request))
        self._notifications.put("asking")
        try:
            answer = self.inbound.get(timeout=IDLE_SECONDS)
        except queue.Empty:
            self.cancel()
            raise _Closed("conversation idle timeout") from None
        if answer is _STOP or self._cancelled.is_set():
            raise _Closed("conversation closed")
        if isinstance(answer, tuple):  # (label text, form answer) from the UI
            answer, self._form = answer
        return answer

    def form(self) -> dict | None:
        """The pending question as a UI form, from the rules' _turn/_ask request.

        slot and kind are rule fields (missing, formKind); a choice lists the
        rows of the last _measure receipt. None when nothing is being asked.
        """
        with self._lock:
            if self.done or not self._pending:
                return None
            tool, request = self._pending
            if tool not in {"_ask", "_turn"} or "missing" not in request:
                return None
            kind = request.get("formKind", "text")
            form = {"slot": request["missing"], "kind": kind,
                    "label": request.get("question", "")}
            if kind == "choice":
                form["options"] = [{"value": row["departure"],
                                    "label": row.get("label", row["departure"])}
                                   for row in self._rows if "departure" in row]
            elif kind == "number":
                form["min"] = 0
            return form

    def cancel(self):
        """Close an abandoned conversation and wake its worker without a reply."""
        with self._lock:
            if self.done:
                return
            self._cancelled.set()
            self.status, self.done = "failed", True
            self.inbound.put(_STOP)
            self._notifications.put("done")

    def _sink(self, event):
        if self._cancelled.is_set():
            raise _Closed("conversation closed")
        if "workflow" in event:
            pattern = ("P7 Division by competence" if event["workflow"] == "handedOn"
                       else "P12 Model selects, rules write")
            self._append(_step("rules", pattern=pattern,
                               summary=f'Workflow: {event["workflow"]}', receipt=event))
            return
        tool = event["tool"]
        parameters = event.get("parameters", {})
        if tool == "_say" and "wording" in parameters:
            # The rules' P3 acceptance decision, made from the receipts above.
            accepted = parameters["wording"] == "model"
            self._append(_step("rules", pattern="P3 Translator", summary=(
                "Rules accepted the model's phrasing" if accepted else
                "Rules kept the rule-written text"), request={"wording": parameters["wording"]}))
        actor, pattern = {
            "_llm": ("model", "P1 Sensor"),
            "_turn": ("model", "P5 Rules steer"),
            "_ask": ("rules", "P5 Rules steer"),
            "_say": ("rules", "P12 Model selects, rules write"),
            "_station": ("knowledgeBase", "P1 Sensor"),
            "_measure": ("knowledgeBase", "P7 Division by competence"),
            "_policy": ("rules", "P12 Model selects, rules write"),
            "_query": ("rules", "P5 Rules steer"),
            "_format": ("rules", "P12 Model selects, rules write"),
            "_numbersMatch": ("rules", "P3 Translator"),
        }.get(tool, ("host", ""))
        phrasing = tool == "_llm" and "mustSay" in parameters
        if phrasing:
            actor, pattern = "model", "P3 Translator"
        output = event.get("output", {})
        ok = event.get("status") == "succeeded"
        if ok and tool == "_measure":
            with self._lock:
                self._rows = [dict(row) for row in output.get("rows", [])
                              if isinstance(row, dict)]
        if tool == "_say" and event.get("parameters", {}).get("status") == "handedOn":
            pattern = "P7 Division by competence"
        summary = (output.get("text") or output.get("question") or
                   output.get("status") or f"{tool} receipt") if ok else event.get("error", "Tool failed")
        if ok and phrasing:
            summary = f'Phrased the reply (saysDecision: {output.get("saysDecision")})'
        elif ok and tool == "_numbersMatch":
            summary = f'Numbers match the rule text: {output.get("ok")}'
        elif ok and tool == "_llm":
            summary = f'Read {len(output.get("rows", []))} proposed travel facts'
        elif ok and tool == "_query":
            summary = f'Sensor snapshot: {output.get("status", "unknown")}'
        elif ok and tool in {"_station", "_measure", "_policy"}:
            summary = f'{tool}: {output.get("status", "unknown")}'
        receipt = dict(output) if ok else {"error": event.get("error", "Tool failed")}
        # Preserve dated provenance without adding a second shape to the UI API.
        if event.get("evidence"):
            receipt["evidence"] = event["evidence"]
        self._append(_step(actor, tool, pattern, str(summary),
                           dict(parameters), receipt, ok))

    def _adapters(self):
        adapters = {**_dialogue_tools(self.channel), **self.bot._kb_tools,
                    **self.bot._policy_tools, "_format": _format,
                    "_numbersMatch": _numbers_match}
        measure = adapters["_measure"]

        def measured(parameters):
            output, evidence = measure(parameters)
            # Transport metadata for the rules' fold over bounded receipt rows.
            return dict(output, rowCount=len(output.get("rows", []))), evidence

        adapters["_measure"] = measured
        for name in ("_ask", "_turn", "_say"):
            original = adapters[name]

            def bound(parameters, original=original, name=name):
                if self._cancelled.is_set():
                    raise _Closed("conversation closed")
                self._pending = (name, dict(parameters))
                self._form = None
                if name == "_say":
                    # wording is trace metadata for the P3 step, not for the channel.
                    parameters = {k: v for k, v in parameters.items() if k != "wording"}
                output, evidence = original(parameters)
                if name == "_say":
                    output = dict(output, status=parameters["status"])
                elif "answer" in output:
                    # Every answer receipt says whether it came from a UI form;
                    # the rules sense only form false and validate form values.
                    form, self._form = self._form, None
                    output = dict(output, form=form is not None)
                    if form is not None:
                        output.update(formSlot=form["slot"], formValue=form["value"])
                return output, evidence

            adapters[name] = bound
        return adapters

    def _run(self, text):
        try:
            result = tools.run(_source(text), binary=query.binary(), max_actions=200,
                               adapters=self._adapters(), sink=self._sink)
            if result["status"] not in _FINAL:
                raise RuntimeError(f'FrameX stopped without a final reply ({result["status"]})')
            if result["status"] == "failed":
                self._fail("The final reply could not be delivered")
                return
            with self._lock:
                if not self.done and not self._cancelled.is_set():
                    self.status, self.done = result["status"], True
        except Exception as exc:
            if not self._cancelled.is_set():
                self._fail(str(exc))
        finally:
            self._notifications.put("done")

    def _fail(self, error):
        with self._lock:
            if self.done:
                return
            self._cancelled.set()
            self.status, self.done = "failed", True
            self.inbound.put(_STOP)
            self._output.append("I could not complete the check. Please contact SBB customer service.")
            self.trace.append(_step(summary=error, receipt={"error": error}, ok=False))


class RefundBot:
    def __init__(self, kb=None, *, cache_dir=_ROOT / ".model-answers", env_file=_ROOT / ".env"):
        _load_env(Path(env_file))
        for key, value in {"FRAMEX_MODEL_PROVIDER": "openai", "FRAMEX_MODEL": "gpt-5-mini",
                           "FRAMEX_MODEL_EFFORT": "minimal", "FRAMEX_MODEL_CACHE": str(cache_dir)}.items():
            os.environ.setdefault(key, value)
        # Import lazily so test adapters can use exactly the production contract.
        from refund.kb import RefundKB, tools as kb_tools
        from refund.policy import TOOLS as POLICY_TOOLS

        self.kb = RefundKB() if kb is None else kb
        self._kb_tools = kb_tools(self.kb)
        self._policy_tools = dict(POLICY_TOOLS)

    def turn(self, state, text: str, *, form=None) -> dict:
        """One passenger message. form={"slot", "value"} answers the pending
        question from a UI form: the rules receive it without a model call."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if state is not None and not isinstance(state, Conversation):
            raise TypeError("state must be None or the returned Conversation")
        fresh = state is None or state.done
        conversation = Conversation(self, text) if fresh else state
        if conversation.bot is not self:
            raise ValueError("state belongs to another RefundBot")
        # A form answers a pending question; a new conversation is always sensed.
        answer = None if fresh else _form_answer(form)
        with conversation._turn_lock:
            # A second request from the same tab may have queued behind a turn
            # that has just finished. It too must start a fresh conversation.
            if not fresh and conversation.done:
                return self.turn(None, text)
            with conversation._lock:
                start, output_start = len(conversation.trace), len(conversation._output)
            if answer is None:
                conversation._append(_step("passenger", summary=text, request={"text": text}))
            else:
                conversation._append(_step(
                    "passenger", pattern="P5 Rules steer",
                    summary=f'Form answer: {answer["slot"]} = {answer["value"]} (no model call)',
                    request={"text": text, "form": answer}))
            if fresh:
                conversation.worker.start()
            else:
                conversation.inbound.put(text if answer is None else (text, answer))
            try:
                notice = conversation._notifications.get(timeout=TURN_TIMEOUT)
                with conversation._lock:
                    if not conversation.done and notice == "asking":
                        conversation.status = "asking"
            except queue.Empty:
                with conversation._lock:
                    if not conversation.done:
                        conversation._fail(f"Refund check timed out after {TURN_TIMEOUT:g} seconds")
            with conversation._lock:
                out = {"reply": "\n\n".join(conversation._output[output_start:]),
                       "status": conversation.status, "steps": list(conversation.trace[start:]),
                       "done": conversation.done, "state": conversation}
                if conversation.status == "asking" and not conversation.done:
                    asked = conversation.form()
                    if asked is not None:
                        out["form"] = asked
                return out
