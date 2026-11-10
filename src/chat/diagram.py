"""Architecture diagram from the team's FlightMode sheet (2.1), drawn as SVG.

Passenger, language model (GPT-5 mini), knowledge base (FrameX rules + SBB data)
and SBB customer service, with the numbered arrows of the sheet:

  1 query                     passenger -> model              (passenger flow)
  2 P3 Model as Translator    model -> knowledge base
  3 P5 ask for missing facts  knowledge base -> model
  4 question to passenger     model -> passenger              (P5: the rules chose it)
  5 additional info           passenger -> model              (passenger flow)
  6 P1 Model as Sensor        model -> knowledge base
  7 P7 Division by Competence knowledge base: answer found, or escalate
  8 answer to the passenger   knowledge base -> passenger     (passenger flow)
  9 hand-over                 knowledge base -> SBB customer service (P7)

Each pattern has its own colour; passenger traffic is SBB red. The arrows and
patterns used so far in the conversation light up in their colour; an arrow
that fired more than once shows how often (e.g. "x3"), each chip its step count. The diagram only
reads the trace: it never changes what the backend decided.
"""
from __future__ import annotations

import json
import re
from html import escape

from .backend import ASKING, ENTITLED, FAILED, HANDED_ON, NOT_ENTITLED

PATTERNS = {
    "P1": "Model as Sensor",
    "P3": "Model as Translator",
    "P5": "Rules Steer the Model",
    "P7": "Division by Competence",
}
# Patterns the backend may also report; their chip appears once they are used.
EXTRA_PATTERNS = {"P12": "Model selects, rules write"}

# edge id -> (path, number circle x, y, number, label, label side, colour kind)
EDGES = {
    "e1": ("M 232 176 C 380 100, 520 62, 628 58", 430, 70, "1", "query", "start", "flow"),
    "e2": ("M 744 128 L 744 292", 744, 252, "2", "P3", "start", "p3"),
    "e3": ("M 828 292 L 828 128", 828, 210, "3", "P5 ask for facts", "start", "p5"),
    "e4": ("M 628 92 C 500 110, 380 150, 232 196", 318, 150, "4", "question", "start", "p5"),
    "e5": ("M 232 228 C 400 210, 540 160, 640 128", 462, 214, "5", "additional info", "start", "flow"),
    "e6": ("M 662 128 L 662 292", 662, 210, "6", "P1 sensor", "end", "p1"),
    "e7": ("M 860 330 C 920 330, 920 380, 860 380", 892, 420, "7", "P7 decide or escalate", "end", "p7"),
    "e8": ("M 628 350 C 480 340, 330 280, 232 238", 410, 296, "8", "answer", "start", "flow"),
    "e9": ("M 628 370 C 480 400, 330 420, 232 420", 430, 392, "9", "hand-over", "start", "p7"),
}

# Small line icons (24x24 grid), drawn in the node's corner.
ICONS = {
    "passenger": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
    "model": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>'
             '<path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
    "kb": '<ellipse cx="12" cy="5.5" rx="7" ry="2.5"/><path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13"/>'
          '<path d="M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/>',
    "service": '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="13" width="4" height="6" rx="1.5"/>'
               '<rect x="17" y="13" width="4" height="6" rx="1.5"/><path d="M19 19c0 1.5-2 2.5-5 2.5"/>',
}

NODES = {
    "passenger": (40, 166, 192, 92, "Passenger", "asks in their own words"),
    "model": (628, 30, 232, 98, "Language model", "GPT-5 mini"),
    "kb": (628, 292, 232, 104, "Knowledge base", "FrameX facts + rules · SBB 07.11.2026"),
    "service": (40, 374, 192, 88, "SBB customer service", "settles what rules cannot"),
}


_CODE = re.compile(r"^P(\d+)\b")
KB_TOOLS = {"_station", "_measure", "_policy"}
QUESTION_TOOLS = {"_turn", "_ask"}
VERDICTS = {ENTITLED, NOT_ENTITLED}
# Which nodes each arrow touches.
ENDS = {"e1": ("passenger", "model"), "e2": ("model", "kb"), "e3": ("kb", "model"),
        "e4": ("model", "passenger"), "e5": ("passenger", "model"), "e6": ("model", "kb"),
        "e7": ("kb",), "e8": ("kb", "passenger"), "e9": ("kb", "service")}


def _code(pattern) -> str | None:
    """'P7 Competence' -> 'P7'; '-' or '' -> None."""
    m = _CODE.match(str(pattern or "").strip())
    return f"P{int(m.group(1))}" if m else None


