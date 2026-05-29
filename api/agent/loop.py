"""
agent/loop.py — the main agent loop.

Drives the conversation with the Claude API using native function
calling.  Each iteration sends the current message history plus the
tool schema to Claude; if Claude returns a tool_use block the
corresponding tool is executed, its result is appended to the history,
and the loop continues until Claude returns a final text response.

Responsibilities
----------------
- Build and maintain the message list across turns.
- Dispatch tool_use blocks to the correct handler in tools.py.
- Return the assistant's final plain-text answer to the caller.
"""
