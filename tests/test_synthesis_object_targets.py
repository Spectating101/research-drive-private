from __future__ import annotations


def _rail(**overrides):
    rail = {
        "tab": "synthesis",
        "entity": {"kind": "synthesis_thread", "id": "thread-a"},
        "selected": {
            "thread_id": "thread-a",
            "decision_kind": "review_proposal",
            "proposal_id": "proposal-durable",
            "accepted_spec_hash": "spec-accepted",
            "preview_spec_hash": "spec-preview",
            "job_id": "job-durable",
            "output_dataset_id": "output-durable",
        },
    }
    rail.update(overrides)
    return rail


def test_typed_proposal_result_targets_recorded_proposal_id():
    from scripts.research_data_mcp.synthesis_object_targets import synthesis_target

    target = synthesis_target(
        _rail(),
        {
            "action": "synthesis_proposal_recorded_response_error",
            "artifacts": {
                "proposal_recorded": True,
                "synthesis_proposal": {"id": "proposal-new"},
            },
        },
    )

    assert target == {
        "kind": "proposal",
        "object_id": "proposal-new",
        "label": "Method proposal",
        "thread_id": "thread-a",
        "surface": "synthesis-proposal-state",
    }


def test_selected_object_context_drives_contextual_turn_without_text_inference():
    from scripts.research_data_mcp.synthesis_object_targets import synthesis_target

    rail = _rail(
        synthesis_object_context={
            "kind": "join",
            "object_id": "thread-a:join",
            "label": "Join decision",
            "surface": "synthesis-join-decision",
        }
    )
    target = synthesis_target(rail, {"action": "contextual", "text": "Checking current recorded state"})

    assert target["kind"] == "join"
    assert target["object_id"] == "thread-a:join"
    assert target["surface"] == "synthesis-join-decision"


def test_execution_job_identity_overrides_stale_thread_job():
    from scripts.research_data_mcp.synthesis_object_targets import synthesis_target

    target = synthesis_target(
        _rail(),
        {
            "action": "queue",
            "job": {
                "id": "job-new",
                "plan": {"job_type": "synthesis_execute"},
            },
        },
    )

    assert target["kind"] == "execution"
    assert target["object_id"] == "job-new"


def test_chat_adapter_replays_targeted_receipts_for_buffered_endpoint(monkeypatch):
    from scripts.research_data_mcp.procurement_chat import ProcurementChatOrchestrator
    from scripts.research_data_mcp.procurement_chat_core import (
        ProcurementChatOrchestrator as CoreProcurementChatOrchestrator,
    )

    def fake_events(self, gateway, message, **kwargs):
        yield {
            "type": "activity",
            "action": "proposal",
            "text": "Checking current recorded state",
        }
        yield {
            "type": "complete",
            "result": {
                "session_id": "session-a",
                "reply": "Proposal recorded.",
                "action": "synthesis_proposal_recorded",
                "artifacts": {"synthesis_proposal": {"id": "proposal-new"}},
            },
        }

    monkeypatch.setattr(CoreProcurementChatOrchestrator, "chat_events", fake_events)
    orchestrator = object.__new__(ProcurementChatOrchestrator)
    events = list(
        orchestrator.chat_events(
            object(),
            "record the proposal",
            rail_context=_rail(),
        )
    )

    activity = events[0]
    complete = events[-1]["result"]
    assert activity["target"]["kind"] == "proposal"
    assert activity["target"]["object_id"] == "proposal-durable"
    assert complete["activity_target"]["object_id"] == "proposal-new"
    assert complete["activity_events"][0]["target"]["object_id"] == "proposal-durable"

    # POST /library/chat consumes the same adapter and keeps the receipts even
    # when the proxy buffers/does not expose the NDJSON stream.
    result = orchestrator.chat(
        object(),
        "record the proposal",
        rail_context=_rail(),
    )
    assert result["activity_target"]["object_id"] == "proposal-new"
    assert result["activity_events"][0]["target"]["kind"] == "proposal"