def _data(raw) -> dict:
    """The trace row's data column (JSON text from the UI, or a dict) as a dict."""
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else {}
    except ValueError:
        value = {}
    return value if isinstance(value, dict) else {}


def trace_counts(rows: list, status: str | None) -> tuple[dict, set, dict]:
    """(edge -> times fired, lit nodes, pattern code -> step count) for the whole conversation.

    rows: the UI's trace rows [turn, time, pattern, actor, action, data]. Every count comes from
    real rows; the final status only adds the arrow that ended the turn when no row shows it.
    """
    edges: dict = {}
    nodes, patterns = set(), {}

    def fire(eid, n=1):
        if n > 0:
            edges[eid] = edges.get(eid, 0) + n

    passenger_turns = []
    for row in rows or []:
        turn, _, pattern, actor, _, raw = (list(row) + [None] * 6)[:6]
        code = _code(pattern)
        if code:
            patterns[code] = patterns.get(code, 0) + 1
        data = _data(raw)
        tool = data.get("tool") or ""
        request = data.get("request") if isinstance(data.get("request"), dict) else {}
        if actor == "passenger":
            nodes.add("passenger")
            if turn not in passenger_turns:  # UI row and backend row of one message count once
                passenger_turns.append(turn)
            continue
        if actor == "model":
            nodes.add("model")
        elif actor in ("rules", "knowledge base"):
            nodes.add("kb")
        if tool in QUESTION_TOOLS:
            if "receipt" not in data:  # the question itself; the receipt row is the answer coming back
                fire("e3")
                fire("e4")
        elif tool in KB_TOOLS:
            fire("e7")
        elif tool == "_say":
            said = request.get("status")
            if said in VERDICTS:
                fire("e8")
            elif said == HANDED_ON:
                fire("e9")
        elif code == "P3":
            fire("e2")
        elif code == "P1" and tool in ("", "_llm"):
            fire("e6")
        elif not tool and code == "P5" and actor in ("rules", "model"):
            fire("e3")
        elif not tool and code == "P7" and actor != "host":
            fire("e7")
    if passenger_turns:
        fire("e1")
        fire("e5", len(passenger_turns) - 1)
    # The status the turn ended with is real too: show its arrow if no row carried it.
    if status == ASKING and "e4" not in edges:
        fire("e4")
    elif status in VERDICTS and "e8" not in edges:
        fire("e8")
    elif status in (HANDED_ON, FAILED):
        if "e9" not in edges:
            fire("e9")
        if "e7" not in edges:
            fire("e7")
    for eid in edges:
        nodes.update(ENDS[eid])
    return edges, nodes, patterns


def lit_from_trace(rows: list, status: str | None) -> tuple[set, set, set]:
    """(lit edges, lit nodes, used patterns) for the conversation so far."""
    edges, nodes, patterns = trace_counts(rows, status)
    return set(edges), nodes, set(patterns)


def _chip(code: str, name: str, count: int) -> str:
    steps = f" · {count} step{'' if count == 1 else 's'}" if count else ""
    return (f'<span class="chip k-{code.lower()}{" lit" if count else ""}" data-pattern="{code}">'
            f'<i class="dot"></i><b>{code}</b> {escape(name)}{steps}</span>')


def render_diagram(rows: list | None = None, status: str | None = None) -> str:
    edges, nodes, patterns = trace_counts(rows or [], status)
    parts = []
    for eid, (path, cx, cy, num, label, side, kind) in EDGES.items():
        times = edges.get(eid, 0)
        on = times > 0
        tx = cx + 14 if side == "start" else cx - 14
        text = f"{label} ×{times}" if times > 1 else label
        parts.append(
            f'<g class="edge k-{kind}{" lit" if on else ""}" data-edge="{eid}" data-count="{times}">'
            f'<path d="{path}" marker-end="url(#arrow-{kind if on else "idle"})"/>'
            f'<circle cx="{cx}" cy="{cy}" r="9"/><text class="num" x="{cx}" y="{cy + 4}">{num}</text>'
            f'<text class="elabel" x="{tx}" y="{cy + 4}" text-anchor="{side}">{escape(text)}</text></g>')
    for nid, (x, y, w, h, title, sub) in NODES.items():
        parts.append(
            f'<g class="node{" lit" if nid in nodes else ""}" data-node="{nid}">'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12"/>'
            f'<g class="icon" transform="translate({x + 12} {y + 10}) scale(0.75)">{ICONS[nid]}</g>'
            f'<text class="ntitle" x="{x + w / 2}" y="{y + h / 2 + 2}">{escape(title)}</text>'
            f'<text class="nsub" x="{x + w / 2}" y="{y + h / 2 + 21}">{escape(sub)}</text></g>')
    markers = "".join(
        f'<marker id="arrow-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="ahead ah-{k}"/></marker>'
        for k in ("idle", "flow", "p1", "p3", "p5", "p7"))
    shown = dict(PATTERNS)
    for code in sorted(patterns, key=lambda c: int(c[1:])):
        shown.setdefault(code, EXTRA_PATTERNS.get(code, "pattern"))
    chips = "".join(_chip(code, name, patterns.get(code, 0)) for code, name in shown.items())
    chips += '<span class="chip k-flow legend"><i class="dot"></i>passenger traffic</span>'
    counter = (f'<div class="pattern-count" data-patterns-used="{len(patterns)}">'
               f'Patterns used in this conversation: <b>{len(patterns)}</b></div>')
    return (
        '<div class="sbb-diagram">'
        '<svg viewBox="0 0 960 470" role="img" aria-label="System architecture: passenger, '
        f'language model, knowledge base, customer service"><defs>{markers}</defs>'
        + "".join(parts) + f'</svg>{counter}<div class="chips">{chips}</div></div>')


