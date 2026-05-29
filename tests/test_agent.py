"""
tests/test_agent.py — tests for agent/agent.py

All Anthropic API calls are mocked.
"""

import json
import pytest
from unittest.mock import MagicMock, patch


def _make_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(name: str, input_: dict, use_id: str = "tu-1"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_
    block.id = use_id
    return block


def _make_response(stop_reason: str, content: list):
    resp = MagicMock()
    resp.stop_reason = stop_reason
    resp.content = content
    return resp


# ── _extract_text ──────────────────────────────────────────────────────────────

class TestExtractText:
    def test_single_text_block(self):
        from api.agent.agent import _extract_text
        block = _make_text_block("Hello world")
        assert _extract_text([block]) == "Hello world"

    def test_multiple_text_blocks_joined(self):
        from api.agent.agent import _extract_text
        blocks = [_make_text_block("Hello"), _make_text_block("world")]
        assert _extract_text(blocks) == "Hello\nworld"

    def test_skips_blocks_without_text_attr(self):
        from api.agent.agent import _extract_text
        no_text = MagicMock(spec=[])  # no .text attribute
        text_block = _make_text_block("Hi")
        assert _extract_text([no_text, text_block]) == "Hi"

    def test_empty_list_returns_empty_string(self):
        from api.agent.agent import _extract_text
        assert _extract_text([]) == ""

    def test_strips_surrounding_whitespace(self):
        from api.agent.agent import _extract_text
        block = _make_text_block("  hello  ")
        assert _extract_text([block]) == "hello"


# ── run — end_turn path ────────────────────────────────────────────────────────

class TestRunEndTurn:
    def _mock_client(self, stop_reason, content):
        mock_anthropic = MagicMock()
        mock_messages = MagicMock()
        mock_anthropic.return_value.messages = mock_messages
        mock_messages.create.return_value = _make_response(stop_reason, content)
        return mock_anthropic

    def test_returns_plain_string_by_default(self):
        from api.agent.agent import run
        content = [_make_text_block("Final answer")]
        mock_anthropic = self._mock_client("end_turn", content)
        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"):
            result = run("What is my grade?", token="tok", user_id="u1", verbose=False)
        assert result == "Final answer"

    def test_returns_tuple_when_return_tool_calls_true(self):
        from api.agent.agent import run
        content = [_make_text_block("Answer")]
        mock_anthropic = self._mock_client("end_turn", content)
        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"):
            result = run("Hello", return_tool_calls=True, verbose=False)
        assert isinstance(result, tuple)
        answer, calls = result
        assert answer == "Answer"
        assert calls == []

    def test_uses_history_messages(self):
        from api.agent.agent import run
        content = [_make_text_block("Done")]
        mock_anthropic = MagicMock()
        mock_anthropic.return_value.messages.create.return_value = _make_response("end_turn", content)
        history = [{"role": "user", "text": "hi"}, {"role": "assistant", "text": "hello"}]
        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"):
            result = run("Follow-up?", history=history, verbose=False)
        assert result == "Done"
        # The mock stores a reference to the list which gets mutated after the call
        # (agent appends the assistant response). So the final list is
        # [2 history + 1 user + 1 assistant appended] = 4.
        call_args = mock_anthropic.return_value.messages.create.call_args
        messages_sent = call_args.kwargs["messages"]
        assert len(messages_sent) == 4  # 2 history + 1 user + 1 appended assistant

    def test_history_capped_at_max(self):
        from api.agent.agent import run
        from api.agent.agent import _MAX_HISTORY_MESSAGES
        content = [_make_text_block("Done")]
        mock_anthropic = MagicMock()
        mock_anthropic.return_value.messages.create.return_value = _make_response("end_turn", content)
        # Create more history than the cap
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "text": f"msg{i}"}
            for i in range(_MAX_HISTORY_MESSAGES + 4)
        ]
        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"):
            run("Now", history=history, verbose=False)
        call_args = mock_anthropic.return_value.messages.create.call_args
        messages_sent = call_args.kwargs["messages"]
        # The list is mutated: capped history + new user + 1 appended assistant
        assert len(messages_sent) == _MAX_HISTORY_MESSAGES + 2

    def test_history_filters_missing_text(self):
        from api.agent.agent import run
        content = [_make_text_block("Done")]
        mock_anthropic = MagicMock()
        mock_anthropic.return_value.messages.create.return_value = _make_response("end_turn", content)
        # Entry with no 'text' key should be skipped
        history = [{"role": "user", "text": "valid"}, {"role": "user"}]
        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"):
            run("Q", history=history, verbose=False)
        call_args = mock_anthropic.return_value.messages.create.call_args
        messages_sent = call_args.kwargs["messages"]
        # 1 valid history + 1 user + 1 appended assistant = 3
        assert len(messages_sent) == 3

    def test_unknown_stop_reason_returns_answer(self):
        from api.agent.agent import run
        content = [_make_text_block("Fallback answer")]
        mock_anthropic = self._mock_client("some_unknown_reason", content)
        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"):
            result = run("Q", verbose=False)
        assert result == "Fallback answer"


# ── run — tool_use path ────────────────────────────────────────────────────────

