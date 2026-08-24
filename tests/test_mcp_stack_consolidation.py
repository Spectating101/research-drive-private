"""MCP toolbox consolidation — tiers, discover routing, shared constants."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.research_data_mcp.procurement_constants import (
    DOWNLOADABLE_VIA,
    MCP_TOOL_ACQUIRE,
    MCP_TOOL_CORE,
    MCP_TOOL_OPS,
)
from scripts.research_data_mcp.tool_handlers import MCP_TOOL_NAMES, ResearchToolHandlers


def test_downloadable_via_unified() -> None:
    assert "spectator" in DOWNLOADABLE_VIA
    assert "datacite" in DOWNLOADABLE_VIA
    assert "http_manifest" in DOWNLOADABLE_VIA


def test_mcp_tool_tiers_cover_all_registered_tools() -> None:
    tiered = set(MCP_TOOL_CORE) | set(MCP_TOOL_ACQUIRE) | set(MCP_TOOL_OPS)
    assert set(MCP_TOOL_NAMES) == tiered


def test_unified_search_merges_discover_profile_when_email_set() -> None:
    gw = MagicMock()
    gw.unified_search_with_profile.return_value = {
        "sections": [{"id": "datacite_vault", "rows": [{"title": "x"}]}],
        "total": 1,
        "routed_via": "unified_dataset_search+discover_profile",
    }
    handlers = ResearchToolHandlers(MagicMock(gateway=gw))
    out = handlers.research_unified_search("USDT flows", email="drkong@saturn.yzu.edu.tw")
    gw.unified_search_with_profile.assert_called_once()
    assert out.get("routed_via") == "unified_dataset_search+discover_profile"
    gw.discover_search.assert_not_called()


def test_procure_chat_passes_user_email() -> None:
    gw = MagicMock()
    gw.procurement_chat.return_value = {"ok": True}
    handlers = ResearchToolHandlers(MagicMock(gateway=gw))
    handlers.research_procure_chat("hello", user_email="drkong@saturn.yzu.edu.tw")
    gw.procurement_chat.assert_called_once_with(
        "hello",
        session_id=None,
        user_email="drkong@saturn.yzu.edu.tw",
    )


def test_tool_catalog_has_tiers() -> None:
    handlers = ResearchToolHandlers(MagicMock())
    cat = handlers.tool_catalog()
    assert "tiers" in cat
    assert "research_discover_search" in cat["tiers"]["core"]
    assert "research_platform_consolidated" in cat["tiers"]["core"]
    assert cat.get("start_here") == "research_platform_consolidated"


def test_platform_consolidated_tool() -> None:
    gw = MagicMock()
    gw.consolidated_state.return_value = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "live": False,
        "headline": {"instant_query_ready": 29, "instant_datasets": 47, "gap_cells": 8},
        "entitlement_summary": {"gap_cells": 8},
        "priority_access_gaps": [{"source_id": "crsp_moveit", "gap": "not_wired"}],
        "instant_probe": {},
        "sourcing_capability": [{"mode": "licensed_bulk", "status": "partial"}],
    }
    handlers = ResearchToolHandlers(MagicMock(gateway=gw))
    out = handlers.research_platform_consolidated(live=False)
    assert out.get("instant_query_ready") == 29
    assert out.get("gap_cells") == 8
    assert out.get("priority_access_gaps")


def test_composer_can_propose_discover_routes_but_not_approve_collection() -> None:
    gateway = MagicMock()
    gateway.discover_intent_create.return_value = {"id": "intent-1"}
    handlers = ResearchToolHandlers(MagicMock(gateway=gateway))

    out = handlers.research_discover_create_intent("Historical stablecoin activity")
    assert out["id"] == "intent-1"
    gateway.discover_intent_create.assert_called_once()

    with pytest.raises(PermissionError, match="researcher confirmation"):
        handlers.yzu_approve_job("job-1")
    with pytest.raises(PermissionError, match="researcher confirmation"):
        handlers.procurement_approve_job("job-1")
