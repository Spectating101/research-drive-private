from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.research_data_mcp import desk_auth
from scripts.research_data_mcp.desk_principal import DeskPrincipal
from scripts.research_data_mcp.http_router import handle_get, handle_post
from scripts.research_data_mcp.research_profile import (
    effective_profile_row,
    research_profile_document,
)
from scripts.research_data_mcp.research_profile_memory import (
    active_research_memories,
    clear_research_memories,
    forget_research_memory,
    remember_research_context,
    research_memory_document,
    update_research_memory_settings,
)
from scripts.research_data_mcp.research_seed import build_research_seed
from scripts.research_data_mcp.mcp_instructions import mcp_server_instructions
from scripts.research_data_mcp.tool_handlers import ResearchToolHandlers


def _principal(name: str, *, role: str = "public_member") -> DeskPrincipal:
    return DeskPrincipal(
        principal_id=f"cf-{name}-0123456789abcdef0123456789abcdef",
        email=f"{name}@example.edu",
        display_name=name.title(),
        role=role,
    )


def _stack(tmp_path):
    return SimpleNamespace(gateway=SimpleNamespace(repo_root=tmp_path))


def test_memory_is_learned_automatically_but_kept_separate_from_declared_profile(tmp_path):
    alice = _principal("alice")
    with desk_auth.desk_principal_context(alice):
        result = remember_research_context(
            tmp_path,
            kind="topic",
            value="wildfire economics",
            evidence="The researcher described this as their thesis topic.",
        )
        profile = research_profile_document(tmp_path)
        effective = effective_profile_row(tmp_path)

    assert result["remembered"] is True
    assert profile["profile"] == {}
    assert profile["configured"] is False
    assert profile["memory"]["stored_count"] == 1
    assert profile["memory"]["authority"]["separate_from_declared_profile"] is True
    assert effective["specialties"] == ["wildfire economics"]
    assert effective["learned_memories"][0]["kind"] == "topic"


def test_memory_is_principal_scoped_and_repeat_evidence_is_upserted(tmp_path):
    alice = _principal("alice")
    bob = _principal("bob")
    with desk_auth.desk_principal_context(alice):
        first = remember_research_context(tmp_path, kind="method", value="Panel regression")
        second = remember_research_context(
            tmp_path,
            kind="method",
            value="panel regression",
            evidence="Repeated in a later Ask turn",
        )
        alice_memory = research_memory_document(tmp_path)
    with desk_auth.desk_principal_context(bob):
        bob_memory = research_memory_document(tmp_path)

    assert first["memory"]["id"] == second["memory"]["id"]
    assert alice_memory["stored_count"] == 1
    assert alice_memory["memories"][0]["evidence_count"] == 2
    assert bob_memory["stored_count"] == 0


def test_memory_controls_disable_learning_and_use_without_deleting(tmp_path):
    alice = _principal("alice")
    with desk_auth.desk_principal_context(alice):
        remembered = remember_research_context(
            tmp_path,
            kind="data_interest",
            value="county employment panels",
        )
        update_research_memory_settings(tmp_path, auto_learn=False, use_memory=False)
        refused = remember_research_context(tmp_path, kind="topic", value="labor economics")
        document = research_memory_document(tmp_path)
        active = active_research_memories(tmp_path)

    assert remembered["remembered"] is True
    assert refused["remembered"] is False
    assert refused["reason"] == "auto_learn_disabled"
    assert document["stored_count"] == 1
    assert document["active_count"] == 0
    assert active == []


def test_memory_can_be_forgotten_individually_or_cleared(tmp_path):
    alice = _principal("alice")
    with desk_auth.desk_principal_context(alice):
        one = remember_research_context(tmp_path, kind="topic", value="market liquidity")
        remember_research_context(tmp_path, kind="method", value="event study")
        removed = forget_research_memory(tmp_path, one["memory"]["id"])
        assert removed["removed"] is True
        assert removed["memory_document"]["stored_count"] == 1
        cleared = clear_research_memories(tmp_path)
    assert cleared["stored_count"] == 0


def test_memory_rejects_secrets_and_project_scope_without_identity(tmp_path):
    alice = _principal("alice")
    with desk_auth.desk_principal_context(alice):
        with pytest.raises(ValueError, match="credentials and secrets"):
            remember_research_context(tmp_path, kind="preference", value="api_key=secret-value")
        with pytest.raises(ValueError, match="memory evidence"):
            remember_research_context(
                tmp_path,
                kind="topic",
                value="wildfire economics",
                evidence="access_token=ghp_not-a-real-secret-but-never-store-this",
            )
        with pytest.raises(ValueError, match="requires project_id"):
            remember_research_context(
                tmp_path,
                kind="research_goal",
                value="Estimate wildfire employment effects",
                scope="project",
            )


def test_memory_http_route_and_auth_boundary(tmp_path, monkeypatch):
    alice = _principal("alice")
    stack = _stack(tmp_path)
    with desk_auth.desk_principal_context(alice):
        settings = handle_post(
            "/library/profile/memory",
            {"action": "settings", "auto_learn": False},
            stack,
        )
        reread = handle_get("/library/profile/memory", {}, stack)
    assert settings["status"] == 200
    assert reread["body"]["settings"]["auto_learn"] is False

    monkeypatch.setattr(desk_auth, "desk_auth_configured", lambda: True)
    monkeypatch.setattr(
        desk_auth,
        "request_desk_principal",
        lambda _handler: DeskPrincipal(
            principal_id="guest-abcdefghijklmnopqrstuvwxyz",
            email="",
            display_name="Guest",
            role="public_guest",
        ),
    )
    allowed, message = desk_auth.authorize(
        SimpleNamespace(headers={}), "/library/profile/memory", "GET"
    )
    assert allowed is False
    assert "manage_research_profile" in message


def test_memory_mcp_tool_uses_server_bound_principal_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_MCP_PRINCIPAL_ID", "cf-mcp-0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("RESEARCH_MCP_PRINCIPAL_ROLE", "public_member")
    tools = ResearchToolHandlers(_stack(tmp_path))
    result = tools.research_profile_remember(
        "research_goal",
        "Build a defensible wildfire economics panel",
        evidence="Explicit long-term project statement",
    )
    assert result["remembered"] is True
    assert tools.research_profile_memory()["stored_count"] == 1


def test_learned_memory_enriches_seed_without_claiming_user_authorship(tmp_path):
    alice = _principal("alice")
    with desk_auth.desk_principal_context(alice):
        remember_research_context(tmp_path, kind="topic", value="wildfire economics")
        seed = build_research_seed(tmp_path)
    assert seed["bootstrap_mode"] == "personal_profile"
    assert seed["policy"]["profile_source"] == "learned_memory"
    assert seed["source_summary"]["learned_memories"] == 1


def test_desk_instructions_make_learning_selective_and_visible(monkeypatch):
    monkeypatch.setenv("RESEARCH_MCP_DESK", "1")
    instructions = mcp_server_instructions()
    assert "automatically call research_profile_remember" in instructions
    assert "Do not remember one-off requests" in instructions
    assert "say so briefly in the reply" in instructions
