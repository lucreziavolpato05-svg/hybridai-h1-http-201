"""Architecture diagram from the team's FlightMode sheet (2.1), drawn as SVG.

Passenger, language model (GPT-5 mini), knowledge base (FrameX rules + SBB data)
and SBB customer service, with the numbered arrows of the sheet:

  1 query                     passenger -> model
  2 P3 Model as Translator    model -> knowledge base
  3 P5 ask for missing facts  knowledge base -> model
  4 question to passenger     model -> passenger
  5 additional info           passenger -> model
  6 P1 Model as Sensor        model -> knowledge base
  7 P7 Division by Competence knowledge base: answer found, or escalate
  8 answer to the passenger   knowledge base -> passenger
  9 hand-over                 knowledge base -> SBB customer service

The arrows and patterns used in the latest turn "light up" (SBB red, glow).
The diagram only reads the trace: it never changes what the backend decided.
"""
from __future__ import annotations

from html import escape

from .backend import ASKING, ENTITLED, FAILED, HANDED_ON, NOT_ENTITLED

PATTERNS = {
    "P1": "Model as Sensor",
    "P3": "Model as Translator",
    "P5": "Rules Steer the Model",
    "P7": "Division by Competence",
}

# edge id -> (path, number circle x, y, number, label, label side "start"|"end")
# The three vertical arrows carry their number on the line; labels sit outside them.
EDGES = {
    "e1": ("M 232 176 C 380 100, 520 62, 628 58", 430, 70, "1", "query", "start"),
    "e2": ("M 744 128 L 744 292", 744, 252, "2", "P3", "start"),
    "e3": ("M 828 292 L 828 128", 828, 210, "3", "P5 ask for facts", "start"),
    "e4": ("M 628 92 C 500 110, 380 150, 232 196", 318, 150, "4", "question", "start"),
    "e5": ("M 232 228 C 400 210, 540 160, 640 128", 462, 214, "5", "additional info", "start"),
    "e6": ("M 662 128 L 662 292", 662, 210, "6", "P1 sensor", "end"),
    "e7": ("M 860 330 C 920 330, 920 380, 860 380", 892, 420, "7", "P7 decide or escalate", "end"),
    "e8": ("M 628 350 C 480 340, 330 280, 232 238", 410, 296, "8", "answer", "start"),
    "e9": ("M 628 370 C 480 400, 330 420, 232 420", 430, 392, "9", "hand-over", "start"),
}

NODES = {
    "passenger": (40, 166, 192, 92, "Passenger", "asks in their own words"),
    "model": (628, 30, 232, 98, "Language model", "GPT-5 mini"),
    "kb": (628, 292, 232, 104, "Knowledge base", "FrameX facts + rules · SBB 07.11.2026"),
    "service": (40, 384, 192, 72, "SBB customer service", "settles what rules cannot"),
}


def lit_from_trace(rows: list, status: str | None) -> tuple[set, set, set]:
    """(lit edges, lit nodes, lit patterns) for the latest turn of the trace.

    rows: the UI's trace rows [turn, time, pattern, actor, action, data].
    """
    if not rows:
        return set(), set(), set()
    turn = max(r[0] for r in rows)
    edges, nodes, patterns = set(), set(), set()
    for _, _, pattern, actor, _, _ in (r for r in rows if r[0] == turn):
        code = (pattern or "").split(" ")[0]
        if code in PATTERNS:
            patterns.add(code)
        if actor == "passenger":
            edges.add("e1" if turn == 1 else "e5")
            nodes.update({"passenger", "model"})
        elif actor == "model":
            nodes.add("model")
        elif actor in ("rules", "knowledge base"):
            nodes.add("kb")
        if code == "P1":
            edges.add("e6")
        elif code == "P3":
            edges.add("e2")
        elif code == "P5":
            edges.add("e3")
        elif code == "P7":
            edges.add("e7")
    if status == ASKING:
        edges.add("e4")
        nodes.add("passenger")
    elif status in (ENTITLED, NOT_ENTITLED):
        edges.add("e8")
        nodes.update({"kb", "passenger"})
    elif status in (HANDED_ON, FAILED):
        edges.update({"e7", "e9"})
        nodes.update({"kb", "service"})
        patterns.add("P7")
    return edges, nodes, patterns


def render_diagram(rows: list | None = None, status: str | None = None) -> str:
    edges, nodes, patterns = lit_from_trace(rows or [], status)
    parts = []
    for eid, (path, cx, cy, num, label, side) in EDGES.items():
        cls = "edge lit" if eid in edges else "edge"
        tx = cx + 14 if side == "start" else cx - 14
        parts.append(
            f'<g class="{cls}" data-edge="{eid}"><path d="{path}" marker-end="url(#arrow{"-lit" if eid in edges else ""})"/>'
            f'<circle cx="{cx}" cy="{cy}" r="9"/><text class="num" x="{cx}" y="{cy + 4}">{num}</text>'
            f'<text class="elabel" x="{tx}" y="{cy + 4}" text-anchor="{side}">{escape(label)}</text></g>')
    for nid, (x, y, w, h, title, sub) in NODES.items():
        cls = "node lit" if nid in nodes else "node"
        parts.append(
            f'<g class="{cls}" data-node="{nid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/>'
            f'<text class="ntitle" x="{x + w / 2}" y="{y + h / 2 - 4}">{escape(title)}</text>'
            f'<text class="nsub" x="{x + w / 2}" y="{y + h / 2 + 16}">{escape(sub)}</text></g>')
    chips = "".join(
        f'<span class="chip{" lit" if code in patterns else ""}" data-pattern="{code}">'
        f'<b>{code}</b> {escape(name)}</span>' for code, name in PATTERNS.items())
    return (
        '<div class="sbb-diagram">'
        '<svg viewBox="0 0 960 470" role="img" aria-label="System architecture: passenger, '
        'language model, knowledge base, customer service">'
        '<defs>'
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" class="ahead"/></marker>'
        '<marker id="arrow-lit" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" class="ahead-lit"/></marker>'
        '</defs>' + "".join(parts) + '</svg>'
        f'<div class="chips">{chips}</div></div>')


