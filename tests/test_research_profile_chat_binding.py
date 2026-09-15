from __future__ import annotations

import threading
from types import SimpleNamespace

from scripts.research_data_mcp import desk_auth
from scripts.research_data_mcp import desk_brain
from scripts.research_data_mcp.desk_brain import AgentTurn
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


def test_authenticated_principal_reaches_threaded_chat_worker(tmp_path, monkeypatch):
    alice = _researcher()
    orchestrator = ProcurementChatOrchestrator(tmp_path)
    observed = []

    monkeypatch.setattr(desk_brain, "desk_brain_mode", lambda _root=None: "unavailable")

    def fake_run(_gateway, _message, _state, _sid, *, event_sink=None):
        del event_sink
        observed.append(desk_auth.current_desk_principal())
        return AgentTurn(
            plan={"action": "composer"},
            action_result={"action": "composer"},
            reply="Principal observed.",
        )

    monkeypatch.setattr(orchestrator, "_run_agent_turn", fake_run)
    gateway = SimpleNamespace(repo_root=tmp_path)

    with desk_auth.desk_principal_context(alice):
        result = orchestrator.chat(gateway, "Check my signed-in context")

    assert result["reply"] == "Principal observed."
    assert observed == [alice]


def test_authenticated_principal_reaches_background_warm_worker(tmp_path, monkeypatch):
    from scripts.research_data_mcp import desk_warm

    alice = _researcher()
    orchestrator = ProcurementChatOrchestrator(tmp_path)
    session = orchestrator.sessions.get_or_create(None)
    orchestrator.sessions.update_state(
        session["id"],
        {"vault_brief": "Verified Library brief."},
    )
    observed = []
    completed = threading.Event()

    monkeypatch.setattr(desk_brain, "desk_brain_mode", lambda _root=None: "copilot_composer")
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_vault_brief.build_vault_brief",
        lambda _root, _profile=None: "Verified Library brief.",
    )

    def fake_prime(_gateway, state, _session_id):
        observed.append(desk_auth.current_desk_principal())
        state["desk_primed"] = True
        completed.set()
        return True

    monkeypatch.setattr(desk_warm, "prime_desk_agent", fake_prime)
    gateway = SimpleNamespace(
        repo_root=tmp_path,
        _procurement_chat_orchestrator=lambda: orchestrator,
    )

    with desk_auth.desk_principal_context(alice):
        result = desk_warm.warm_desk_session(
            gateway,
            session_id=session["id"],
            background=True,
        )

    assert result["priming"] is True
    assert completed.wait(timeout=2)
    assert observed == [alice]
