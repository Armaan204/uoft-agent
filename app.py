"""
app.py — Streamlit chat interface for uoft-agent.
"""

import streamlit as st
from dotenv import load_dotenv

from agent.agent import run
from integrations.quercus import QuercusClient, QuercusError

load_dotenv()

st.set_page_config(page_title="UofT Agent", page_icon="📚", layout="centered")

# ---------------------------------------------------------------------------
# Onboarding — shown until a valid token is stored in session state
# ---------------------------------------------------------------------------

if "token" not in st.session_state:
    st.title("Welcome to UofT Agent")
    st.markdown(
        "Enter your Quercus personal access token to get started.  \n"
        "You can generate one at **q.utoronto.ca → Account → Settings → "
        "Under Approved Integrations → New Access Token**."
    )

    token_input = st.text_input("Quercus access token", type="password")

    if st.button("Connect"):
        if not token_input.strip():
            st.error("Please enter a token.")
        else:
            with st.spinner("Validating token..."):
                try:
                    QuercusClient(token=token_input.strip()).get_courses()
                    st.session_state.token = token_input.strip()
                    st.session_state.messages = []
                    st.rerun()
                except QuercusError:
                    st.error("Invalid token — please check and try again.")

    st.stop()

# ---------------------------------------------------------------------------
# Chat UI — only reached after a valid token is in session state
# ---------------------------------------------------------------------------

st.title("UofT Agent")
st.caption("Ask anything about your grades and courses")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Render conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            for tc in msg.get("tool_calls", []):
                label = "🔧 {}({})".format(
                    tc["name"],
                    ", ".join(f"{k}={v}" for k, v in tc["input"].items()),
                )
                with st.expander(label, expanded=False):
                    st.json(tc["result"])
        st.markdown(msg["content"])

# New message
if prompt := st.chat_input("Ask about your grades..."):
    st.session_state.messages.append({"role": "user", "content": prompt, "tool_calls": []})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer, tool_calls = run(
                prompt,
                token=st.session_state.token,
                verbose=False,
                return_tool_calls=True,
            )

        for tc in tool_calls:
            label = "🔧 {}({})".format(
                tc["name"],
                ", ".join(f"{k}={v}" for k, v in tc["input"].items()),
            )
            with st.expander(label, expanded=False):
                st.json(tc["result"])

        st.markdown(answer)

    st.session_state.messages.append({
        "role":       "assistant",
        "content":    answer,
        "tool_calls": tool_calls,
    })
