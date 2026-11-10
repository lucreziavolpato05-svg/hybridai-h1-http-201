"""Gradio app: passenger chat on the left, workflow view on the right.

Run from the repo root:
    uv run python -m chat            (from src/)  or
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
from chat.ui import TRACE_HEADERS, handle_message, new_session, status_label

PATTERNS_MD = """
**Patterns in this system**
- **P1 Model as Sensor**: the model extracts stations, date, time and price, each with a quote; the rules accept or reject each one.
- **P5 Rules Steer the Model**: the rules decide what is missing and what to ask next.
- **P3 Model as Translator**: the model puts the rules' verdict into words; the reply must state the rules' decision.
- **P7 Division by Competence**: whatever the rules cannot settle goes to SBB customer service.

Every station, time, delay and percentage comes from the knowledge base (SBB data, 07.11.2026).
"""

EXAMPLES = [
    "On 7 November I was going from St. Gallen to Zürich HB at 8 o'clock. I had a delay. Do I get a refund?",
    "My train from Bern to Zürich HB on 7.11. was late, the ticket cost CHF 52.",
    "I travelled from Basel SBB to Zürich HB on 8 November at 9. Refund?",
]


def build_demo(backend: Backend | None = None) -> gr.Blocks:
    backend = backend or DemoBackend()
    with gr.Blocks(title="SBB refund assistant") as demo:
        gr.Markdown("## SBB delay refund assistant\nDescribe your journey on Saturday 7 November 2026 in your own words.")
        session = gr.State(new_session())
        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(label="Chat", height=480)
                status = gr.Markdown("")
                box = gr.Textbox(placeholder="e.g. St. Gallen to Zürich HB at 8:00, CHF 46 ticket ...",
                                 label="Your message (Enter to send, Shift+Enter for a new line)",
                                 lines=1, max_lines=6)  # lines=1 makes Enter submit in Gradio 6
                with gr.Row():
                    send = gr.Button("Send", variant="primary")
                    reset = gr.Button("New conversation")
                gr.Examples(EXAMPLES, inputs=box)
            with gr.Column(scale=4):
                gr.Markdown("### Workflow view")
                gr.Markdown(PATTERNS_MD)
                trace = gr.Dataframe(headers=TRACE_HEADERS, value=[], label="What happened, step by step",
                                     wrap=True, interactive=False)

        def on_send(message, history, sess):
            history, sess = handle_message(message, history, sess, backend)
            label = status_label(sess.get("status"))
            return "", history, sess, sess["trace_rows"], (f"**Status:** {label}" if label else "")

        def on_reset():
            return [], new_session(), [], ""

        send.click(on_send, [box, chatbot, session], [box, chatbot, session, trace, status])
        box.submit(on_send, [box, chatbot, session], [box, chatbot, session, trace, status])
        reset.click(on_reset, None, [chatbot, session, trace, status])
    return demo


def main():
    build_demo(load_backend()).launch()


if __name__ == "__main__":
    main()
