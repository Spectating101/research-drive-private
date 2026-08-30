from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts.research_data_mcp import (
    copilot_pool_preflight,
    desk_brain,
    desk_copilot_provider,
)
from scripts.research_data_mcp.desk_brain import AgentTurn


def test_mcp_uses_hosting_interpreter_when_staged_repo_has_no_venv(monkeypatch, tmp_path):
    monkeypatch.delenv("PYTHON", raising=False)
    monkeypatch.setattr(desk_brain.sys, "executable", "/runtime/venv/bin/python")

    assert desk_brain._repo_python(tmp_path) == "/runtime/venv/bin/python"


def test_mcp_respects_explicit_python_override_when_staged_repo_has_no_venv(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHON", "/custom/python")

    assert desk_brain._repo_python(tmp_path) == "/custom/python"


def test_configured_accounts_are_ordered_deduplicated_and_validated(monkeypatch):
    monkeypatch.setenv(
        "DESK_COPILOT_ACCOUNTS",
        "primary, secondary,primary,../../bad,third account",
    )

    assert desk_copilot_provider.configured_copilot_accounts() == [
        "primary",
        "secondary",
    ]


def test_account_choice_is_sticky_for_a_session(monkeypatch):
    monkeypatch.setenv("DESK_COPILOT_ACCOUNTS", "primary,secondary")
    state = {}

    chosen = desk_copilot_provider.choose_copilot_account("session-7", state)

    assert chosen in {"primary", "secondary"}
    assert state["copilot_account"] == chosen
    assert desk_copilot_provider.choose_copilot_account("another-session", state) == chosen


def test_synthesis_mcp_is_limited_to_wire_verified_nonexecuting_tools(monkeypatch):
    monkeypatch.setenv("DESK_COPILOT_ACCOUNTS", "primary")
    monkeypatch.setattr(desk_copilot_provider, "copilot_composer_available", lambda: True)
    bindings = desk_copilot_provider.load_copilot_cursor_bindings("primary")

    config = bindings.stdio_mcp_server_config(
        command="python",
        args=["-m", "server"],
        cwd="/tmp/repo",
        env={"RESEARCH_MCP_SYNTHESIS_READ_ONLY": "1"},
    )

    assert config["tools"] == [
        "research_semantic_discover",
        "research_discover_search",
        "research_describe_dataset",
        "research_query_dataset",
        "research_synthesis_pair",
        "research_synthesis_propose_state",
    ]


def test_general_mcp_allowlist_excludes_known_bigint_crash_tools(monkeypatch):
    monkeypatch.setenv("DESK_COPILOT_ACCOUNTS", "primary")
    monkeypatch.setattr(desk_copilot_provider, "copilot_composer_available", lambda: True)
    bindings = desk_copilot_provider.load_copilot_cursor_bindings("primary")

    config = bindings.stdio_mcp_server_config(
        command="python",
        args=["-m", "server"],
        cwd="/tmp/repo",
        env={},
    )

    assert "research_semantic_discover" in config["tools"]
    assert "research_discover_search" in config["tools"]
    assert "yzu_submit_job" in config["tools"]
    assert "research_unified_search" not in config["tools"]
    assert "research_list_datasets" not in config["tools"]
    assert "*" not in config["tools"]


def test_final_assistant_reply_prefers_post_tool_top_level_message():
    def event(content, *, parent=None):
        return SimpleNamespace(
            type=SimpleNamespace(value="assistant.message"),
            data=SimpleNamespace(content=content, parent_tool_call_id=parent),
        )

    events = [
        event("I will inspect the evidence."),
        event("Nested worker text", parent="tool-1"),
        event("Grounded final answer."),
    ]

    assert desk_copilot_provider._final_assistant_reply(events) == "Grounded final answer."


def test_copilot_conversation_prefers_structured_mcp_result():
    payload = {
        "thread_id": "thread-1",
        "synthesis_proposal": {"id": "proposal-1"},
    }
    events = [
        SimpleNamespace(
            type="tool.execution_start",
            data=SimpleNamespace(
                tool_call_id="call-1",
                mcp_tool_name="research_synthesis_propose_state",
            ),
        ),
        SimpleNamespace(
            type="tool.execution_complete",
            data=SimpleNamespace(
                tool_call_id="call-1",
                result=SimpleNamespace(
                    content='{"thread_id":"thread-1"}\n{"thread_id":"thread-1"}',
                    structured_content=payload,
                ),
            ),
        ),
    ]

    messages = desk_copilot_provider._conversation_messages(events)

    assert len(messages) == 1
    assert messages[0].result == payload


def test_composer_artifacts_parse_first_object_from_repeated_mcp_content():
    payload = {
        "thread_id": "thread-1",
        "synthesis_proposal": {"id": "proposal-1"},
    }
    repeated = json.dumps(payload) + "\n\n" + json.dumps(payload)
    run = SimpleNamespace(
        conversation=lambda: [
            SimpleNamespace(
                steps=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            type="tool_call",
                            name="research_synthesis_propose_state",
                            result=repeated,
                        )
                    )
                ]
            )
        ]
    )

    artifacts = desk_brain._artifacts_from_conversation(run)

    assert artifacts["synthesis_thread_id"] == "thread-1"
    assert artifacts["synthesis_proposal"]["id"] == "proposal-1"


