#!/usr/bin/env python3
"""Bounded Discover agent reuse — amortizes cold start, never pools forever."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "kernel"), str(ROOT / "drive")]

from scripts.research_data_mcp import discover_composer as dc  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_pool():
    dc.reset_discover_agent_pool()
    yield
    dc.reset_discover_agent_pool()


def test_empty_pool_has_nothing_to_reuse():
    assert dc._pooled_discover_agent_id() == ""


def test_remembered_agent_is_returned_on_the_next_call():
    dc._remember_discover_agent("agent-abc123")
    assert dc._pooled_discover_agent_id() == "agent-abc123"


def test_blank_agent_id_is_not_remembered():
    dc._remember_discover_agent("")
    assert dc._pooled_discover_agent_id() == ""


def test_pool_expires_after_the_use_cap(monkeypatch):
    monkeypatch.setattr(dc, "_AGENT_MAX_USES", 2)
    dc._remember_discover_agent("agent-1")
    assert dc._pooled_discover_agent_id() == "agent-1"
    dc._remember_discover_agent("agent-1")
    # third read is past the cap
    assert dc._pooled_discover_agent_id() == ""


def test_pool_expires_after_ttl(monkeypatch):
    monkeypatch.setattr(dc, "_AGENT_TTL_S", 0.05)
    dc._remember_discover_agent("agent-1")
    assert dc._pooled_discover_agent_id() == "agent-1"
    time.sleep(0.08)
    assert dc._pooled_discover_agent_id() == ""


def test_a_new_agent_id_resets_the_use_counter():
    dc._remember_discover_agent("agent-1")
    dc._remember_discover_agent("agent-1")
    assert dc._AGENT_POOL["uses"] == 2
    dc._remember_discover_agent("agent-2")
    assert dc._AGENT_POOL["uses"] == 1
    assert dc._AGENT_POOL["id"] == "agent-2"


def test_reset_clears_everything():
    dc._remember_discover_agent("agent-1")
    dc.reset_discover_agent_pool()
    assert dc._pooled_discover_agent_id() == ""
    assert dc._AGENT_POOL == {"id": "", "created": 0.0, "uses": 0}