class TestRunToolUse:
    def test_single_tool_call_then_end_turn(self):
        from api.agent.agent import run
        tool_block = _make_tool_use_block("get_courses", {}, "tu-1")
        tool_response = _make_response("tool_use", [tool_block])
        final_block = _make_text_block("Here are your courses")
        final_response = _make_response("end_turn", [final_block])

        mock_anthropic = MagicMock()
        mock_anthropic.return_value.messages.create.side_effect = [tool_response, final_response]

        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"), \
             patch("api.agent.agent.execute_tool", return_value={"courses": []}):
            result = run("List my courses", verbose=False)
        assert result == "Here are your courses"

    def test_tool_call_recorded_in_all_tool_calls(self):
        from api.agent.agent import run
        tool_block = _make_tool_use_block("get_grades", {"course_id": 1}, "tu-2")
        tool_response = _make_response("tool_use", [tool_block])
        final_response = _make_response("end_turn", [_make_text_block("Done")])

        mock_anthropic = MagicMock()
        mock_anthropic.return_value.messages.create.side_effect = [tool_response, final_response]

        tool_result = {"grade": 85}
        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"), \
             patch("api.agent.agent.execute_tool", return_value=tool_result):
            answer, calls = run("Grades?", return_tool_calls=True, verbose=False)
        assert len(calls) == 1
        assert calls[0]["name"] == "get_grades"
        assert calls[0]["input"] == {"course_id": 1}
        assert calls[0]["result"] == tool_result

    def test_verbose_prints_tool_info(self, capsys):
        from api.agent.agent import run
        tool_block = _make_tool_use_block("get_courses", {}, "tu-3")
        tool_response = _make_response("tool_use", [tool_block])
        final_response = _make_response("end_turn", [_make_text_block("Done")])

        mock_anthropic = MagicMock()
        mock_anthropic.return_value.messages.create.side_effect = [tool_response, final_response]

        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"), \
             patch("api.agent.agent.execute_tool", return_value={}):
            run("Q", verbose=True)
        captured = capsys.readouterr()
        assert "tool call" in captured.out
        assert "tool result" in captured.out

    def test_verbose_truncates_long_result(self, capsys):
        from api.agent.agent import run
        tool_block = _make_tool_use_block("get_courses", {}, "tu-4")
        tool_response = _make_response("tool_use", [tool_block])
        final_response = _make_response("end_turn", [_make_text_block("Done")])

        mock_anthropic = MagicMock()
        mock_anthropic.return_value.messages.create.side_effect = [tool_response, final_response]

        # Long result that should be truncated
        big_result = {"data": "x" * 2000}
        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"), \
             patch("api.agent.agent.execute_tool", return_value=big_result):
            run("Q", verbose=True)
        captured = capsys.readouterr()
        assert "truncated" in captured.out

    def test_skips_non_tool_use_blocks_in_tool_response(self):
        """Cover line 92: the `continue` for text blocks mixed into a tool_use response."""
        from api.agent.agent import run
        text_block = _make_text_block("Thinking...")  # not a tool_use block
        tool_block = _make_tool_use_block("get_courses", {}, "tu-skip")
        tool_response = _make_response("tool_use", [text_block, tool_block])
        final_response = _make_response("end_turn", [_make_text_block("Done")])

        mock_anthropic = MagicMock()
        mock_anthropic.return_value.messages.create.side_effect = [tool_response, final_response]

        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"), \
             patch("api.agent.agent.execute_tool", return_value={}) as mock_exec:
            answer, calls = run("Q", return_tool_calls=True, verbose=False)
        # Only the tool_use block should trigger execute_tool; the text block is skipped
        assert mock_exec.call_count == 1
        assert len(calls) == 1

    def test_multiple_tool_blocks_in_one_turn(self):
        from api.agent.agent import run
        block1 = _make_tool_use_block("get_courses", {}, "tu-5")
        block2 = _make_tool_use_block("get_grades", {"course_id": 1}, "tu-6")
        tool_response = _make_response("tool_use", [block1, block2])
        final_response = _make_response("end_turn", [_make_text_block("All done")])

        mock_anthropic = MagicMock()
        mock_anthropic.return_value.messages.create.side_effect = [tool_response, final_response]

        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"), \
             patch("api.agent.agent.execute_tool", return_value={}):
            answer, calls = run("Q", return_tool_calls=True, verbose=False)
        assert len(calls) == 2
        assert calls[0]["name"] == "get_courses"
        assert calls[1]["name"] == "get_grades"

    def test_tool_results_fed_back_to_claude(self):
        from api.agent.agent import run
        tool_block = _make_tool_use_block("get_courses", {}, "tu-7")
        tool_response = _make_response("tool_use", [tool_block])
        final_response = _make_response("end_turn", [_make_text_block("Result")])

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [tool_response, final_response]
        mock_anthropic = MagicMock(return_value=mock_client)

        with patch("api.agent.agent.anthropic.Anthropic", mock_anthropic), \
             patch("api.agent.agent.QuercusClient"), \
             patch("api.agent.agent.execute_tool", return_value={"ok": True}):
            run("Q", verbose=False)

        # The mock stores a list reference mutated after each call.
        # After the second (end_turn) call, the assistant response is appended,
        # so the final list is: [user, assistant_tool_use, user_tool_result, assistant_end_turn].
        # The tool_result user message is at index -2 (before the appended assistant response).
        second_call_messages = mock_client.messages.create.call_args_list[1].kwargs["messages"]
        tool_result_msg = second_call_messages[-2]
        assert tool_result_msg["role"] == "user"
        result_content = tool_result_msg["content"]
        assert result_content[0]["type"] == "tool_result"
        assert result_content[0]["tool_use_id"] == "tu-7"
        assert json.loads(result_content[0]["content"]) == {"ok": True}