def test_copilot_pool_preflight_requires_every_configured_identity(monkeypatch, tmp_path):
    launcher = tmp_path / "copilot-launcher"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o700)
    monkeypatch.setattr(
        copilot_pool_preflight,
        "configured_copilot_accounts",
        lambda: ["primary", "secondary"],
    )
    monkeypatch.setattr(copilot_pool_preflight, "copilot_launcher_path", lambda: launcher)
    monkeypatch.setattr(
        copilot_pool_preflight.importlib.metadata,
        "version",
        lambda _name: "1.0.11",
    )

    result = copilot_pool_preflight.probe_copilot_pool(
        runner=lambda *_a, **_k: SimpleNamespace(returncode=0, stdout="primary\n")
    )

    assert result["ready"] is False
    assert result["active_requested_accounts"] == ["primary"]
    assert "secondary" in result["problems"][0]


def test_explicit_copilot_provider_fails_closed_when_unavailable(monkeypatch):
    monkeypatch.setenv("DESK_COMPOSER_PROVIDER", "copilot")
    monkeypatch.setattr(desk_brain, "copilot_composer_available", lambda: False)
    monkeypatch.setattr(desk_brain, "cursor_composer_available", lambda: True)

    assert desk_brain.selected_composer_provider() == "unavailable"
    assert desk_brain.desk_brain_mode() == "unavailable"


def test_auto_provider_preserves_cursor_precedence(monkeypatch):
    monkeypatch.setenv("DESK_COMPOSER_PROVIDER", "auto")
    monkeypatch.setattr(desk_brain, "copilot_composer_available", lambda: True)
    monkeypatch.setattr(desk_brain, "cursor_composer_available", lambda: True)

    assert desk_brain.selected_composer_provider() == "cursor_composer"


def test_copilot_turn_reuses_shared_contract_and_reports_assignment(monkeypatch):
    monkeypatch.setattr(
        desk_copilot_provider,
        "choose_copilot_account",
        lambda session_id, state: "primary",
    )
    monkeypatch.setattr(
        desk_copilot_provider,
        "configured_copilot_accounts",
        lambda: ["primary", "secondary"],
    )
    bindings = SimpleNamespace()
    monkeypatch.setattr(
        desk_copilot_provider,
        "load_copilot_cursor_bindings",
        lambda account: bindings,
    )
    captured = {}

    def fake_shared(*args, **kwargs):
        captured.update(kwargs)
        return AgentTurn(
            plan={"action": "composer"},
            action_result={"action": "composer"},
            reply="Grounded response.",
        )

    monkeypatch.setattr(desk_brain, "run_cursor_composer_turn", fake_shared)

    turn = desk_brain.run_copilot_composer_turn(
        SimpleNamespace(repo_root="/tmp/repo"),
        "Assess this construct",
        {},
        session_id="desk-session",
    )

    assert captured["_sdk_override"] is bindings
    assert captured["_brain_override"] == "copilot_composer"
    assert captured["_models_override"] == ["auto"]
    assert captured["_agent_state_key"] == "copilot_session_id"
    assert turn.action_result["copilot_account"] == "primary"
    assert turn.action_result["copilot_pool_size"] == 2


def test_desk_turn_dispatches_to_selected_copilot_provider(monkeypatch):
    monkeypatch.setattr(desk_brain, "selected_composer_provider", lambda: "copilot_composer")
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_direct_turns.try_direct_equipment_turn",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_direct_turns.try_direct_synthesis_read_turn",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_synthesis_contract.synthesis_first_turn",
        lambda _state: False,
    )
    expected = AgentTurn(
        plan={"action": "composer"},
        action_result={"brain": "copilot_composer"},
        reply="Copilot response.",
    )
    monkeypatch.setattr(desk_brain, "run_copilot_composer_turn", lambda *_a, **_k: expected)

    actual = desk_brain.run_desk_agent_turn(
        None,
        SimpleNamespace(repo_root="/tmp/repo"),
        "hello",
        {},
        session_id="desk-session",
    )

    assert actual is expected


