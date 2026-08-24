"""Consolidated desk state API."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def gateway():
    from scripts.research_data_mcp.bootstrap import create_stack

    return create_stack(repo_root=REPO).gateway


def test_consolidated_state_has_headline(gateway):
    state = gateway.consolidated_state(live=False)
    headline = state.get("headline") or {}
    assert headline.get("registry_datasets")
    assert "instant_query_ready" in headline
    assert state.get("sourcing_capability")


def test_consolidated_live_build(gateway):
    state = gateway.consolidated_state(live=True)
    assert state.get("live") is True
    assert state.get("instant_probe", {}).get("instant_total") is not None


def test_consolidated_http_route_registered():
    from scripts.research_data_mcp.http_router import ROUTE_CATALOG

    paths = {r["path"] for r in ROUTE_CATALOG}
    assert "/library/consolidated" in paths
