"""Synthesis failover stays grounded, read-only, and operationally honest."""

from __future__ import annotations

import io
import json
import sys
import types
import urllib.error


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_gemini_fallback_uses_read_only_generate_content(monkeypatch):
    from scripts.research_data_mcp import desk_synthesis_fallback as fallback

    fallback._reset_synthesis_fallback_runtime_status()
    monkeypatch.setenv("DESK_SYNTHESIS_GEMINI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key")
    monkeypatch.setenv("DESK_SYNTHESIS_GEMINI_MODEL", "gemini-test")
    observed = {}

    def fake_open(request, timeout):
        observed["url"] = request.full_url
        observed["key"] = request.get_header("X-goog-api-key")
        observed["payload"] = json.loads(request.data.decode("utf-8"))
        observed["timeout"] = timeout
        return _Response(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        "A provisional proxy could use the supplied "
                                        "Library evidence. Which horizon matters most?"
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(fallback.urllib.request, "urlopen", fake_open)
    reply, metadata = fallback.run_gemini_synthesis_turn("Grounded prompt")

    assert reply.startswith("A provisional proxy")
    assert observed["url"].endswith("/models/gemini-test:generateContent")
    assert observed["key"] == "secret-test-key"
    assert observed["payload"]["system_instruction"]
    assert "Never claim to have collected" in observed["payload"]["system_instruction"]["parts"][0]["text"]
    assert observed["payload"]["contents"][0]["parts"][0]["text"] == "Grounded prompt"
    assert metadata == {
        "provider": "gemini",
        "model": "gemini-test",
        "read_only": True,
        "grounding": "research_drive",
    }
    status = fallback.synthesis_fallback_runtime_status()
    assert status["status"] == "ready"
    assert status["verified"] is True
    assert status["error_category"] is None


def test_gemini_invalid_key_is_sanitised_and_reported(monkeypatch):
    from scripts.research_data_mcp import desk_synthesis_fallback as fallback

    fallback._reset_synthesis_fallback_runtime_status()
    monkeypatch.setenv("DESK_SYNTHESIS_GEMINI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key")
    body = io.BytesIO(
        json.dumps(
            {"error": {"message": "API key not valid. Please pass a valid API key."}}
        ).encode("utf-8")
    )

    def fake_open(_request, timeout):
        _ = timeout
        raise urllib.error.HTTPError(
            "https://example.invalid",
            400,
            "Bad Request",
            {},
            body,
        )

    monkeypatch.setattr(fallback.urllib.request, "urlopen", fake_open)
    try:
        fallback.run_gemini_synthesis_turn("Grounded prompt")
    except fallback.SynthesisFallbackError as exc:
        assert exc.category == "authentication"
        assert exc.status_code == 400
        assert "secret-test-key" not in str(exc)
    else:
        raise AssertionError("invalid key must fail")

    status = fallback.synthesis_fallback_runtime_status()
    assert status["status"] == "degraded"
    assert status["error_category"] == "authentication"
    assert "secret-test-key" not in str(status)


def test_fallback_status_is_unverified_until_a_real_call(monkeypatch):
    from scripts.research_data_mcp import desk_synthesis_fallback as fallback

    fallback._reset_synthesis_fallback_runtime_status()
    monkeypatch.setenv("DESK_SYNTHESIS_GEMINI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "configured-not-proven")
    status = fallback.synthesis_fallback_runtime_status()
    assert status["status"] == "unverified"
    assert status["configured"] is True
    assert status["verified"] is False


def test_fallback_is_disabled_without_explicit_operator_opt_in(monkeypatch):
    from scripts.research_data_mcp import desk_synthesis_fallback as fallback

    fallback._reset_synthesis_fallback_runtime_status()
    monkeypatch.delenv("DESK_SYNTHESIS_GEMINI_ENABLED", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "present-but-not-authorised")

    status = fallback.synthesis_fallback_runtime_status()
    assert status["status"] == "disabled"
    assert status["configured"] is False
    assert status["error_category"] == "disabled_by_policy"
    try:
        fallback.run_gemini_synthesis_turn("private research question")
    except fallback.SynthesisFallbackError as exc:
        assert exc.category == "disabled_by_policy"
    else:
        raise AssertionError("external fallback must require explicit opt-in")


def _install_failing_cursor(monkeypatch):
    class FailingAgent:
        @classmethod
        def create(cls, _opts):
            raise RuntimeError("cursor provider unavailable")

        @classmethod
        def resume(cls, _agent_id, _opts):
            raise RuntimeError("cursor provider unavailable")

    cursor_sdk = types.ModuleType("cursor_sdk")
    cursor_sdk.Agent = FailingAgent
    cursor_types = types.ModuleType("cursor_sdk.types")
    cursor_types.AgentOptions = lambda **kwargs: kwargs
    cursor_types.ModelSelection = lambda **kwargs: kwargs
    cursor_types.SendOptions = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "cursor_sdk", cursor_sdk)
    monkeypatch.setitem(sys.modules, "cursor_sdk.types", cursor_types)


def test_cursor_failure_fails_over_with_bounded_project_memory(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain, desk_synthesis_fallback

    _install_failing_cursor(monkeypatch)
    monkeypatch.setenv("CURSOR_API_KEY", "cursor-test")
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda _root: {})
    observed = {}

    def fake_fallback(prompt):
        observed["prompt"] = prompt
        return (
            (
                "A provisional coordination proxy could combine the indexed "
                "evidence while preserving measurement and timing limitations. "
                "Which weekly event window should define coordination?"
            ),
            {
                "provider": "gemini",
                "model": "gemini-test",
                "read_only": True,
                "grounding": "research_drive",
            },
        )

    monkeypatch.setattr(
        desk_synthesis_fallback,
        "run_gemini_synthesis_turn",
        fake_fallback,
    )
    gateway = types.SimpleNamespace(
        repo_root=tmp_path,
        synthesis_list_profiles=lambda: {"profiles": []},
    )
    state = {
        "desk_primed": True,
        "rail_context": {"tab": "synthesis", "mode": "define"},
        "synthesis_user_turns": 1,
        "synthesis_turn_history": [
            {
                "user": "Construct coordination.",
                "assistant": "A provisional definition needs a time horizon?",
                "provider": "cursor_composer",
            }
        ],
    }

    turn = desk_brain.run_cursor_composer_turn(
        gateway,
        "Use a weekly horizon.",
        state,
    )

    assert turn.action_result["action"] == "synthesis_reasoning"
    assert turn.action_result["brain"] == "gemini_synthesis"
    assert turn.action_result["read_only"] is True
    assert turn.action_result["fallback_from"] == "cursor_composer"
    assert "[Prior Synthesis turns]" in observed["prompt"]
    assert "Construct coordination." in observed["prompt"]
    assert state["synthesis_user_turns"] == 2
    assert state["synthesis_turn_history"][-1]["provider"] == "gemini"


def test_fallback_contract_violation_is_not_surfaced(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain, desk_synthesis_fallback

    _install_failing_cursor(monkeypatch)
    monkeypatch.setenv("CURSOR_API_KEY", "cursor-test")
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda _root: {})
    monkeypatch.setattr(
        desk_synthesis_fallback,
        "run_gemini_synthesis_turn",
        lambda _prompt: (
            "I have collected and registered the final dataset.",
            {
                "provider": "gemini",
                "model": "gemini-test",
                "read_only": True,
                "grounding": "research_drive",
            },
        ),
    )
    gateway = types.SimpleNamespace(
        repo_root=tmp_path,
        synthesis_list_profiles=lambda: {"profiles": []},
    )
    state = {
        "desk_primed": True,
        "rail_context": {"tab": "synthesis", "mode": "define"},
    }

    turn = desk_brain.run_cursor_composer_turn(gateway, "Build a proxy", state)

    assert turn.action_result["action"] == "composer_error"
    assert turn.action_result["fallback"] == "gemini_failed"
    assert turn.action_result["fallback_error_category"] == "contract_violation"
    assert "collected and registered" not in turn.reply
    assert state.get("synthesis_user_turns") is None
