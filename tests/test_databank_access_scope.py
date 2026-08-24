"""Databank entitlement scope — accessible vs materialized."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def audit():
    from scripts.research_data_mcp.access_scope import build_access_coverage_audit

    return build_access_coverage_audit(REPO)


def test_access_scope_config_loads():
    path = REPO / "config/databank_access_scope.json"
    assert path.is_file()
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc.get("version") == 1
    assert len(doc.get("sources") or []) >= 10


def test_entitlement_matrix_covers_geographies(audit):
    matrix = audit.get("entitlement_matrix") or {}
    assert "US" in matrix
    assert "Asia_multi_13" in matrix
    assert matrix["US"].get("estimates_revisions") in ("full", "partial", "on_demand", "not_wired")


def test_crsp_moveit_licensed_not_ingested(audit):
    crsp = next(s for s in audit["sources"] if s["source_id"] == "crsp_moveit")
    assert crsp["subscription_status"] == "active"
    gaps = audit.get("source_level_gaps") or {}
    assert "crsp_moveit" in gaps


def test_materialized_matrix_merged(audit):
    assert audit["summary"]["materialized_matrix_loaded"] is True
    combined = audit.get("combined_matrix") or {}
    us_prices = combined.get("US", {}).get("daily_prices") or {}
    assert us_prices.get("accessible") is not None
    assert us_prices.get("materialized_score") is not None


def test_refinitiv_probe_attached_when_present(audit):
    probe = audit.get("refinitiv_entitlement_probe")
    if (REPO / "docs/status/generated/refinitiv_harvest_completion.json").is_file():
        assert probe is not None
        assert probe.get("summary")
