"""Cross-surface contract for explicit Synthesis Preview and approval intent."""

from __future__ import annotations


class _Gateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def synthesis_thread_submit_execution(self, thread_id: str, action: str = "request_approval"):
        self.calls.append((thread_id, action))
        if action == "preview":
            return {
                "preview_only": True,
                "execution_submitted": False,
                "preview": {"status": "succeeded"},
            }
        return {
            "preview_only": False,
            "execution_submitted": True,
            "job": {"id": "job-1", "status": "pending_approval"},
        }


def _handler():
    from scripts.research_data_mcp.tool_handlers import ResearchToolHandlers

    handler = ResearchToolHandlers.__new__(ResearchToolHandlers)
    handler.gateway = _Gateway()
    return handler


def test_mcp_preview_intent_cannot_masquerade_as_submission():
    handler = _handler()

    out = handler.research_synthesis_submit_execution("thread-1", action="preview")

    assert handler.gateway.calls == [("thread-1", "preview")]
    assert out["preview_only"] is True
    assert out["execution_submitted"] is False
    assert out["job_id"] is None
    assert out["job_status"] is None
    assert "no execution job was created" in out["note"]
    assert out["agent_may_approve_synthesis"] is False


def test_mcp_approval_intent_remains_manual_and_distinct():
    handler = _handler()

    out = handler.research_synthesis_submit_execution("thread-1", action="request_approval")

    assert handler.gateway.calls == [("thread-1", "request_approval")]
    assert out["preview_only"] is False
    assert out["execution_submitted"] is True
    assert out["job_id"] == "job-1"
    assert out["job_status"] == "pending_approval"
    assert "researcher desk approval" in out["note"]
    assert out["agent_may_approve_synthesis"] is False
