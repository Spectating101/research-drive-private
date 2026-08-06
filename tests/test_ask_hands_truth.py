"""Ask hands policy + artifact-true action labels."""

from __future__ import annotations

import os


def test_infer_action_label_ignores_reply_prose():
    from scripts.research_data_mcp.procurement_chat import ProcurementChatOrchestrator

    label = ProcurementChatOrchestrator._infer_action_label(
        "What should I collect next?",
        "I queued a collection job for DOI 10.5281/zenodo.1 and scheduled a weekly refresh.",
        "composer",
        {},
    )
    assert label == "composer"


def test_infer_action_label_uses_job_artifact():
    from scripts.research_data_mcp.procurement_chat import ProcurementChatOrchestrator

    label = ProcurementChatOrchestrator._infer_action_label(
        "collect it",
        "anything",
        "composer",
        {"job": {"id": "job-1", "status": "queued"}},
    )
    assert label == "queue"


def test_infer_action_label_uses_subscription_artifact():
    from scripts.research_data_mcp.procurement_chat import ProcurementChatOrchestrator

    label = ProcurementChatOrchestrator._infer_action_label(
        "refresh weekly",
        "scheduled",
        "composer",
        {"platform_registered": True, "subscription_id": "sub-1"},
    )
    assert label == "schedule_refresh"


def test_ask_mcp_stays_attached_when_strong_held(monkeypatch, tmp_path):
    """Hands remain available even when DESK_FACTS already measured strong holdings."""
    import types
    import sys
    from scripts.research_data_mcp import desk_brain

    class SuccessfulRun:
        status = "success"

        def wait(self):
            return None

        def text(self):
            return "You can preview this held panel now."

        def conversation(self):
            return []

    seen = {"mcp": None}

    class CapturingAgent:
        agent_id = "agent-mcp"

        @classmethod
        def create(cls, opts):
            seen["mcp"] = getattr(opts, "mcp_servers", None) or (
                opts.get("mcp_servers") if isinstance(opts, dict) else None
            )
            return cls()

        @classmethod
        def resume(cls, _agent_id, opts):
            return cls.create(opts)

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def send(self, _text, _opts):
            return SuccessfulRun()

    cursor_sdk = types.ModuleType("cursor_sdk")
    cursor_sdk.Agent = CapturingAgent
    cursor_types = types.ModuleType("cursor_sdk.types")
    cursor_types.AgentOptions = lambda **kwargs: kwargs
    cursor_types.ModelSelection = lambda **kwargs: kwargs
    cursor_types.SendOptions = lambda **kwargs: kwargs
    cursor_types.StdioMcpServerConfig = lambda **kwargs: kwargs
    cursor_types.LocalAgentOptions = lambda **kwargs: kwargs
    cursor_types.CloudAgentOptions = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "cursor_sdk", cursor_sdk)
    monkeypatch.setitem(sys.modules, "cursor_sdk.types", cursor_types)
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.delenv("DESK_ASK_ATTACH_MCP", raising=False)
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(
        desk_brain,
        "_mcp_stdio_config",
        lambda *_a, **_k: {"research_procurement": {"command": "true"}},
    )
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda *_a, **_k: {})

    state = {
        "desk_primed": True,
        "ask_desk_facts": {"strong_held": True, "held_count": 1, "route_count": 0},
        "_ask_desk_measure": {
            "strong_held": True,
            "held": [{"dataset_id": "x", "title": "X"}],
            "routes": [],
            "held_count": 1,
            "route_count": 0,
            "query": "stablecoin",
        },
        "rail_context": {"tab": "library", "surface": "library"},
    }
    # Force ask_desk_grounded path by leaving vault brief present and non-prime
    turn = desk_brain.run_cursor_composer_turn(
        types.SimpleNamespace(repo_root=tmp_path),
        "Can I query this now?",
        state,
    )
    assert state.get("ask_mcp_attached") is True
    assert seen["mcp"], "MCP servers should be attached for strong_held Ask"
    assert turn.reply.startswith("You can preview")


def test_ask_mcp_can_still_be_forced_off(monkeypatch, tmp_path):
    import types
    import sys
    from scripts.research_data_mcp import desk_brain

    class SuccessfulRun:
        status = "success"

        def wait(self):
            return None

        def text(self):
            return "Answer without tools."

        def conversation(self):
            return []

    class Agent:
        agent_id = "agent-off"

        @classmethod
        def create(cls, _opts):
            return cls()

        @classmethod
        def resume(cls, _id, _opts):
            return cls()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def send(self, _text, _opts):
            return SuccessfulRun()

    cursor_sdk = types.ModuleType("cursor_sdk")
    cursor_sdk.Agent = Agent
    cursor_types = types.ModuleType("cursor_sdk.types")
    cursor_types.AgentOptions = lambda **kwargs: kwargs
    cursor_types.ModelSelection = lambda **kwargs: kwargs
    cursor_types.SendOptions = lambda **kwargs: kwargs
    cursor_types.StdioMcpServerConfig = lambda **kwargs: kwargs
    cursor_types.LocalAgentOptions = lambda **kwargs: kwargs
    cursor_types.CloudAgentOptions = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "cursor_sdk", cursor_sdk)
    monkeypatch.setitem(sys.modules, "cursor_sdk.types", cursor_types)
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setenv("DESK_ASK_ATTACH_MCP", "0")
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(
        desk_brain,
        "_mcp_stdio_config",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("mcp must not be built")),
    )
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda *_a, **_k: {})

    state = {
        "desk_primed": True,
        "ask_desk_facts": {"strong_held": False},
        "_ask_desk_measure": {
            "strong_held": False,
            "held": [],
            "routes": [],
            "held_count": 0,
            "route_count": 0,
            "query": "x",
        },
    }
    desk_brain.run_cursor_composer_turn(
        types.SimpleNamespace(repo_root=tmp_path),
        "hello",
        state,
    )
    assert state.get("ask_mcp_attached") is False
