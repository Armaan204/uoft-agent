"""
calculator — pure-Python grade mathematics, no LLM involved.

All numeric reasoning lives here.  The agent calls these functions with
data retrieved from the integrations layer and passes the results back
to Claude as tool outputs.  Keeping arithmetic out of the LLM prevents
floating-point hallucinations.
"""
