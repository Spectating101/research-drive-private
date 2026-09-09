from __future__ import annotations

import json
import time
import urllib.parse

import pytest

from scripts.research_data_mcp import connected_accounts as accounts
from scripts.research_data_mcp.desk_auth import desk_principal_context
from scripts.research_data_mcp.desk_principal import DeskPrincipal
from scripts.research_data_mcp import http_router


def principal(pid: str, role: str = "member") -> DeskPrincipal:
    return DeskPrincipal(
        principal_id=pid,
        email=f"{pid}@example.test",
        display_name=pid,
        role=role,
    )


@pytest.fixture(autouse=True)
def oauth_env(monkeypatch):
    monkeypatch.setenv("YZU_CONNECTED_ACCOUNTS_PUBLIC_BASE_URL", "https://desk.example.test")
    monkeypatch.setenv("YZU_GOOGLE_DRIVE_CLIENT_ID", "google-client")
    monkeypatch.setenv("YZU_GOOGLE_DRIVE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("YZU_DROPBOX_CLIENT_ID", "dropbox-client")
    monkeypatch.setenv("YZU_DROPBOX_CLIENT_SECRET", "dropbox-secret")
    monkeypatch.setenv("YZU_ONEDRIVE_CLIENT_ID", "onedrive-client")
    monkeypatch.setenv("YZU_ONEDRIVE_CLIENT_SECRET", "onedrive-secret")
    monkeypatch.setattr(accounts, "rclone_ready", lambda: True)


def state_from(started: dict) -> str:
    return urllib.parse.parse_qs(urllib.parse.urlparse(started["authorize_url"]).query)["state"][0]


def test_provider_catalog_is_capability_only():
    payload = json.dumps(accounts.provider_catalog())
    assert "google-secret" not in payload
    assert "dropbox-secret" not in payload
    assert "onedrive-secret" not in payload
    rows = {row["id"]: row for row in accounts.provider_catalog()}
    assert rows["google_drive"]["supports_index_only"] is True
    assert rows["dropbox"]["supports_index_only"] is True
    assert rows["onedrive"]["supports_index_only"] is False


def test_public_identity_cannot_bind_storage(tmp_path):
    with desk_principal_context(principal("public-user", role="public_member")):
        with pytest.raises(PermissionError):
            accounts.connected_accounts_document(tmp_path)


def test_oauth_state_is_bound_to_principal(tmp_path):
    alice = principal("alice")
    bob = principal("bob")
    with desk_principal_context(alice):
        started = accounts.start_oauth(tmp_path, provider="google_drive", access_mode="read")
    with desk_principal_context(bob):
        with pytest.raises(ValueError, match="invalid or expired"):
            accounts.complete_oauth(
                tmp_path,
                provider="google_drive",
                state=state_from(started),
                code="provider-code",
            )


def test_expired_oauth_state_is_rejected(tmp_path):
    actor = principal("alice")
    with desk_principal_context(actor):
        started = accounts.start_oauth(tmp_path, provider="dropbox", access_mode="index")
        pending_path = accounts._pending_path(tmp_path, actor)
        payload = json.loads(pending_path.read_text(encoding="utf-8"))
        row = next(iter(payload["pending"].values()))
        row["expires_at"] = int(time.time()) - 1
        pending_path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="invalid or expired|expired"):
            accounts.complete_oauth(
                tmp_path,
                provider="dropbox",
                state=state_from(started),
                code="provider-code",
            )


def test_complete_oauth_persists_metadata_not_tokens(tmp_path, monkeypatch):
    actor = principal("alice")
    monkeypatch.setattr(
        accounts,
        "_exchange_code",
        lambda provider, code, pending: {
            "access_token": "TOP-SECRET-ACCESS",
            "refresh_token": "TOP-SECRET-REFRESH",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
    )
    monkeypatch.setattr(
        accounts,
        "_provider_identity",
        lambda provider, token: {
            "provider_account_id": "google-123",
            "email": "alice@gmail.test",
            "display_name": "Alice personal",
        },
    )
    monkeypatch.setattr(
        accounts,
        "_create_rclone_remote",
        lambda repo_root, principal, **kwargs: "rd_alice_google",
    )

    with desk_principal_context(actor):
        started = accounts.start_oauth(tmp_path, provider="google_drive", access_mode="read")
        row = accounts.complete_oauth(
            tmp_path,
            provider="google_drive",
            state=state_from(started),
            code="provider-code",
        )
        doc = accounts.connected_accounts_document(tmp_path)

    assert row["provider"] == "google_drive"
    assert doc["accounts"][0]["email"] == "alice@gmail.test"
    raw_registry = accounts._registry_path(tmp_path, actor).read_text(encoding="utf-8")
    assert "TOP-SECRET-ACCESS" not in raw_registry
    assert "TOP-SECRET-REFRESH" not in raw_registry


def test_multiple_accounts_same_provider_and_principal_isolation(tmp_path, monkeypatch):
    alice = principal("alice")
    bob = principal("bob")
    identities = iter(
        [
            {"provider_account_id": "g-1", "email": "one@gmail.test", "display_name": "One"},
            {"provider_account_id": "g-2", "email": "two@gmail.test", "display_name": "Two"},
        ]
    )
    monkeypatch.setattr(
        accounts,
        "_exchange_code",
        lambda provider, code, pending: {"access_token": f"token-{code}"},
    )
    monkeypatch.setattr(accounts, "_provider_identity", lambda provider, token: next(identities))
    monkeypatch.setattr(
        accounts,
        "_create_rclone_remote",
        lambda repo_root, principal, **kwargs: f"remote-{kwargs['account_id']}",
    )

    with desk_principal_context(alice):
        for code in ("one", "two"):
            started = accounts.start_oauth(tmp_path, provider="google_drive")
            accounts.complete_oauth(
                tmp_path,
                provider="google_drive",
                state=state_from(started),
                code=code,
            )
        assert len(accounts.list_connected_accounts(tmp_path)) == 2

    with desk_principal_context(bob):
        assert accounts.list_connected_accounts(tmp_path) == []


def test_router_exposes_connected_account_contract():
    routes = {(row["method"], row["path"]) for row in http_router.ROUTE_CATALOG}
    assert ("GET", "/library/accounts") in routes
    assert ("POST", "/library/accounts/oauth/start") in routes
    assert ("POST", "/library/accounts/oauth/complete") in routes
    assert ("POST", "/library/accounts/{account_id}/verify") in routes
    assert ("POST", "/library/accounts/{account_id}/disconnect") in routes
