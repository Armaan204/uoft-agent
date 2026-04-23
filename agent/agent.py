"""
agent/agent.py — the main agent loop.

run(user_message) drives a multi-turn conversation with Claude using
native function calling.  Tool results are fed back into the message
history until Claude returns a plain-text final answer.

A simple CLI loop at the bottom lets you test interactively.
"""

import json
import os
import sys

import anthropic
from dotenv import load_dotenv

from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOL_SCHEMAS, execute_tool
from integrations.quercus import QuercusClient

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

MODEL = "claude-sonnet-4-6"


def run(
    user_message: str,
    token: str = None,
    user_id: str | int | None = None,
    verbose: bool = True,
    return_tool_calls: bool = False,
) -> "str | tuple[str, list[dict]]":
    """Send a user message through the agent loop and return the final answer.

    Parameters
    ----------
    user_message      : the student's natural-language question.
    verbose           : if True, print each tool call and result to stdout.
    return_tool_calls : if True, return (answer, tool_calls) instead of just
                        the answer string.  tool_calls is a list of dicts with
                        keys 'name', 'input', and 'result'.

    Returns
    -------
    str when return_tool_calls is False (default).
    (str, list[dict]) when return_tool_calls is True.
    """
    client         = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    quercus_client = QuercusClient(token=token)
    messages       = [{"role": "user", "content": user_message}]
    all_tool_calls: list[dict] = []

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        # Append the full assistant turn to history
        messages.append({"role": "assistant", "content": response.content})

        # If Claude is done, return the text
        if response.stop_reason == "end_turn":
            answer = _extract_text(response.content)
            return (answer, all_tool_calls) if return_tool_calls else answer

        # Otherwise handle tool_use blocks
        if response.stop_reason != "tool_use":
            answer = _extract_text(response.content)
            return (answer, all_tool_calls) if return_tool_calls else answer

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            if verbose:
                print(f"\n[tool call]  {block.name}({json.dumps(block.input, indent=2)})")

            result = execute_tool(block.name, block.input, quercus_client, user_id=user_id)

            if verbose:
                result_preview = json.dumps(result, indent=2)
                if len(result_preview) > 800:
                    result_preview = result_preview[:800] + "\n  ... (truncated)"
                print(f"[tool result] {result_preview}")

            all_tool_calls.append({
                "name":   block.name,
                "input":  block.input,
                "result": result,
            })

            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": block.id,
                "content":     json.dumps(result),
            })

        # Feed all results back in a single user turn
        messages.append({"role": "user", "content": tool_results})


def _extract_text(content: list) -> str:
    """Pull plain text out of an assistant content block list."""
    parts = [block.text for block in content if hasattr(block, "text")]
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("UofT Academic Assistant  (type 'quit' to exit)\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in {"quit", "exit"}:
            break
        answer = run(question, token=os.getenv("QUERCUS_API_TOKEN"))
        safe = answer.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding)
        print(f"\nAssistant: {safe}\n")