# Icons for the theme toggle and buttons, as CSS data URIs (white line icons).
def _icon(paths: str, colour: str = "white") -> str:
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='{colour}' "
           f"stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{paths}</svg>")
    return "url(\"data:image/svg+xml;utf8," + svg.replace("#", "%23").replace('"', "'") + "\")"


MOON = _icon("<path d='M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z'/>")
SUN = _icon("<circle cx='12' cy='12' r='4.5'/><path d='M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4"
            "M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4'/>")
SEND = _icon("<path d='M22 2L11 13'/><path d='M22 2l-7 20-4-9-9-4z'/>")
RESET_LIGHT = _icon("<path d='M3 12a9 9 0 1 0 3-6.7L3 8'/><path d='M3 3v5h5'/>", "#444")
RESET_DARK = _icon("<path d='M3 12a9 9 0 1 0 3-6.7L3 8'/><path d='M3 3v5h5'/>", "#ddd")

CSS = """
.sbb-diagram, .status-pill, #sbb-header, .card, #form-card {
  --sbb-red: #EB0000; --sbb-red-dark: #C60018;
  --dg-bg: #FFFFFF; --dg-node: #F7F7F8; --dg-stroke: #E1E1E4; --dg-text: #18181B;
  --dg-sub: #71717A; --dg-edge: #D4D4D8; --dg-label: #52525B; --dg-node-lit: #FFFFFF;
  --k-flow: #EB0000; --k-p1: #0A6CFF; --k-p3: #7C3AED; --k-p5: #E08A00; --k-p7: #009B80;
  --card-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 16px rgba(0,0,0,.06);
}
.dark .sbb-diagram, .dark .status-pill, .dark #sbb-header, .dark .card, .dark #form-card {
  --dg-bg: #17171A; --dg-node: #212126; --dg-stroke: #33333A; --dg-text: #F4F4F5;
  --dg-sub: #A1A1AA; --dg-edge: #3F3F46; --dg-label: #A1A1AA; --dg-node-lit: #2A2A31;
  --k-flow: #FF4D4D; --k-p1: #5B9BFF; --k-p3: #A78BFA; --k-p5: #FBBF24; --k-p7: #2DD4B0;
  --card-shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
}
.gradio-container { max-width: 1440px !important; }

/* Gradio scopes custom CSS under .gradio-container and rewrites a selector that starts at the page body into one
   that never matches, so dark rules here are written as `.dark X` (Gradio puts .dark on <body>). */
/* ---- header bar with title and the round theme toggle ---- */
#sbb-header { background: linear-gradient(100deg, #EB0000 0%, #C60018 100%); border-radius: 16px;
  padding: 10px 14px 10px 20px; align-items: center; box-shadow: var(--card-shadow); border: none; gap: 8px; }
#sbb-header > * { background: transparent !important; border: none !important; }
.sbb-title { display: flex; align-items: center; gap: 14px; }
.sbb-title h1 { color: #FFFFFF !important; margin: 0; font: 700 21px/1.2 Helvetica, Arial, sans-serif;
  letter-spacing: -.01em; }
.sbb-title p { color: rgba(255,255,255,.85) !important; margin: 2px 0 0; font: 13.5px Helvetica, Arial, sans-serif; }
.sbb-logo { width: 40px; height: 40px; flex: none; border-radius: 12px; background: rgba(255,255,255,.16);
  display: grid; place-items: center; }
#theme-toggle { min-width: 42px !important; max-width: 42px !important; height: 42px; padding: 0 !important;
  border-radius: 50% !important; border: 1px solid rgba(255,255,255,.35) !important;
  background: rgba(255,255,255,.14) """ + MOON + """ center / 20px no-repeat !important;
  color: transparent !important; font-size: 0 !important; box-shadow: none !important;
  transition: background-color .2s, transform .3s; flex: none !important; margin-left: auto; }
#theme-toggle:hover { background-color: rgba(255,255,255,.26) !important; transform: rotate(-20deg); }
.dark #theme-toggle { background-image: """ + SUN + """ !important; }

/* ---- buttons with icons ---- */
#send-btn::before { content: ""; width: 16px; height: 16px; margin-right: 8px; display: inline-block;
  background: """ + SEND + """ center / contain no-repeat; vertical-align: -2px; }
#reset-btn::before { content: ""; width: 15px; height: 15px; margin-right: 8px; display: inline-block;
  background: """ + RESET_LIGHT + """ center / contain no-repeat; vertical-align: -2px; }
.dark #reset-btn::before { background-image: """ + RESET_DARK + """; }
#send-btn, #reset-btn { border-radius: 12px !important; }

/* ---- the backend's form under the chat ---- */
#form-card { border-radius: 16px !important; border: 1px solid var(--dg-stroke, #E1E1E4) !important;
  padding: 12px 14px !important; box-shadow: var(--card-shadow) !important; }
#form-label p { margin: 0 0 6px; font-weight: 600; }
#form-choice { flex-wrap: wrap; gap: 8px; }
#form-choice button { border-radius: 999px !important; padding: 7px 14px !important; min-width: 0 !important;
  flex: none !important; }
.status-pill.working { opacity: .8; }
#form-send { border-radius: 12px !important; min-width: 110px; }
/* ---- cards ---- */
.card { border-radius: 16px !important; box-shadow: var(--card-shadow) !important; }
.status-pill { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px;
  font: 600 13px Helvetica, Arial, sans-serif; background: var(--dg-node); color: var(--dg-text);
  border: 1px solid var(--dg-stroke); }
.status-pill i { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.status-pill.asking { color: var(--k-p5); } .status-pill.entitled { color: var(--k-p7); }
.status-pill.notEntitled { color: var(--dg-text); } .status-pill.handedOn, .status-pill.failed { color: var(--k-flow); }
.status-pill span { color: var(--dg-text); }

/* ---- diagram ---- */
.sbb-diagram { background: var(--dg-bg); border: 1px solid var(--dg-stroke); border-radius: 16px; padding: 10px 12px;
  box-shadow: var(--card-shadow); }
.sbb-diagram svg { width: 100%; height: auto; display: block; font-family: Helvetica, Arial, sans-serif; }
.sbb-diagram .node rect { fill: var(--dg-node); stroke: var(--dg-stroke); stroke-width: 1.2; transition: all .35s; }
.sbb-diagram .node .icon { fill: none; stroke: var(--dg-sub); stroke-width: 1.8; stroke-linecap: round;
  stroke-linejoin: round; transition: stroke .35s; }
.sbb-diagram .ntitle { fill: var(--dg-text); font-size: 15.5px; font-weight: 700; text-anchor: middle; }
.sbb-diagram .nsub { fill: var(--dg-sub); font-size: 11.5px; text-anchor: middle; }
.sbb-diagram .node.lit rect { fill: var(--dg-node-lit); stroke: var(--dg-text); stroke-width: 1.8;
  filter: drop-shadow(0 4px 12px rgba(0,0,0,.18)); }
.sbb-diagram .node.lit .icon { stroke: var(--sbb-red); }
.sbb-diagram .edge { color: var(--dg-edge); }
.sbb-diagram .edge path { fill: none; stroke: var(--dg-edge); stroke-width: 1.8; transition: stroke .35s; }
.sbb-diagram .edge circle { fill: var(--dg-bg); stroke: var(--dg-edge); stroke-width: 1.4; }
.sbb-diagram .num { fill: var(--dg-label); font-size: 11px; font-weight: 700; text-anchor: middle; }
.sbb-diagram .elabel { fill: var(--dg-label); font-size: 12px; paint-order: stroke;
  stroke: var(--dg-bg); stroke-width: 5px; stroke-linejoin: round; }
.sbb-diagram .k-flow { color: var(--k-flow); } .sbb-diagram .k-p1 { color: var(--k-p1); }
.sbb-diagram .k-p3 { color: var(--k-p3); } .sbb-diagram .k-p5 { color: var(--k-p5); }
.sbb-diagram .k-p7 { color: var(--k-p7); }
.sbb-diagram .ah-idle { fill: var(--dg-edge); } .sbb-diagram .ah-flow { fill: var(--k-flow); }
.sbb-diagram .ah-p1 { fill: var(--k-p1); } .sbb-diagram .ah-p3 { fill: var(--k-p3); }
.sbb-diagram .ah-p5 { fill: var(--k-p5); } .sbb-diagram .ah-p7 { fill: var(--k-p7); }
.sbb-diagram .edge.lit path { stroke: currentColor; stroke-width: 3.2; stroke-dasharray: 9 6;
  animation: dg-flow .8s linear infinite; filter: drop-shadow(0 0 5px currentColor); }
.sbb-diagram .edge.lit circle { fill: currentColor; stroke: currentColor; }
.sbb-diagram .edge.lit .num { fill: #FFFFFF; }
.sbb-diagram .edge.lit .elabel { fill: currentColor; font-weight: 700; }
@keyframes dg-flow { to { stroke-dashoffset: -15; } }
.sbb-diagram .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.sbb-diagram .chip { display: inline-flex; align-items: center; gap: 6px; font: 12.5px Helvetica, Arial, sans-serif;
  padding: 4px 11px 4px 9px; border-radius: 999px; border: 1px solid var(--dg-stroke); color: var(--dg-sub);
  background: var(--dg-node); transition: all .35s; }
.sbb-diagram .chip .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.sbb-diagram .chip.k-flow .dot { background: var(--k-flow); } .sbb-diagram .chip.k-p1 .dot { background: var(--k-p1); }
.sbb-diagram .chip.k-p3 .dot { background: var(--k-p3); } .sbb-diagram .chip.k-p5 .dot { background: var(--k-p5); }
.sbb-diagram .chip.k-p7 .dot { background: var(--k-p7); }
.sbb-diagram .chip:not(.lit) { color: var(--dg-sub); }
.sbb-diagram .chip.lit.k-p1 { color: var(--k-p1); } .sbb-diagram .chip.lit.k-p3 { color: var(--k-p3); }
.sbb-diagram .chip.lit.k-p5 { color: var(--k-p5); } .sbb-diagram .chip.lit.k-p7 { color: var(--k-p7); }
.sbb-diagram .chip.lit { background: currentColor; border-color: currentColor;
  box-shadow: 0 0 12px currentColor; animation: dg-pulse 1.4s ease-in-out infinite; }
.sbb-diagram .chip.lit b, .sbb-diagram .chip.lit { -webkit-text-fill-color: #FFFFFF; }
.sbb-diagram .chip.lit .dot { background: #FFFFFF !important; }
.sbb-diagram .chip.legend { border-style: dashed; }
.sbb-diagram .chip.lit.k-p12 { color: var(--dg-label); }
.sbb-diagram .pattern-count { margin-top: 8px; font: 13px Helvetica, Arial, sans-serif; color: var(--dg-sub); }
.sbb-diagram .pattern-count b { color: var(--dg-text); }
@keyframes dg-pulse { 50% { box-shadow: 0 0 3px currentColor; } }
@media (prefers-reduced-motion: reduce) {
  .sbb-diagram .edge.lit path, .sbb-diagram .chip.lit { animation: none; }
}
"""

