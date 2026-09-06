from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.research_data_mcp import connected_accounts_security as security
from scripts.research_data_mcp.desk_auth import desk_principal_context
from scripts.research_data_mcp.desk_principal import DeskPrincipal


def principal(pid: str = "alice") -> DeskPrincipal:
    return DeskPrincipal(
        principal_id=pid,
        email=f"{pid}@example.test",
        display_name=pid,
        role="member",
    )


def test_encrypted_store_fails_closed_without_password_source(tmp_path, monkeypatch):
    monkeypatch.delenv("RCLONE_CONFIG_PASS", raising=False)
    monkeypatch.delenv("RCLONE_PASSWORD_COMMAND", raising=False)
    monkeypatch.setattr(security, "rclone_ready", lambda: True)
    with desk_principal_context(principal()):
        with pytest.raises(ValueError, match="encrypted credential storage"):
            security.ensure_encrypted_credential_store(tmp_path, initialize=True)


def test_new_store_is_encrypted_before_use(tmp_path, monkeypatch):
    monkeypatch.setenv("RCLONE_PASSWORD_COMMAND", "/bin/echo test-password")
    monkeypatch.setattr(security, "rclone_ready", lambda: True)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        config_index = cmd.index("--config") + 1
        path = security.Path(cmd[config_index])
        if cmd[1:3] == ["config", "touch"]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(security.subprocess, "run", fake_run)
    with desk_principal_context(principal()):
        path = security.ensure_encrypted_credential_store(tmp_path, initialize=True)

    operations = [call[1:4] for call in calls]
    assert ["config", "touch", "--config"] in operations
    assert ["config", "encryption", "set"] in operations
    assert ["config", "encryption", "check"] in operations
    assert path.exists()


def test_existing_plain_or_unreadable_store_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("RCLONE_CONFIG_PASS", "host-secret")
    monkeypatch.setattr(security, "rclone_ready", lambda: True)

    def fake_run(cmd, **kwargs):
        if cmd[1:4] == ["config", "encryption", "check"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="not encrypted")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(security.subprocess, "run", fake_run)
    actor = principal()
    with desk_principal_context(actor):
        path = security._rclone_config_path(tmp_path, actor)
        path.write_text("[remote]\ntoken = secret\n", encoding="utf-8")
        with pytest.raises(ValueError, match="not encrypted or cannot be decrypted"):
            security.ensure_encrypted_credential_store(tmp_path)


def test_public_account_redacts_adapter_and_credential_fields():
    public = security.public_connected_account(
        {
            "id": "acc_1",
            "provider": "google_drive",
            "label": "Alice Drive",
            "remote": "rd_internal_remote",
            "credential_ref": "secret-ref",
            "token": "token",
            "access_token": "access",
            "refresh_token": "refresh",
            "client_secret": "client-secret",
        }
    )
    assert public == {"id": "acc_1", "provider": "google_drive", "label": "Alice Drive"}


def test_public_document_declares_encrypted_boundary(monkeypatch):
    monkeypatch.setenv("RCLONE_CONFIG_PASS", "host-secret")
    document = security.public_connected_accounts_document(
        {
            "accounts": [{"id": "acc_1", "provider": "dropbox", "remote": "internal"}],
            "providers": [{"id": "dropbox", "credential_store_encrypted": True}],
            "storage_model": {"mode": "federated"},
        }
    )
    assert "remote" not in document["accounts"][0]
    assert document["providers"][0]["credential_store_encrypted"] is True
    assert document["storage_model"]["credential_store_required_encrypted"] is True
    assert document["storage_model"]["internal_adapter_ids_returned_to_browser"] is False
