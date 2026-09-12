from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.research_data_mcp import desk_auth
from scripts.research_data_mcp.desk_principal import DeskPrincipal, permissions_document
from scripts.research_data_mcp.research_profile import (
    effective_profile_row,
    personal_profile,
    research_profile_document,
    update_personal_profile,
)
from scripts.research_data_mcp.research_seed import build_research_seed


def _principal(name: str, *, role: str = "public_member") -> DeskPrincipal:
    return DeskPrincipal(
        principal_id=f"cf-{name}-0123456789abcdef0123456789abcdef",
        email=f"{name}@example.edu",
        display_name=name.title(),
        role=role,
    )


def test_public_member_profile_starts_thin_and_is_principal_scoped(tmp_path):
    alice = _principal("alice")
    bob = _principal("bob")

    with desk_auth.desk_principal_context(alice):
        empty = research_profile_document(tmp_path)
        assert empty["configured"] is False
        assert empty["onboarding_required"] is True
        assert empty["principal"]["email"] == "alice@example.edu"
        saved = update_personal_profile(
            tmp_path,
            {
                "academic_stage": "Master's student",
                "discipline": "Finance",
                "research_topics": ["stablecoin trust", "market liquidity"],
                "methods": ["panel regression"],
                "current_project": "Stablecoin trust deterioration thesis",
            },
        )
        assert saved["configured"] is True
        assert saved["profile"]["discipline"] == "Finance"

    with desk_auth.desk_principal_context(bob):
        other = research_profile_document(tmp_path)
        assert other["configured"] is False
        assert other["profile"] == {}

    with desk_auth.desk_principal_context(alice):
        assert personal_profile(tmp_path)["current_project"] == "Stablecoin trust deterioration thesis"


def test_profile_payload_cannot_change_identity_or_role(tmp_path):
    alice = _principal("alice")
    with desk_auth.desk_principal_context(alice):
        for payload in (
            {"email": "attacker@example.edu"},
            {"role": "operator"},
            {"permissions": ["approve_jobs"]},
            {"principal_id": "someone-else"},
        ):
            with pytest.raises(ValueError, match="cannot change account identity"):
                update_personal_profile(tmp_path, payload)


def test_public_member_effective_profile_uses_user_confirmed_context(tmp_path):
    alice = _principal("alice")
    with desk_auth.desk_principal_context(alice):
        update_personal_profile(
            tmp_path,
            {
                "discipline": "Marketing",
                "research_topics": ["AI chatbot trust", "consumer behavior"],
                "methods": ["survey", "SEM"],
                "data_interests": ["consumer survey panels"],
                "current_project": "Master's thesis on AI chatbot trust",
            },
        )
        row = effective_profile_row(tmp_path)

    assert row["email"] == "alice@example.edu"
    assert row["name_en"] == "Alice"
    assert row["discipline"] == "Marketing"
    assert row["specialties"] == ["AI chatbot trust", "consumer behavior"]
    assert row["method_tags"] == ["survey", "SEM"]
    assert "consumer survey panels" in row["research_keywords"]
    assert row["unknown"] is False
    assert row["personal_profile"] is True


def test_public_member_seed_works_without_faculty_or_cloud_account(tmp_path):
    alice = _principal("alice")
    with desk_auth.desk_principal_context(alice):
        cold = build_research_seed(tmp_path)
        assert cold["bootstrap_mode"] == "generic_cold_start"
        assert cold["connected_sources"] == []
        assert cold["policy"]["collection_allowed"] is False

        update_personal_profile(
            tmp_path,
            {
                "discipline": "Finance",
                "research_topics": ["digital assets"],
                "current_project": "Master's thesis",
            },
        )
        seeded = build_research_seed(tmp_path)

    assert seeded["bootstrap_mode"] == "personal_profile"
    assert seeded["research_context"]["profile_unknown"] is False
    assert seeded["research_context"]["discipline"] == "Finance"
    assert seeded["connected_sources"] == []
    assert seeded["policy"]["collection_allowed"] is False


def test_profile_permission_is_separate_from_collection_authority(monkeypatch):
    public_member = _principal("alice")
    guest = DeskPrincipal(
        principal_id="guest-abcdefghijklmnopqrstuvwxyz",
        email="",
        display_name="Guest researcher",
        role="public_guest",
    )
    assert permissions_document(public_member)["manage_research_profile"] is True
    assert permissions_document(guest)["manage_research_profile"] is False
    assert "submit_collection" not in public_member.permissions

    monkeypatch.setattr(desk_auth, "desk_auth_configured", lambda: True)
    monkeypatch.setattr(desk_auth, "request_desk_principal", lambda _handler: public_member)
    handler = SimpleNamespace(headers={})
    assert desk_auth.authorize(handler, "/library/profile", "GET")[0] is True
    assert desk_auth.authorize(handler, "/library/profile", "POST")[0] is True
    allowed, message = desk_auth.authorize(handler, "/library/jobs", "POST")
    assert allowed is False and "submit_collection" in message

    monkeypatch.setattr(desk_auth, "request_desk_principal", lambda _handler: guest)
    allowed, message = desk_auth.authorize(handler, "/library/profile", "GET")
    assert allowed is False and "manage_research_profile" in message