CSS = """
:root, body {
  --sbb-red: #EB0000; --sbb-red-dark: #C60018;
  --dg-bg: #FFFFFF; --dg-node: #F6F6F6; --dg-stroke: #A8A8A8; --dg-text: #151515;
  --dg-sub: #686868; --dg-edge: #CDCDCD; --dg-label: #444444; --dg-lit: #EB0000;
  --dg-lit-fill: #FFECEC;
}
body.dark {
  --dg-bg: #141414; --dg-node: #232323; --dg-stroke: #555555; --dg-text: #F2F2F2;
  --dg-sub: #A8A8A8; --dg-edge: #444444; --dg-label: #BDBDBD; --dg-lit: #FF3B3B;
  --dg-lit-fill: #3A1414;
}
.sbb-diagram { background: var(--dg-bg); border: 1px solid var(--dg-stroke); border-radius: 10px; padding: 8px; }
.sbb-diagram svg { width: 100%; height: auto; display: block; font-family: Helvetica, Arial, sans-serif; }
.sbb-diagram .node rect { fill: var(--dg-node); stroke: var(--dg-stroke); stroke-width: 1.5; transition: all .3s; }
.sbb-diagram .ntitle { fill: var(--dg-text); font-size: 16px; font-weight: 700; text-anchor: middle; }
.sbb-diagram .nsub { fill: var(--dg-sub); font-size: 11.5px; text-anchor: middle; }
.sbb-diagram .node.lit rect { stroke: var(--dg-lit); stroke-width: 3; fill: var(--dg-lit-fill);
  filter: drop-shadow(0 0 6px var(--dg-lit)); }
.sbb-diagram .edge path { fill: none; stroke: var(--dg-edge); stroke-width: 2; }
.sbb-diagram .edge circle { fill: var(--dg-bg); stroke: var(--dg-edge); stroke-width: 1.5; }
.sbb-diagram .num { fill: var(--dg-label); font-size: 11px; font-weight: 700; text-anchor: middle; }
.sbb-diagram .elabel { fill: var(--dg-label); font-size: 12px; paint-order: stroke;
  stroke: var(--dg-bg); stroke-width: 5px; stroke-linejoin: round; }
.sbb-diagram .ahead { fill: var(--dg-edge); }
.sbb-diagram .ahead-lit { fill: var(--dg-lit); }
.sbb-diagram .edge.lit path { stroke: var(--dg-lit); stroke-width: 3.5; stroke-dasharray: 10 6;
  animation: dg-flow .8s linear infinite; filter: drop-shadow(0 0 4px var(--dg-lit)); }
.sbb-diagram .edge.lit circle { fill: var(--dg-lit); stroke: var(--dg-lit); }
.sbb-diagram .edge.lit .num { fill: #FFFFFF; }
.sbb-diagram .edge.lit .elabel { fill: var(--dg-lit); font-weight: 700; }
@keyframes dg-flow { to { stroke-dashoffset: -16; } }
.sbb-diagram .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.sbb-diagram .chip { font: 12.5px Helvetica, Arial, sans-serif; padding: 4px 10px; border-radius: 999px;
  border: 1px solid var(--dg-stroke); color: var(--dg-sub); background: var(--dg-node); transition: all .3s; }
.sbb-diagram .chip.lit { background: var(--dg-lit); border-color: var(--dg-lit); color: #FFFFFF;
  box-shadow: 0 0 10px var(--dg-lit); animation: dg-pulse 1.4s ease-in-out infinite; }
@keyframes dg-pulse { 50% { box-shadow: 0 0 2px var(--dg-lit); } }
@media (prefers-reduced-motion: reduce) {
  .sbb-diagram .edge.lit path, .sbb-diagram .chip.lit { animation: none; }
}
.sbb-header { background: #EB0000; color: #FFFFFF; padding: 14px 20px; border-radius: 10px;
  display: flex; align-items: center; gap: 14px; }
.sbb-header h1 { color: #FFFFFF !important; margin: 0; font: 700 22px Helvetica, Arial, sans-serif; }
.sbb-header p { color: #FFFFFF !important; margin: 2px 0 0; opacity: .9; font: 14px Helvetica, Arial, sans-serif; }
.sbb-logo { width: 46px; height: 30px; flex: none; }
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
<div class="sbb-header">
  <svg class="sbb-logo" viewBox="0 0 46 30" aria-hidden="true">
    <rect x="11" y="3" width="24" height="20" rx="5" fill="#FFFFFF"/>
    <rect x="15" y="7" width="16" height="7" rx="1.5" fill="#EB0000"/>
    <circle cx="17" cy="18.5" r="1.8" fill="#EB0000"/><circle cx="29" cy="18.5" r="1.8" fill="#EB0000"/>
    <path d="M15 23 L12 28 M31 23 L34 28" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round"/>
  </svg>
  <div><h1>Delay refund assistant</h1>
  <p>Describe your journey on Saturday 7 November 2026 in your own words.</p></div>
</div>
"""
