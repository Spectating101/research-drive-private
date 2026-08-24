"""Desk scale — cache, I/O pressure, status fast path."""

from __future__ import annotations

from unittest.mock import MagicMock

from scripts.research_data_mcp.desk_direct_turns import is_direct_status_message, try_direct_status_turn
from scripts.research_data_mcp.desk_scale import (
    get_search_cache,
    io_pressure_sample,
    scale_status,
    set_search_cache,
)


def test_search_cache_roundtrip():
    set_search_cache("unified", "mops", {"rows": [{"id": 1}], "total": 1}, limit=6, hf=1, dc=1, resolve=0)
    hit = get_search_cache("unified", "mops", limit=6, hf=1, dc=1, resolve=0)
    assert hit is not None
    assert hit.get("cache_hit") is True
    assert hit["total"] == 1


def test_scale_status_shape():
    out = scale_status()
    assert "composer_sla_seconds" in out
    assert "search_cache" in out
    assert "io" in out


def test_io_pressure_sample():
    sample = io_pressure_sample(refresh=True)
    assert sample.get("pressure") in {"ok", "high", "unknown"}


def test_status_fast_path():
    gw = MagicMock()
    gw.orchestrator.store.get.side_effect = KeyError("nope")
    state = {"composer_pending": True, "pending_job_id": "job-123"}
    turn = try_direct_status_turn(gw, "status", state)
    assert turn is not None
    assert turn.action_result.get("fast_path") is True
    assert "Composer is still finishing" in turn.reply


def test_status_intent():
    assert is_direct_status_message("status")
    assert not is_direct_status_message("search vault for mops")
