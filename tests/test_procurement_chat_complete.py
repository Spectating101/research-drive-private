"""Procurement chat complete payload — job id and state merge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.research_data_mcp.desk_brain import AgentTurn
from scripts.research_data_mcp.procurement_chat import ProcurementChatOrchestrator


def test_chat_complete_includes_job_id_from_direct_collect(tmp_path):
    orch = ProcurementChatOrchestrator(tmp_path)
    gateway = MagicMock()
    gateway.repo_root = tmp_path

    turn = AgentTurn(
        plan={"action": "submit_collect"},
        action_result={
            "action": "submit_collect",
            "fast_path": True,
            "job_id": "job-abc-123",
            "job": {"id": "job-abc-123", "status": "pending_approval"},
            "search": {"rows": [{"title": "MOPS", "kind": "local_registry"}]},
        },
        reply="Queued for cluster",
        suggested_prompts=[],
        tool_name="datacite_collect_doi",
    )

    with patch.object(orch, "_run_agent_turn", return_value=turn):
        with patch("scripts.research_data_mcp.desk_brain.cursor_composer_available", return_value=False):
            events = list(
                orch.chat_events(
                    gateway,
                    "collect 10.5281/zenodo.1",
                    session_id="sess-test",
                )
            )

    complete = [e for e in events if e.get("type") == "complete"]
    assert complete, events
    result = complete[0]["result"]
    assert result.get("job_id") == "job-abc-123"
    assert result.get("pending_job_id") == "job-abc-123"
    assert result.get("job_status") == "pending_approval"
    assert result["artifacts"]["search"]["rows"][0]["title"] == "MOPS"
