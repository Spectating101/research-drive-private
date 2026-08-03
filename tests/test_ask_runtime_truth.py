#!/usr/bin/env python3
"""Ask/Composer runtime truth — health honesty, bounded timeout, contextual direct turns."""

from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "kernel"), str(REPO / "drive")]


@pytest.fixture()
def desk_brain(monkeypatch):
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.delenv("DESK_CHAT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("DESK_COMPOSER_SLA_SECONDS", raising=False)
    monkeypatch.delenv("DESK_COMPOSER_FORCE_UNAVAILABLE", raising=False)
    from scripts.research_data_mcp import desk_brain as mod

    importlib.reload(mod)
    return mod


def test_desk_brain_mode_not_optimistic_without_composer(desk_brain, monkeypatch):
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    importlib.reload(desk_brain)
    assert desk_brain.cursor_composer_available() is False
    mode = desk_brain.desk_brain_mode()
    assert mode != "cursor_composer"
    assert mode in {"direct", "fallback", "unavailable"}
    status = desk_brain.composer_runtime_status()
    assert status["composer_configured"] is False
    assert status["brain"] == mode
    assert status["composer_status"] in {"direct", "fallback", "unavailable"}


def test_desk_brain_mode_composer_only_when_plausibly_invocable(desk_brain, monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_load_cursor_sdk_bindings", lambda: SimpleNamespace())
    assert desk_brain.cursor_composer_available() is True
    assert desk_brain.desk_brain_mode() == "cursor_composer"
    status = desk_brain.composer_runtime_status()
    assert status["composer_configured"] is True
    assert status["composer_status"] == "unverified"
    assert status["brain"] == "cursor_composer"


def test_health_payload_consumes_composer_runtime_status(desk_brain, monkeypatch):
    """desk_health must project composer_runtime_status — not a static optimistic brain."""
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    importlib.reload(desk_brain)
    status = desk_brain.composer_runtime_status()
    assert status["composer_configured"] is False
    assert status["brain"] != "cursor_composer"

    captured: dict = {}

    def _fake_runtime_status(repo_root=None):
        captured["called_with"] = repo_root
        return {
            "brain": "direct",
            "composer_configured": False,
            "composer_status": "direct",
        }

    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_brain.composer_runtime_status",
        _fake_runtime_status,
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.storage_tiers.storage_tiers_status",
        lambda _root: {
            "canonical": {
                "quota_tb": 1,
                "pool_tb": 1,
                "label": "test",
                "drive_root": "/tmp",
                "role": "canonical",
                "used_tb": 0,
            },
            "cache": {},
        },
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_auth.access_token_required",
        lambda: False,
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.llm_client.llm_configured",
        lambda: False,
    )

    gateway = MagicMock()
    gateway.repo_root = REPO
    gateway.orchestrator = MagicMock()
    gateway.orchestrator.stats.return_value = {}
    gateway.orchestrator.cfg = {"storage": {}}
    gateway._serve_ui = False
    gateway.inventory_summary = MagicMock(
        return_value={
            "totals": {
                "registered": 0,
                "visible_to_desk": 0,
                "excluded_operational_test": 0,
            },
            "by_analysis_readiness": {"registered": {}},
            "by_materialization_query_ready": {"registered": {}},
            "registry_revision": {"fingerprint": "test"},
        }
    )
    gateway.engine = MagicMock()
    gateway.engine.list_datasets.return_value = []
    gateway.platform_state = MagicMock(return_value={"found": False})

    from scripts.research_data_mcp.gateway import ResearchDataGateway

    out = ResearchDataGateway.desk_health(gateway, live=False)
    desk = out["desk"]
    assert "called_with" in captured
    assert desk["brain"] == "direct"
    assert desk["composer_configured"] is False
    assert desk["composer_status"] == "direct"
    assert desk["brain"] != "cursor_composer"


def test_chat_timeout_env_bounded(desk_brain, monkeypatch):
    from scripts.research_data_mcp import desk_scale

    monkeypatch.setenv("DESK_CHAT_TIMEOUT_SECONDS", "12")
    importlib.reload(desk_scale)
    assert desk_scale.chat_timeout_seconds() == 12.0
    monkeypatch.delenv("DESK_CHAT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("DESK_COMPOSER_SLA_SECONDS", "18")
    importlib.reload(desk_scale)
    assert desk_scale.chat_timeout_seconds() == 18.0


def test_wait_run_bounded_returns_promptly_on_timeout(desk_brain):
    """Timeout must not block until the stuck wait() releases (executor shutdown trap)."""
    released = threading.Event()

    class _FakeRun:
        def wait(self) -> None:
            # Stay blocked far longer than the bound unless released.
            released.wait(timeout=30)

    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        desk_brain._wait_run_bounded(_FakeRun(), 1.0)
    elapsed = time.monotonic() - t0
    released.set()
    assert elapsed < 5.0, (
        f"_wait_run_bounded blocked {elapsed:.1f}s — executor shutdown likely waited "
        "for the stuck worker (use shutdown(wait=False, cancel_futures=True))"
    )


def test_blocking_composer_times_out_with_typed_error(tmp_path, monkeypatch):
    # Floor is 5s in chat_timeout_seconds(); keep the bound tight for the hang proof.
    monkeypatch.setenv("DESK_CHAT_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "cursor_sdk", SimpleNamespace())

    from scripts.research_data_mcp import desk_brain, desk_scale, procurement_chat

    importlib.reload(desk_scale)
    importlib.reload(desk_brain)
    importlib.reload(procurement_chat)

    started = threading.Event()
    released = threading.Event()

    def _blocking_composer(*_a, **_k):
        started.set()
        released.wait(timeout=30)
        return desk_brain.AgentTurn(
            plan={"action": "composer"},
            action_result={"action": "composer"},
            reply="should-not-surface",
            suggested_prompts=[],
            tool_name="cursor_composer",
        )

    monkeypatch.setattr(desk_brain, "run_cursor_composer_turn", _blocking_composer)
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_brain.run_cursor_composer_turn",
        _blocking_composer,
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_warm.warm_desk_session",
        lambda *_a, **_k: {"session_id": "x", "primed": False, "priming": False},
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_vault_brief.build_vault_brief",
        lambda *_a, **_k: "vault brief",
    )

    orch = procurement_chat.ProcurementChatOrchestrator(tmp_path)
    gateway = MagicMock()
    gateway.repo_root = tmp_path

    t0 = time.monotonic()
    result = orch.chat(gateway, "Help me plan a multi-source synthesis strategy for Taiwan equities")
    elapsed = time.monotonic() - t0

    assert elapsed < 12.0, f"chat hung for {elapsed:.1f}s under 5s timeout"
    assert started.is_set()
    artifacts = result.get("artifacts") or {}
    assert result.get("action") == "composer_timeout" or artifacts.get("action") == "composer_timeout"
    assert artifacts.get("error_type") == "composer_timeout"
    reply_l = (result.get("reply") or "").lower()
    assert "timed out" in reply_l or "timeout" in reply_l
    released.set()


def test_contextual_question_preserves_facts_no_side_effects():
    from scripts.research_data_mcp.desk_direct_turns import try_direct_contextual_turn

    gateway = MagicMock()
    state = {
        "rail_context": {
            "tab": "browse",
            "mode": "detail",
            "dataset_id": "twse_mi_index",
            "readiness": "Query-ready",
            "vault_path": "",
            "entity": {"kind": "dataset", "id": "twse_mi_index", "title": "TWSE MI Index"},
            "actions": ["preview_rows", "ask_about"],
            "selected": {
                "source_id": "twse_official",
                "title": "TWSE MI Index",
                "dataset_id": "twse_mi_index",
            },
        }
    }
    turn = try_direct_contextual_turn(
        gateway,
        "What do we know about this selected object?",
        state,
    )
    assert turn is not None
    assert turn.action_result.get("action") == "contextual"
    assert turn.action_result.get("fast_path") is True
    assert turn.action_result.get("side_effects") is False
    reply = turn.reply
    assert "twse_mi_index" in reply
    assert "TWSE MI Index" in reply
    assert "Query-ready" in reply
    assert "unknown" in reply.lower()
    gateway.jobs.assert_not_called()
    gateway.collect_datacite_doi.assert_not_called()
    gateway.probe_source.assert_not_called()
    gateway.discover_refresh_create.assert_not_called()


def test_contextual_does_not_steal_collect_or_approve():
    from scripts.research_data_mcp.desk_direct_turns import try_direct_contextual_turn

    gateway = MagicMock()
    rail = {
        "entity": {"kind": "dataset", "id": "x", "title": "X"},
        "dataset_id": "x",
        "selected": {"source_id": "x", "dataset_id": "x"},
        "actions": ["ask_about"],
    }
    assert try_direct_contextual_turn(gateway, "Collect this source now", {"rail_context": rail}) is None
    assert try_direct_contextual_turn(gateway, "Approve job abcdef123456", {"rail_context": rail}) is None


def test_run_desk_agent_prefers_contextual_over_composer(monkeypatch):
    from scripts.research_data_mcp import desk_brain, desk_direct_turns

    importlib.reload(desk_direct_turns)
    importlib.reload(desk_brain)

    called = {"composer": 0}

    def _boom(*_a, **_k):
        called["composer"] += 1
        raise AssertionError("Composer must not run for read-only contextual asks")

    monkeypatch.setattr(desk_brain, "run_cursor_composer_turn", _boom)
    gateway = MagicMock()
    state = {
        "rail_context": {
            "dataset_id": "abc",
            "readiness": "metadata_only",
            "entity": {"kind": "dataset", "id": "abc", "title": "ABC Panel"},
            "actions": ["ask_about"],
        }
    }
    turn = desk_brain.run_desk_agent_turn(
        None,
        gateway,
        "Tell me about the selected dataset",
        state,
        session_id="s1",
    )
    assert turn is not None
    assert getattr(turn, "action_result", {}).get("action") == "contextual"
    assert getattr(turn, "action_result", {}).get("side_effects") is False
    assert called["composer"] == 0
