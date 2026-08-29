from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts.research_data_mcp import connected_accounts as accounts
from scripts.research_data_mcp import http_router
from scripts.research_data_mcp import research_seed as seed
from scripts.research_data_mcp import research_seed_http
from scripts.research_data_mcp.desk_auth import desk_principal_context
from scripts.research_data_mcp.desk_principal import DeskPrincipal


def principal(pid: str, *, email: str | None = None, role: str = "member") -> DeskPrincipal:
    return DeskPrincipal(
        principal_id=pid,
        email=email if email is not None else f"{pid}@student.yzu.edu.tw",
        display_name=pid.title(),
        role=role,
    )


def _account(*, account_id: str, access_mode: str = "read", verified: bool = True) -> dict:
    return {
        "id": account_id,
        "provider": "google_drive",
        "provider_account_id": f"upstream-{account_id}",
        "label": f"Drive {account_id}",
        "email": f"{account_id}@gmail.test",
        "access_mode": access_mode,
        "remote": f"rd_internal_secret_{account_id}",
        "status": "connected",
        "created_at": "2026-08-29T00:00:00+00:00",
        "updated_at": "2026-08-29T00:00:00+00:00",
        "verified_at": "2026-08-29T00:00:00+00:00" if verified else None,
    }


def test_no_connected_account_still_yields_yzu_cold_start(tmp_path):
    actor = principal("new-researcher", email="new.researcher@student.yzu.edu.tw")
    package = seed.build_research_seed(tmp_path, principal=actor)

    assert package["bootstrap_mode"] == "yzu_profile_fallback"
    assert package["research_context"]["profile_bound"] is True
    assert package["research_context"]["profile_unknown"] is True
    assert package["connected_sources"] == []
    assert package["starter_prompts"]
    assert package["policy"]["connected_storage_optional"] is True
    assert package["policy"]["seed_without_connected_storage"] is True


def test_non_yzu_member_still_gets_generic_seed_without_cloud(tmp_path):
    actor = principal("external", email="external@example.test")
    package = seed.build_research_seed(tmp_path, principal=actor)

    assert package["bootstrap_mode"] == "generic_cold_start"
    assert package["research_context"]["profile_bound"] is False
    assert package["starter_prompts"]
    assert package["connected_sources"] == []


def test_verified_connected_account_becomes_principal_scoped_seed_authority(tmp_path):
    alice = principal("alice")
    bob = principal("bob")
    accounts._save_accounts(tmp_path, alice, [_account(account_id="alice-drive", access_mode="index")])

    alice_package = seed.build_research_seed(tmp_path, principal=alice)
    bob_package = seed.build_research_seed(tmp_path, principal=bob)

    assert len(alice_package["connected_sources"]) == 1
    source = alice_package["connected_sources"][0]
    assert source["id"] == "alice-drive"
    assert source["capabilities"] == {"metadata_index": True, "read": False, "write": False}
    assert bob_package["connected_sources"] == []


def test_unverified_account_is_not_seed_usable(tmp_path):
    actor = principal("alice")
    accounts._save_accounts(tmp_path, actor, [_account(account_id="pending", verified=False)])

    package = seed.build_research_seed(tmp_path, principal=actor)
    assert package["connected_sources"] == []


def test_seed_never_exposes_internal_remote_or_provider_account_id(tmp_path):
    actor = principal("alice")
    accounts._save_accounts(tmp_path, actor, [_account(account_id="safe")])

    raw = json.dumps(seed.build_research_seed(tmp_path, principal=actor))
    assert "rd_internal_secret_safe" not in raw
    assert "upstream-safe" not in raw
    assert "remote" not in seed.connected_source_authorities(tmp_path, principal=actor)[0]
    assert "provider_account_id" not in seed.connected_source_authorities(tmp_path, principal=actor)[0]


def test_write_authority_maps_explicitly_and_does_not_materialize(tmp_path):
    actor = principal("alice")
    accounts._save_accounts(tmp_path, actor, [_account(account_id="write", access_mode="write")])

    package = seed.build_research_seed(tmp_path, principal=actor)
    assert package["connected_sources"][0]["capabilities"] == {
        "metadata_index": True,
        "read": True,
        "write": True,
    }
    assert package["policy"]["automatic_byte_copy"] is False
    assert package["policy"]["automatic_recursive_cloud_index"] is False
    assert package["policy"]["materialization_requires_explicit_operation"] is True


def test_public_identity_cannot_build_private_seed(tmp_path):
    guest = principal("public-user", role="public_member")
    with pytest.raises(PermissionError):
        seed.build_research_seed(tmp_path, principal=guest)


def test_rich_faculty_profile_and_connected_storage_are_additive(tmp_path, monkeypatch):
    actor = principal("professor", email="professor@yzu.edu.tw")
    accounts._save_accounts(tmp_path, actor, [_account(account_id="lab-drive")])
    profile = {
        "email": actor.email,
        "name_en": "Professor Example",
        "discipline": "Finance",
        "specialties": ["FinTech"],
        "research_tracks": [{"title": "Digital assets", "weight": 1.0}],
        "method_tags": ["panel data"],
        "starter_prompts": ["Find a panel for digital asset research"],
        "lab_fintech_stack": [],
        "recommended_datasets": [
            {
                "family": "custom_pipeline",
                "dataset": "Digital asset panel",
                "prompt": "Find a public digital asset panel",
                "priority": 4.8,
            }
        ],
    }
    monkeypatch.setattr(seed, "resolve_profile", lambda **kwargs: profile)

    package = seed.build_research_seed(tmp_path, principal=actor)
    assert package["bootstrap_mode"] == "faculty_profile"
    assert package["research_context"]["specialties"] == ["FinTech"]
    assert package["starter_prompts"] == ["Find a panel for digital asset research"]
    assert package["procurement_recommendations"][0]["dataset"] == "Digital asset panel"
    assert package["connected_sources"][0]["id"] == "lab-drive"


def test_router_exposes_seed_contract():
    routes = {(row["method"], row["path"]) for row in http_router.ROUTE_CATALOG}
    assert ("GET", "/library/seed") in routes


def test_http_seed_uses_bound_request_principal(tmp_path):
    alice = principal("alice", email="alice@student.yzu.edu.tw")
    accounts._save_accounts(tmp_path, alice, [_account(account_id="alice-drive", access_mode="index")])
    stack = SimpleNamespace(gateway=SimpleNamespace(repo_root=tmp_path))
    handler = research_seed_http.research_seed_handlers()["library_seed"]

    with desk_principal_context(alice):
        package = handler(stack, {"email": "bob@student.yzu.edu.tw"}, {}, {})

    assert package["principal"]["id"] == "alice"
    assert [source["id"] for source in package["connected_sources"]] == ["alice-drive"]


def test_http_seed_rejects_missing_request_principal(tmp_path):
    stack = SimpleNamespace(gateway=SimpleNamespace(repo_root=tmp_path))
    handler = research_seed_http.research_seed_handlers()["library_seed"]

    with desk_principal_context(None), pytest.raises(PermissionError):
        handler(stack, {}, {}, {})
