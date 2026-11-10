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
from chat.ui import (TRACE_HEADERS, choice_items, current_form, handle_message, new_session,
                     status_label, submit_form)

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
                # The backend's form (state["form"]): rendered here, answered here, decided there.
                with gr.Group(visible=False, elem_id="form-card") as form_box:
                    form_label = gr.Markdown("", elem_id="form-label")
                    form_choice = gr.Radio(choices=[], value=None, visible=False, show_label=False,
                                           elem_id="form-choice")
                    with gr.Row(equal_height=True):
                        form_number = gr.Number(value=None, visible=False, show_label=False,
                                                elem_id="form-number")
                        form_send = gr.Button("Confirm", variant="primary", visible=False, scale=0,
                                              elem_id="form-send")
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

        def form_view(sess):
            form = current_form(sess)
            hidden = (gr.Group(visible=False), "", gr.Radio(choices=[], value=None, visible=False),
                      gr.Number(value=None, visible=False), gr.Button(visible=False))
            if form is None or form["kind"] not in ("choice", "number"):
                return hidden  # text, date, time: the passenger types in the message box
            label = str(form.get("label") or "Your answer")
            if form["kind"] == "choice":
                return (gr.Group(visible=True), label,
                        gr.Radio(choices=choice_items(form), value=None, visible=True),
                        gr.Number(value=None, visible=False), gr.Button(visible=False))
            return (gr.Group(visible=True), label, gr.Radio(choices=[], value=None, visible=False),
                    gr.Number(value=None, visible=True, minimum=form.get("min")), gr.Button(visible=True))

        def view(history, sess):
            label = status_label(sess.get("status"))
            return (history, sess, sess["trace_rows"], status_pill(sess.get("status"), label),
                    render_diagram(sess["trace_rows"], sess.get("status")), *form_view(sess))

        def on_send(message, history, sess):
            return ("", *view(*handle_message(message, history, sess, backend)))

        def on_choice(choice, history, sess):
            return view(*submit_form(choice, None, history, sess, backend))

        def on_number(number, history, sess):
            return view(*submit_form(None, number, history, sess, backend))

        def on_reset():
            return view([], new_session())

        shown = [chatbot, session, trace, status, diagram, form_box, form_label, form_choice,
                 form_number, form_send]
        send.click(on_send, [box, chatbot, session], [box, *shown])
        box.submit(on_send, [box, chatbot, session], [box, *shown])
        form_choice.input(on_choice, [form_choice, chatbot, session], shown)  # a click sends
        form_send.click(on_number, [form_number, chatbot, session], shown)
        form_number.submit(on_number, [form_number, chatbot, session], shown)
        reset.click(on_reset, None, shown)
        theme_btn.click(None, None, None, js=TOGGLE_JS)
    return demo


def launch(demo: gr.Blocks, **kwargs):
    """Theme, CSS and JS are launch() arguments in Gradio 6."""
    return demo.launch(theme=THEME, css=CSS, js=LOAD_JS, **kwargs)


def main():
    launch(build_demo(load_backend()))


if __name__ == "__main__":
    main()
