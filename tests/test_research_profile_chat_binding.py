from __future__ import annotations

from scripts.research_data_mcp import desk_auth
from scripts.research_data_mcp.desk_principal import DeskPrincipal
from scripts.research_data_mcp.procurement_chat import ProcurementChatOrchestrator
from scripts.research_data_mcp.research_profile import update_personal_profile


def _researcher() -> DeskPrincipal:
    return DeskPrincipal(
        principal_id="cf-alice-0123456789abcdef0123456789abcdef",
        email="alice@example.edu",
        display_name="Alice",
        role="public_member",
    )


def test_instance_binder_overlays_personal_context_without_fake_professor(tmp_path):
    alice = _researcher()
    with desk_auth.desk_principal_context(alice):
        update_personal_profile(
            tmp_path,
            {
                "discipline": "Finance",
                "research_topics": ["stablecoin trust"],
                "methods": ["panel regression"],
            },
        )
        orch = ProcurementChatOrchestrator(tmp_path)
        state = {}
        orch._bind_faculty_profile(state, "ignored@example.edu")

    assert state["user_email"] == "alice@example.edu"
    assert state["research_profile"]["discipline"] == "Finance"
    assert state["faculty_profile_row"]["title"] == "Researcher"
    assert "Professor" not in str(state["faculty_profile"].get("title") or "")


def test_class_call_compatibility_used_by_desk_warm_still_works():
    state = {}
    # Historical warmup API: no orchestrator instance is supplied.
    ProcurementChatOrchestrator._bind_faculty_profile(state, "someone@example.edu")
    assert state["user_email"] == "someone@example.edu"
    assert "faculty_profile" in state
