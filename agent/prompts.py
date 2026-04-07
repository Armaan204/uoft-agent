"""
agent/prompts.py — static prompt strings used by the agent.

Keeps all prompt text in one place so it can be reviewed, iterated on,
and tested independently of the agent logic.

Contents
--------
- SYSTEM_PROMPT : the system message sent at the start of every
  conversation.  Instructs Claude on its persona, capabilities, the
  available tools, and how to reason about grade calculations without
  doing arithmetic itself.
"""
