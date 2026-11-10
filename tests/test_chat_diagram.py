"""The workflow diagram lights up exactly the arrows and patterns the trace shows, with real counts."""
from __future__ import annotations

import json
import re

from chat.backend import ASKING, ENTITLED, FAILED, HANDED_ON, Step, Turn
from chat.diagram import EDGES, PATTERNS, lit_from_trace, render_diagram, trace_counts
from chat.ui import handle_message, new_session


def rows(turn, *steps):
    return [[turn, "12:00:00", p, a, "x", ""] for p, a in steps]


def test_nothing_lit_before_the_first_message():
    html = render_diagram()
    assert " lit" not in html
    assert all(f'data-edge="{e}"' in html for e in EDGES)
    assert all(f'data-pattern="{p}"' in html for p in PATTERNS)


def test_first_message_with_missing_facts_lights_query_sensor_steer_and_question():
    r = rows(1, ("-", "passenger"), ("P1 Sensor", "model"), ("P5 Rules steer", "rules"))
    edges, nodes, patterns = lit_from_trace(r, ASKING)
    assert edges == {"e1", "e6", "e3", "e4"}
    assert patterns == {"P1", "P5"}
    assert {"passenger", "model", "kb"} <= nodes


def test_follow_up_message_uses_additional_info_arrow_not_query():
    r = rows(1, ("-", "passenger")) + rows(2, ("-", "passenger"), ("P1 Sensor", "model"))
    edges, _, _ = trace_counts(r, ASKING)
    assert edges["e1"] == 1 and edges["e5"] == 1, "only the first message is the query"


def test_earlier_turns_stay_lit_for_the_whole_conversation():
    r = rows(1, ("-", "passenger"), ("P3 Translator", "model")) + rows(2, ("-", "passenger"))
    edges, _, patterns = lit_from_trace(r, ASKING)
    assert "P3" in patterns and {"e1", "e2", "e5"} <= edges


def test_verdict_lights_the_answer_arrow():
    r = rows(3, ("-", "passenger"), ("P3 Translator", "model"), ("-", "knowledge base"))
    edges, nodes, patterns = lit_from_trace(r, ENTITLED)
    assert "e8" in edges and "e2" in edges and "e9" not in edges
    assert "service" not in nodes and patterns == {"P3"}


def test_hand_over_and_failure_light_customer_service_and_p7():
    for status in (HANDED_ON, FAILED):
        edges, nodes, patterns = lit_from_trace(rows(1, ("-", "passenger"), ("P7 Competence", "host")), status)
        assert {"e7", "e9"} <= edges and "service" in nodes and "P7" in patterns
        assert "e8" not in edges, "a hand-over is not an answer"


def test_lit_classes_appear_in_the_svg():
    html = render_diagram(rows(1, ("-", "passenger"), ("P1 Sensor", "model")), ASKING)
    lit = set(re.findall(r'class="edge k-\w+ lit" data-edge="(e\d)"', html))
    assert lit == {"e1", "e6", "e4"}
    assert 'class="chip k-p1 lit" data-pattern="P1"' in html
    assert 'class="chip k-p3" data-pattern="P3"' in html


def test_each_pattern_has_its_own_colour():
    from chat.diagram import CSS, EDGES
    kinds = {e[6] for e in EDGES.values()}
    assert kinds == {"flow", "p1", "p3", "p5", "p7"}
    for k in kinds:
        assert f"--k-{k}:" in CSS, f"no colour for {k}"
    light = CSS.split(".dark .sbb-diagram")[0]
    colours = {light.split(f"--k-{k}:")[1].split(";")[0].strip() for k in kinds}
    assert len(colours) == len(kinds), "two kinds share a colour"


def test_lit_arrow_uses_its_pattern_marker():
    html = render_diagram(rows(1, ("-", "passenger"), ("P1 Sensor", "model")), ASKING)
    assert 'data-edge="e6" data-count="1"><path d="M 662 128 L 662 292" marker-end="url(#arrow-p1)"' in html
    assert 'marker-end="url(#arrow-idle)"' in html


def test_status_pill_escapes_and_hides_when_empty():
    from chat.diagram import status_pill
    assert status_pill(None, "") == ""
    assert "&lt;b&gt;" in status_pill("asking", "<b>x</b>")


