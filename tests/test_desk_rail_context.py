"""Desk rail context + API path normalization."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[1]


def test_normalize_api_path_strips_prefix():
    from scripts.research_query_engine.server import is_api_path, normalize_api_path

    assert normalize_api_path("/api/datasets") == "/datasets"
    assert normalize_api_path("/api/library/chat/stream") == "/library/chat/stream"
    assert normalize_api_path("/datasets") == "/datasets"
    assert is_api_path("/api/health") is True
    assert is_api_path("/api/datasets") is True


def test_format_rail_context_includes_entity():
    from scripts.research_data_mcp.desk_brain import _format_rail_context

    text = _format_rail_context(
        {
            "tab": "library",
            "dataset_id": "gdelt_asia_daily_country_panel",
            "entity": {"kind": "dataset", "id": "gdelt_asia_daily_country_panel", "title": "GDELT Asia"},
            "actions": ["preview_rows", "ask_about"],
        }
    )
    assert "[UI rail context]" in text
    assert "gdelt_asia_daily_country_panel" in text
    assert "dataset" in text


def test_chat_events_persists_rail_context():
    from scripts.research_data_mcp.procurement_chat import ProcurementChatOrchestrator

    orch = ProcurementChatOrchestrator(REPO)
    gateway = MagicMock()
    gateway.repo_root = REPO

    rail = {"tab": "browse", "dataset_id": "twse_daily", "entity": {"kind": "dataset", "id": "twse_daily"}}
    with patch.object(orch, "_run_agent_turn") as mock_turn:
        from scripts.research_data_mcp.desk_brain import AgentTurn

        mock_turn.return_value = AgentTurn(
            plan={"action": "composer"},
            action_result={"action": "composer"},
            reply="ok",
        )
        with patch("scripts.research_data_mcp.desk_brain.cursor_composer_available", return_value=False):
            events = list(
                orch.chat_events(
                    gateway,
                    "hello",
                    rail_context=rail,
                )
            )
    complete = [e for e in events if e.get("type") == "complete"]
    assert complete
    session_id = complete[0]["result"]["session_id"]
    stored = orch.sessions.get(session_id)
    assert stored["state"].get("rail_context") == rail


def test_synthesis_http_routes_registered():
    from scripts.research_data_mcp.http_router import ROUTE_CATALOG

    paths = {(r["method"], r["path"]) for r in ROUTE_CATALOG}
    assert ("GET", "/library/synthesis/profiles") in paths
    assert ("POST", "/library/synthesis/run") in paths
    assert ("POST", "/library/synthesis/pair") in paths
