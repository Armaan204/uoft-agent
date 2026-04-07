"""
app.py — Streamlit chat interface for uoft-agent.
"""

import json

import streamlit as st
from dotenv import load_dotenv

from agent.agent import run

load_dotenv()

# ---------------------------------------------------------------------------
# Page config & header
# ---------------------------------------------------------------------------

st.set_page_config(page_title="UofT Agent", page_icon="📚", layout="centered")

st.title("UofT Agent")
st.caption("Ask anything about your grades and courses")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []
    # [{"role": "user"|"assistant", "content": str, "tool_calls": list}]

# ---------------------------------------------------------------------------
# Render existing conversation
# ---------------------------------------------------------------------------

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            # Show tool calls as collapsed expanders above the answer
            for tc in msg.get("tool_calls", []):
                label = f"🔧 {tc['name']}({', '.join(f'{k}={v}' for k, v in tc['input'].items())})"
                with st.expander(label, expanded=False):
                    st.json(tc["result"])
        st.markdown(msg["content"])

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Ask about your grades..."):
    # Show user message immediately
    st.session_state.messages.append({"role": "user", "content": prompt, "tool_calls": []})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Run agent with spinner
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer, tool_calls = run(prompt, verbose=False, return_tool_calls=True)

        # Render tool call expanders
        for tc in tool_calls:
            label = f"🔧 {tc['name']}({', '.join(f'{k}={v}' for k, v in tc['input'].items())})"
            with st.expander(label, expanded=False):
                st.json(tc["result"])

        st.markdown(answer)

    # Persist to session state
    st.session_state.messages.append({
        "role":       "assistant",
        "content":    answer,
        "tool_calls": tool_calls,
    })