def test_labels_are_escaped():
    html = render_diagram()
    assert "<script" not in html


def test_diagram_follows_a_real_ui_turn():
    class B:
        def respond(self, message, state):
            return Turn("Which train?", ASKING, {}, [Step("P5 Rules steer", "rules", "two trains", None)])
    _, s = handle_message("St. Gallen to Zürich HB at 8", [], new_session(), B())
    edges, _, patterns = lit_from_trace(s["trace_rows"], s["status"])
    assert {"e1", "e3", "e4"} <= edges and patterns == {"P5"}


def test_dark_rules_avoid_body_selectors_that_gradio_cannot_scope():
    from chat.diagram import CSS
    assert "body.dark" not in CSS and "body {" not in CSS
    assert ".dark #theme-toggle" in CSS


def row(turn, pattern, actor, tool=None, **data):
    payload = json.dumps({"tool": tool, **data}) if tool else ""
    return [turn, "12:00:00", pattern, actor, tool or "x", payload]


# A real-shaped conversation: two passenger turns, the rules ask once, then answer.
TRACE = [
    row(1, "-", "passenger"),
    row(1, "-", "passenger"),  # the backend's own passenger step for the same message
    row(1, "P1 Sensor", "model", "_llm", receipt={"rows": []}),
    row(1, "P1 Sensor", "knowledge base", "_station", receipt={"status": "ok"}),
    row(1, "P5 Rules steer", "rules", "_query", receipt={"status": "partial"}),
    row(1, "P5 Rules steer", "model", "_turn", request={"question": "Which train?"}),
    row(2, "P5 Rules steer", "passenger", None),
    row(2, "P5 Rules steer", "model", "_turn", request={"question": "Which train?"}, receipt={"answer": "IC 1"}),
    row(2, "P1 Sensor", "model", "_llm", receipt={"rows": []}),
    row(2, "P7 Division by competence", "knowledge base", "_measure", receipt={"status": "ok"}),
    row(2, "P12 Model selects, rules write", "rules", "_policy", receipt={"status": "ok"}),
    row(2, "P3 Translator", "model", "_llm", request={"mustSay": ["CHF 4.20"]}),
    row(2, "P3 Translator", "rules", "_numbersMatch", receipt={"ok": True}),
    row(2, "P12 Model selects, rules write", "rules", "_say", request={"status": "entitled"}),
]


def test_synthetic_trace_lights_only_the_steps_that_happened_with_counts():
    edges, nodes, patterns = trace_counts(TRACE, ENTITLED)
    assert edges == {"e1": 1, "e5": 1, "e6": 2, "e3": 1, "e4": 1, "e7": 3, "e2": 2, "e8": 1}
    assert "e9" not in edges and "service" not in nodes
    assert patterns == {"P1": 3, "P5": 4, "P7": 1, "P12": 2, "P3": 2}


def test_counts_and_pattern_counter_show_in_the_html():
    html = render_diagram(TRACE, ENTITLED)
    assert "P1 sensor ×2" in html and "P3 ×2" in html and "query ×" not in html
    assert "Patterns used in this conversation: <b>5</b>" in html
    assert "<b>P1</b> Model as Sensor · 3 steps</span>" in html
    assert "<b>P7</b> Division by Competence · 1 step</span>" in html
    assert 'class="chip k-p12 lit" data-pattern="P12"' in html


def test_unused_patterns_stay_dimmed_and_p7_variants_group():
    r = [row(1, "-", "passenger"), row(1, "P7 Competence", "rules"),
         row(1, "P7 Division by competence", "knowledge base", "_measure", receipt={})]
    _, _, patterns = trace_counts(r, ASKING)
    assert patterns == {"P7": 2}
    html = render_diagram(r, ASKING)
    assert "Patterns used in this conversation: <b>1</b>" in html
    assert 'class="chip k-p1" data-pattern="P1"' in html and "P12" not in html


def test_empty_trace_is_all_dimmed_with_counter_zero():
    for html in (render_diagram(), render_diagram([], None)):
        assert " lit" not in html
        assert "Patterns used in this conversation: <b>0</b>" in html
        assert "×" not in html and "step" not in html
    assert trace_counts([], None) == ({}, set(), {})