def test_first_copilot_synthesis_turn_retries_until_evidence_tool_is_used(monkeypatch):
    class FakeRun:
        status = "completed"
        model = "gpt-test"

        def __init__(self, reply, messages=()):
            self.reply = reply
            self.messages = list(messages)

        def wait(self):
            return None

        def text(self):
            return self.reply

        def conversation(self):
            steps = [SimpleNamespace(message=message) for message in self.messages]
            return [SimpleNamespace(steps=steps)] if steps else []

    class FakeAgent:
        agent_id = "copilot-session"
        sends = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def close(self):
            return None

        def send(self, text, options):
            self.sends.append(text)
            if len(self.sends) == 1:
                return FakeRun(
                    "Provisional interpretation based on supplied context. "
                    "Which definition should govern the construct?"
                )
            options.on_delta(
                {
                    "type": "tool-call-started",
                    "tool_call": {"name": "research_describe_dataset"},
                }
            )
            message = SimpleNamespace(
                type="tool_call",
                name="research_describe_dataset",
                result='{"dataset_id":"held_panel"}',
            )
            return FakeRun(
                "Provisional interpretation grounded in held_panel. Supported facts "
                "remain separate from proposed proxy choices and unresolved limitations. "
                "Which definition should govern the construct?",
                [message],
            )

    fake_agent = FakeAgent()
    sdk = desk_brain._CursorSdkBindings(
        agent=SimpleNamespace(
            create=lambda _options: fake_agent,
            resume=lambda _agent_id, _options: fake_agent,
        ),
        agent_options=lambda **kwargs: SimpleNamespace(**kwargs),
        model_selection=lambda **kwargs: SimpleNamespace(**kwargs),
        send_options=lambda **kwargs: SimpleNamespace(**kwargs),
        stdio_mcp_server_config=lambda **kwargs: kwargs,
        local_agent_options=lambda **kwargs: kwargs,
        cloud_agent_options=lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(desk_brain, "_durable_synthesis_thread_brief", lambda *_a: "")
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_synthesis_grounding.build_synthesis_grounding_brief",
        lambda *_a, **_k: "Verified grounding brief.",
    )
    gateway = MagicMock()
    gateway.repo_root = "/tmp/repo"
    state = {
        "desk_primed": True,
        "rail_context": {
            "tab": "synthesis",
            "thread_id": "thread-1",
            "entity": {"kind": "synthesis_thread", "id": "thread-1"},
        },
    }

    turn = desk_brain.run_cursor_composer_turn(
        gateway,
        "Assess the construct",
        state,
        _sdk_override=sdk,
        _credential_override="managed",
        _brain_override="copilot_composer",
        _models_override=["auto"],
        _agent_state_key="copilot_session_id",
    )

    assert len(fake_agent.sends) == 2
    assert "Use at least one available Research MCP tool now" in fake_agent.sends[1]
    assert turn.action_result["synthesis_contract_validated"] is True
    assert turn.action_result["composer_model"] == "gpt-test"


def test_later_synthesis_turn_does_not_require_first_turn_language(monkeypatch):
    """A grounded follow-up must not be rejected for lacking a new question."""

    class FakeRun:
        status = "completed"
        model = "gpt-test"

        def wait(self):
            return None

        def text(self):
            return "The recorded grain is ticker_day; its coverage remains limited."

        def conversation(self):
            return []

    class FakeAgent:
        agent_id = "copilot-session"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send(self, *_args, **_kwargs):
            return FakeRun()

    sdk = desk_brain._CursorSdkBindings(
        agent=SimpleNamespace(create=lambda _options: FakeAgent()),
        agent_options=lambda **kwargs: SimpleNamespace(**kwargs),
        model_selection=lambda **kwargs: SimpleNamespace(**kwargs),
        send_options=lambda **kwargs: SimpleNamespace(**kwargs),
        stdio_mcp_server_config=lambda **kwargs: kwargs,
        local_agent_options=lambda **kwargs: kwargs,
        cloud_agent_options=lambda **kwargs: kwargs,
    )
    gateway = MagicMock()
    gateway.repo_root = "/tmp/repo"
    state = {
        "desk_primed": True,
        "rail_context": {
            "tab": "synthesis",
            "thread_id": "thread-1",
            "entity": {"kind": "synthesis_thread", "id": "thread-1"},
        },
        "synthesis_thread_turns": {"thread-1": 1},
    }

    turn = desk_brain.run_cursor_composer_turn(
        gateway,
        "State the recorded limitation.",
        state,
        _sdk_override=sdk,
        _credential_override="managed",
        _brain_override="copilot_composer",
        _models_override=["auto"],
        _agent_state_key="copilot_session_id",
    )

    assert turn.action_result["action"] == "composer"
    assert "contract_violations" not in turn.action_result
    assert state["synthesis_thread_turns"]["thread-1"] == 2


