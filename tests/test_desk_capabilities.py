#!/usr/bin/env python3
"""Capability families never claim a tool the runtime does not register."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drive"))

from scripts.research_data_mcp.desk_capabilities import (  # noqa: E402
    FAMILIES,
    available_families,
    capability_block,
    families_for_turn,
    registered_tool_names,
)


def test_every_declared_tool_is_actually_registered():
    registered = registered_tool_names(None)
    assert registered is not None and registered, "expected the live MCP tool registry to be importable"
    declared = {t for spec in FAMILIES.values() for t in spec["tools"]}
    missing = sorted(declared - registered)
    assert missing == [], f"capability map names unregistered tools: {missing}"


def test_unregistered_tools_are_dropped_not_advertised():
    class Gateway:
        def mcp_tool_names(self):
            return ["research_query_dataset"]

    families = available_families(Gateway(), only=["answer_from_held", "warehouse"])
    keys = {f["key"] for f in families}
    assert "answer_from_held" in keys
    assert "warehouse" not in keys
    answer = [f for f in families if f["key"] == "answer_from_held"][0]
    assert answer["tools"] == ["research_query_dataset"]


def test_held_question_turn_offers_querying_the_data():
    keys = families_for_turn(has_held=True, has_routes=False, is_question=True)
    assert keys[0] == "answer_from_held"
    assert "synthesis" in keys
    assert "catalog" not in keys


def test_empty_desk_turn_offers_external_reach():
    keys = families_for_turn(has_held=False, has_routes=True, is_question=False)
    assert "catalog" in keys
    assert "warehouse" in keys
    assert "answer_from_held" not in keys


def test_nothing_held_or_routed_still_offers_collect():
    # Previously "collect" only appeared when has_routes=True — exactly
    # backwards, since a fresh research_propose_pending_collect proposal is
    # most needed precisely when nothing is held AND nothing is routed.
    keys = families_for_turn(has_held=False, has_routes=False, is_question=False)
    assert "collect" in keys


def test_collect_family_names_the_pending_collect_tool_first():
    # capability_block() only renders the first 3 tool names per family, so
    # the tool actually worth calling has to lead, not just appear in the hint.
    assert FAMILIES["collect"]["tools"][:3][0] == "research_propose_pending_collect"


def test_block_is_bounded_and_names_tools():
    block = capability_block(None, has_held=True, has_routes=True, is_question=True)
    assert "research_query_dataset" in block
    assert len(block.splitlines()) <= 8


def test_block_is_empty_when_nothing_is_registered():
    class Gateway:
        def mcp_tool_names(self):
            return []

    assert capability_block(Gateway(), has_held=True) == ""
