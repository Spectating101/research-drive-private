"""Desk direct-turn fast paths (probe/search without Composer)."""

from __future__ import annotations

from unittest.mock import MagicMock

from scripts.research_data_mcp.desk_direct_turns import (
    doi_from_message,
    probe_url_from_message,
    search_query_from_message,
    try_direct_collect_turn,
    try_submit_collect_turn,
    try_direct_describe_turn,
    try_direct_probe_turn,
    try_direct_query_turn,
    try_direct_search_turn,
)


def test_probe_url_from_message_keyword():
    assert probe_url_from_message("Probe https://example.com please") == "https://example.com"


def test_probe_url_from_message_rail_action():
    assert (
        probe_url_from_message(
            "https://www.sec.gov/files/company_tickers.json",
            {"actions": ["probe"]},
        )
        == "https://www.sec.gov/files/company_tickers.json"
    )


def test_probe_url_ignored_without_intent():
    assert probe_url_from_message("Compare https://example.com with vault holdings") is None


def test_try_direct_probe_turn_uses_gateway():
    gateway = MagicMock()
    gateway.probe_source.return_value = {
        "summary": "JSON bulk download",
        "connector": {
            "spec": {
                "access_mode": "direct_download",
                "content_type": "application/json",
                "discovered_file_count": 1,
            }
        },
    }
    turn = try_direct_probe_turn(gateway, "Probe https://example.com", {})
    assert turn is not None
    assert turn.action_result.get("fast_path") is True
    gateway.probe_source.assert_called_once()
    assert turn.reply == "JSON bulk download"


def test_unified_search_skip_discover_flag():
    from scripts.research_data_mcp.gateway import ResearchDataGateway

    gw = ResearchDataGateway.__new__(ResearchDataGateway)
    gw.discover_search = MagicMock(return_value={"sections": [{"rows": [{"id": "d1"}]}]})
    gw.unified_dataset_search = MagicMock(
        return_value={"sections": [{"rows": [{"id": "u1"}]}], "rows": [{"id": "u1"}], "total": 1}
    )
    out = gw.unified_search_with_profile("mops", email="demo@yzu.edu.tw", skip_discover=True)
    gw.discover_search.assert_not_called()
    assert out.get("discover_skipped") is True


def test_search_query_from_message_vault_for():
    assert search_query_from_message("Search vault for mops governance panel") == "mops governance panel"


def test_search_query_ignored_for_planning():
    assert search_query_from_message("Explain how we should collect mops data") is None


def test_try_direct_search_turn():
    gateway = MagicMock()
    gateway.unified_dataset_search.return_value = {
        "rows": [{"title": "MOPS panel", "kind": "local_registry"}],
        "total": 1,
    }
    turn = try_direct_search_turn(gateway, "search for mops governance", {})
    assert turn is not None
    assert turn.action_result.get("fast_path") is True
    gateway.unified_dataset_search.assert_called_once_with("mops governance", limit=12)


def test_doi_from_collect_message():
    assert doi_from_message("Collect 10.5281/zenodo.12345 into the lab") == "10.5281/zenodo.12345"
    assert doi_from_message("Explain how to collect 10.5281/zenodo.12345") is None


def test_try_direct_describe_turn():
    gateway = MagicMock()
    gateway.describe_dataset.return_value = {
        "title": "MOPS panel",
        "readiness": "instant",
        "summary": "TWSE filings",
    }
    turn = try_direct_describe_turn(gateway, "describe dataset mops_governance_panel", {})
    assert turn is not None
    assert turn.action_result.get("fast_path") is True
    assert "MOPS panel" in turn.reply


def test_try_direct_query_turn():
    gateway = MagicMock()
    gateway.query_dataset.return_value = {"rows": [{"symbol": "2330"}], "columns": ["symbol"]}
    turn = try_direct_query_turn(gateway, "query dataset mops_governance_panel limit 5", {})
    assert turn is not None
    gateway.query_dataset.assert_called_once_with("mops_governance_panel", {"limit": 5})


def test_try_submit_collect_turn_blocked():
    gateway = MagicMock()
    gateway.collect_datacite_doi.return_value = {
        "blocked": True,
        "message": "license approval required",
        "gate": {"blocked_reason": "license approval required"},
    }
    turn = try_submit_collect_turn(gateway, "collect 10.5281/zenodo.99", {})
    assert turn is not None
    assert turn.action_result.get("procurement_submit") is True
    assert turn.action_result.get("action") == "submit_collect"
    assert "approval" in turn.reply.lower()
    assert "cluster" in turn.reply.lower() or "queue" in turn.reply.lower()


def test_try_submit_collect_turn_job_id_from_id_field():
    gateway = MagicMock()
    gateway.collect_datacite_doi.return_value = {
        "job": {"id": "jid-99", "status": "pending_approval"},
        "resolved": {"title": "Zenodo set"},
    }
    state: dict = {}
    turn = try_submit_collect_turn(gateway, "collect 10.5281/zenodo.99", state)
    assert turn is not None
    assert turn.action_result.get("job_id") == "jid-99"
    assert state.get("pending_job_id") == "jid-99"
    assert state.get("job_status") == "pending_approval"
