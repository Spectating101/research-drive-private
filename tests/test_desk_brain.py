"""Desk brain — Composer + MCP only (no scripted ladder)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts.research_data_mcp import desk_brain
from scripts.research_data_mcp.desk_brain import AgentTurn, desk_brain_mode, run_cursor_composer_turn


class _FakeOptions:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def _sdk_bindings(agent) -> desk_brain._CursorSdkBindings:
    return desk_brain._CursorSdkBindings(
        agent=agent,
        agent_options=_FakeOptions,
        model_selection=_FakeOptions,
        send_options=_FakeOptions,
        stdio_mcp_server_config=_FakeOptions,
        local_agent_options=_FakeOptions,
        cloud_agent_options=_FakeOptions,
    )


def test_desk_brain_mode_is_unavailable_without_composer(monkeypatch) -> None:
    monkeypatch.delenv("DESK_BRAIN", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    assert desk_brain_mode() == "unavailable"


def test_missing_cursor_key_returns_clear_reply(monkeypatch) -> None:
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    gateway = MagicMock()
    gateway.repo_root = "/tmp/repo"
    turn = run_cursor_composer_turn(gateway, "TWSE data", {})
    assert "CURSOR_API_KEY" in turn.reply
    assert turn.action_result["action"] == "composer_unavailable"


def test_missing_cursor_sdk_returns_clear_reply(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(
        desk_brain,
        "_load_cursor_sdk_bindings",
        MagicMock(side_effect=desk_brain.CursorSdkUnavailable("cursor_sdk unavailable")),
    )
    gateway = MagicMock()
    gateway.repo_root = "/tmp/repo"

    turn = run_cursor_composer_turn(gateway, "TWSE data", {})

    assert "cursor_sdk" in turn.reply
    assert turn.action_result["action"] == "composer_unavailable"


def test_composer_turn_passes_raw_message(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    gateway = MagicMock()
    gateway.repo_root = "/tmp/repo"

    class FakeRun:
        def wait(self):
            return None

        def text(self):
            return "Here is what I found in the vault."

        def conversation(self):
            return []

    class FakeAgent:
        agent_id = "agent-1"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def send(self, text, options=None):
            FakeAgent.last_prompt = text if isinstance(text, str) else str(text)
            return FakeRun()

        def close(self):
            pass

    FakeAgent.last_prompt = ""

    agent = SimpleNamespace(
        create=MagicMock(return_value=FakeAgent()),
        resume=MagicMock(return_value=FakeAgent()),
    )
    monkeypatch.setattr(desk_brain, "_load_cursor_sdk_bindings", lambda: _sdk_bindings(agent))
    state = {"user_email": "drkong@saturn.yzu.edu.tw", "cursor_agent_id": "agent-1"}
    turn = run_cursor_composer_turn(
        gateway, "what TWSE data do we have?", state, session_id="abc"
    )

    assert "Here is what I found" in turn.reply
    # L0 grounding is prepended on purpose; the faculty message must survive intact
    # and stay last so it is what the model answers.
    assert FakeAgent.last_prompt.rstrip().endswith("what TWSE data do we have?")
    assert "[Ask DESK_FACTS]" in FakeAgent.last_prompt
    assert turn.tool_name == "cursor_composer"


def test_empty_composer_reply_does_not_invent_candidates(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    gateway = MagicMock()
    gateway.repo_root = "/tmp/repo"

    class FakeRun:
        status = "completed"

        def wait(self):
            return None

        def text(self):
            return ""

        def conversation(self):
            return []

    class FakeAgent:
        agent_id = "agent-1"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def send(self, _text, options=None):
            return FakeRun()

        def close(self):
            pass

    agent = SimpleNamespace(
        create=MagicMock(return_value=FakeAgent()),
        resume=MagicMock(return_value=FakeAgent()),
    )
    monkeypatch.setattr(desk_brain, "_load_cursor_sdk_bindings", lambda: _sdk_bindings(agent))
    state = {"cursor_agent_id": "agent-1"}
    turn = run_cursor_composer_turn(
        gateway, "compare climate data", state, session_id="abc"
    )

    assert turn.action_result["action"] == "composer_error"
    assert "candidates" not in turn.action_result
    assert "did not return a usable answer" in turn.reply


def test_tool_activity_label() -> None:
    from scripts.research_data_mcp.desk_brain import _tool_activity_label

    assert "vault" in _tool_activity_label("collection_status").lower()
    assert _tool_activity_label("research_query_dataset")


def test_is_empty_desk_reply() -> None:
    from scripts.research_data_mcp.desk_brain import EMPTY_REPLY_FALLBACK, is_empty_desk_reply

    assert is_empty_desk_reply("")
    assert is_empty_desk_reply(EMPTY_REPLY_FALLBACK)
    assert not is_empty_desk_reply("You have TWSE data ready to query.")


def test_reply_from_run_falls_back_to_conversation() -> None:
    from scripts.research_data_mcp.desk_brain import _reply_from_run

    class Msg:
        type = "assistant"
        text = "Recovered from conversation."

    class Step:
        message = Msg()

    class Turn:
        steps = (Step(),)

    class Run:
        def text(self):
            return ""

        def conversation(self):
            return [Turn()]

    assert _reply_from_run(Run(), []) == "Recovered from conversation."


def test_procurement_chat_uses_desk_brain() -> None:
    from scripts.research_data_mcp.procurement_chat import ProcurementChatOrchestrator

    orch = ProcurementChatOrchestrator("/tmp")
    gateway = MagicMock()
    turn = AgentTurn(
        plan={"action": "composer"},
        action_result={"action": "composer"},
        reply="Natural answer.",
        suggested_prompts=[],
    )
    with patch("scripts.research_data_mcp.desk_brain.run_desk_agent_turn", return_value=turn):
        out = orch._run_agent_turn(gateway, "hi", {}, "sess1")
    assert out.reply == "Natural answer."
