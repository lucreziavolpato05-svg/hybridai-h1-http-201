"""Gradio app: passenger chat on the left, workflow view on the right.

The workflow view draws the team's architecture diagram (FlightMode sheet 2.1)
and lights up the arrows and patterns used in the latest turn, above a table
of every step. SBB colours; a toggle switches light and dark mode.

Run from the repo root:
    uv run python src/chat/app.py

Backend: REFUND_BACKEND="module:attr" (see chat/backend.py); default is the demo.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python src/chat/app.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "chat"

import gradio as gr

from chat.backend import Backend, DemoBackend, load_backend
from chat.diagram import CSS, HEADER_HTML, LOAD_JS, TOGGLE_JS, render_diagram, status_pill
from chat.ui import TRACE_HEADERS, handle_message, new_session, status_label

SBB_RED = gr.themes.Color(
    c50="#FFECEC", c100="#FFD1D1", c200="#FFA3A3", c300="#FF6B6B", c400="#F53333",
    c500="#EB0000", c600="#C60018", c700="#A20013", c800="#7E000F", c900="#5C000B",
    c950="#3A0007", name="sbb_red")
THEME = gr.themes.Base(primary_hue=SBB_RED, neutral_hue="zinc", radius_size="lg",
                       font=[gr.themes.Font(f) for f in ("Helvetica", "Arial", "sans-serif")])

EXAMPLES = [
    "On 7 November I was going from St. Gallen to Zürich HB at 8 o'clock. I had a delay. Do I get a refund?",
    "My train from Bern to Zürich HB on 7.11. was late, the ticket cost CHF 52.",
    "I travelled from Basel SBB to Zürich HB on 8 November at 9. Refund?",
]


def build_demo(backend: Backend | None = None) -> gr.Blocks:
    backend = backend or DemoBackend()
    with gr.Blocks(title="SBB refund assistant") as demo:
        with gr.Row(elem_id="sbb-header", equal_height=True):
            gr.HTML(HEADER_HTML)
            theme_btn = gr.Button("Toggle light or dark mode", elem_id="theme-toggle", scale=0)
        session = gr.State(new_session())
        with gr.Row():
            with gr.Column(scale=4):
                chatbot = gr.Chatbot(label="Chat", height=520, elem_classes="card")
                status = gr.HTML("")
                box = gr.Textbox(placeholder="e.g. St. Gallen to Zürich HB at 8:00, CHF 46 ticket ...",
                                 label="Your message (Enter to send, Shift+Enter for a new line)",
                                 lines=1, max_lines=6)  # lines=1 makes Enter submit in Gradio 6
                with gr.Row():
                    send = gr.Button("Send", variant="primary", elem_id="send-btn")
                    reset = gr.Button("New conversation", elem_id="reset-btn")
                gr.Examples(EXAMPLES, inputs=box)
            with gr.Column(scale=5):
                gr.Markdown("### Workflow view")
                diagram = gr.HTML(render_diagram())
                with gr.Accordion("Every step of this conversation", open=False):
                    trace = gr.Dataframe(headers=TRACE_HEADERS, value=[], wrap=True,
                                         interactive=False, label="pattern · actor · what crossed")

        def on_send(message, history, sess):
            history, sess = handle_message(message, history, sess, backend)
            label = status_label(sess.get("status"))
            return ("", history, sess, sess["trace_rows"],
                    status_pill(sess.get("status"), label),
                    render_diagram(sess["trace_rows"], sess.get("status")))

        def on_reset():
            return [], new_session(), [], "", render_diagram()

        outputs = [box, chatbot, session, trace, status, diagram]
        send.click(on_send, [box, chatbot, session], outputs)
        box.submit(on_send, [box, chatbot, session], outputs)
        reset.click(on_reset, None, [chatbot, session, trace, status, diagram])
        theme_btn.click(None, None, None, js=TOGGLE_JS)
    return demo


def launch(demo: gr.Blocks, **kwargs):
    """Theme, CSS and JS are launch() arguments in Gradio 6."""
    return demo.launch(theme=THEME, css=CSS, js=LOAD_JS, **kwargs)


def main():
    launch(build_demo(load_backend()))


if __name__ == "__main__":
    main()