def test_copilot_records_requested_synthesis_proposal_after_grounding(monkeypatch):
    proposal = {
        "id": "proposal-1",
        "title": "Monthly JKSE regime construction",
        "summary": "Review-only construction grounded in held evidence.",
        "operations": [{"op": "update_spec", "value": {"grain": "month"}}],
    }
    grounded_reply = (
        "Provisional interpretation grounded in the held JKSE panel. Supported "
        "facts remain separate from proposed proxy choices and unresolved "
        "limitations. Which threshold definition should govern the construct?"
    )

    class FakeRun:
        status = "completed"
        model = "gpt-test"

        def __init__(self, reply, messages=()):
            self.reply = reply
            self.messages = list(messages)

        def wait(self):
            return None

        def text(self):
            return self.reply

        def conversation(self):
            steps = [SimpleNamespace(message=message) for message in self.messages]
            return [SimpleNamespace(steps=steps)] if steps else []

    class FakeAgent:
        agent_id = "copilot-session"

        def __init__(self):
            self.sends = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def close(self):
            return None

        def send(self, text, options):
            self.sends.append(text)
            if len(self.sends) == 1:
                options.on_delta(
                    {
                        "type": "tool-call-started",
                        "tool_call": {"name": "research_query_dataset"},
                    }
                )
                message = SimpleNamespace(
                    type="tool_call",
                    name="research_query_dataset",
                    result='{"dataset_id":"held_panel"}',
                )
                return FakeRun(grounded_reply, [message])
            options.on_delta(
                {
                    "type": "tool-call-started",
                    "tool_call": {"name": "research_synthesis_propose_state"},
                }
            )
            message = SimpleNamespace(
                type="tool_call",
                name="research_synthesis_propose_state",
                result=json.dumps(
                    {"thread_id": "thread-1", "synthesis_proposal": proposal}
                ),
            )
            return FakeRun("Proposal recorded for review.", [message])

    fake_agent = FakeAgent()
    sdk = desk_brain._CursorSdkBindings(
        agent=SimpleNamespace(
            create=lambda _options: fake_agent,
            resume=lambda _agent_id, _options: fake_agent,
        ),
        agent_options=lambda **kwargs: SimpleNamespace(**kwargs),
        model_selection=lambda **kwargs: SimpleNamespace(**kwargs),
        send_options=lambda **kwargs: SimpleNamespace(**kwargs),
        stdio_mcp_server_config=lambda **kwargs: kwargs,
        local_agent_options=lambda **kwargs: kwargs,
        cloud_agent_options=lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(desk_brain, "_durable_synthesis_thread_brief", lambda *_a: "")
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_synthesis_grounding.build_synthesis_grounding_brief",
        lambda *_a, **_k: "Verified grounding brief.",
    )
    gateway = MagicMock()
    gateway.repo_root = "/tmp/repo"
    state = {
        "desk_primed": True,
        "rail_context": {
            "tab": "synthesis",
            "thread_id": "thread-1",
            "entity": {"kind": "synthesis_thread", "id": "thread-1"},
        },
    }

    turn = desk_brain.run_cursor_composer_turn(
        gateway,
        "Create and record one reviewable Synthesis proposal.",
        state,
        _sdk_override=sdk,
        _credential_override="managed",
        _brain_override="copilot_composer",
        _models_override=["auto"],
        _agent_state_key="copilot_session_id",
    )

    assert len(fake_agent.sends) == 2
    assert "research_synthesis_propose_state" in fake_agent.sends[1]
    assert turn.reply == grounded_reply
    assert turn.action_result["synthesis_proposal"] == proposal
    assert turn.action_result["synthesis_contract_validated"] is True