# Toggle Gradio's dark mode (Gradio puts the `dark` class on <body>) and remember it.
TOGGLE_JS = """
() => {
  const dark = document.body.classList.toggle('dark');
  try { localStorage.setItem('sbb-theme', dark ? 'dark' : 'light'); } catch (e) {}
}
"""

# On load: apply a remembered choice.
LOAD_JS = """
() => {
  try {
    const t = localStorage.getItem('sbb-theme');
    if (t === 'dark') document.body.classList.add('dark');
    if (t === 'light') document.body.classList.remove('dark');
  } catch (e) {}
}
"""

HEADER_HTML = """
<div class="sbb-title">
  <div class="sbb-logo"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF"
    stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <rect x="5" y="3" width="14" height="14" rx="3"/><path d="M5 10h14"/>
    <circle cx="9" cy="13.5" r=".6" fill="#FFFFFF"/><circle cx="15" cy="13.5" r=".6" fill="#FFFFFF"/>
    <path d="M8 21l2-4M16 21l-2-4"/></svg></div>
  <div><h1>Delay refund assistant</h1>
  <p>Describe your journey on Saturday 7 November 2026 in your own words.</p></div>
</div>
"""


def status_pill(status: str | None, label: str) -> str:
    """Small coloured status badge under the chat."""
    if not status or not label:
        return ""
    return f'<div class="status-pill {escape(status)}"><i></i><span>{escape(label)}</span></div>'