def test_later_synthesis_turn_keeps_read_only_direct_routing(monkeypatch):
    monkeypatch.setattr(desk_brain, "selected_composer_provider", lambda: "copilot_composer")
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_direct_turns.try_direct_equipment_turn",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Synthesis must not use equipment fast paths")
        ),
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_direct_turns.try_direct_synthesis_read_turn",
        lambda *_args, **_kwargs: None,
    )
    expected = AgentTurn(
        plan={"action": "composer"},
        action_result={"brain": "copilot_composer"},
        reply="Copilot response.",
    )
    monkeypatch.setattr(desk_brain, "run_copilot_composer_turn", lambda *_a, **_k: expected)
    state = {
        "rail_context": {
            "tab": "synthesis",
            "thread_id": "thread-1",
            "entity": {"kind": "synthesis_thread", "id": "thread-1"},
        },
        "synthesis_thread_turns": {"thread-1": 1},
    }

    actual = desk_brain.run_desk_agent_turn(
        None,
        SimpleNamespace(repo_root="/tmp/repo"),
        "Record the proposal for review",
        state,
        session_id="desk-session",
    )

    assert actual is expected


def test_desk_warm_primes_selected_copilot_session(monkeypatch):
    from scripts.research_data_mcp import desk_warm

    monkeypatch.setattr(desk_brain, "desk_brain_mode", lambda _root=None: "copilot_composer")

    def fake_copilot(_gateway, _message, state, **_kwargs):
        state["copilot_session_id"] = "copilot-prime-session"
        return AgentTurn(
            plan={"action": "composer"},
            action_result={"action": "composer"},
            reply="Ready",
        )

    monkeypatch.setattr(desk_brain, "run_copilot_composer_turn", fake_copilot)
    monkeypatch.setattr(
        desk_brain,
        "run_cursor_composer_turn",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("Cursor must not run")),
    )
    state = {"vault_brief": "Verified Library brief."}

    primed = desk_warm.prime_desk_agent(
        SimpleNamespace(repo_root="/tmp/repo"),
        state,
        "desk-session",
    )

    assert primed is True
    assert state["desk_primed"] is True
    assert state["copilot_session_id"] == "copilot-prime-session"


def test_runtime_probe_requires_every_approved_account(monkeypatch):
    from scripts.research_data_mcp import desk_composer_health, desk_warm

    desk_composer_health._reset_composer_runtime_status()
    monkeypatch.setattr(
        desk_brain,
        "selected_composer_provider",
        lambda: "copilot_composer",
    )
    monkeypatch.setattr(
        desk_copilot_provider,
        "probe_copilot_pool",
        lambda: {
            "ready": True,
            "accounts": [
                {"account": "primary", "ready": True, "model": "gpt-one"},
                {"account": "secondary", "ready": True, "model": "gpt-two"},
            ],
        },
    )

    result = desk_warm.probe_composer_runtime()
    status = desk_composer_health.composer_runtime_status(configured=True)

    assert result["ready"] is True
    assert status["status"] == "ready"
    assert status["probe_source"] == "periodic_pool"
    assert [row["account"] for row in status["provider_accounts"]] == [
        "primary",
        "secondary",
    ]
    assert all(row["ready"] is True for row in status["provider_accounts"])


def test_runtime_probe_fails_closed_when_one_pool_member_fails(monkeypatch):
    from scripts.research_data_mcp import desk_composer_health, desk_warm

    desk_composer_health._reset_composer_runtime_status()
    monkeypatch.setattr(
        desk_brain,
        "selected_composer_provider",
        lambda: "copilot_composer",
    )
    monkeypatch.setattr(
        desk_copilot_provider,
        "probe_copilot_pool",
        lambda: {
            "ready": False,
            "accounts": [
                {"account": "primary", "ready": True, "model": "gpt-one"},
                {
                    "account": "secondary",
                    "ready": False,
                    "error_category": "AuthenticationError",
                },
            ],
        },
    )

    result = desk_warm.probe_composer_runtime()
    status = desk_composer_health.composer_runtime_status(configured=True)

    assert result["ready"] is False
    assert status["status"] == "degraded"
    assert status["verified"] is True
    assert status["provider_accounts"][1]["ready"] is False


def test_probe_interval_is_bounded(monkeypatch):
    from scripts.research_data_mcp import desk_warm

    monkeypatch.setenv("DESK_COMPOSER_PROBE_INTERVAL_SECONDS", "1")
    assert desk_warm.composer_probe_interval_seconds() == 300
    monkeypatch.setenv("DESK_COMPOSER_PROBE_INTERVAL_SECONDS", "999999")
    assert desk_warm.composer_probe_interval_seconds() == 86_400
