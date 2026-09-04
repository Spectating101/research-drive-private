#!/usr/bin/env python3
"""Fail-closed credential-store boundary for Research Drive connected accounts."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.connected_accounts import (
    _require_named_principal,
    _rclone_config_path,
    rclone_ready,
)
from scripts.research_data_mcp.desk_principal import DeskPrincipal

_DIRECTORY_BROWSE_PROVIDERS = frozenset({"google_drive", "dropbox"})


def credential_password_configured() -> bool:
    """Return whether rclone has a non-interactive config-password source."""
    return bool(
        str(os.getenv("RCLONE_CONFIG_PASS") or "").strip()
        or str(os.getenv("RCLONE_PASSWORD_COMMAND") or "").strip()
    )


def _run_config_command(config_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    if not rclone_ready():
        raise ValueError("rclone is required before cloud storage accounts can be connected")
    cmd = [
        "rclone",
        *args,
        "--config",
        str(config_path),
        "--ask-password=false",
    ]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Research Drive could not verify the encrypted credential store") from exc


def ensure_encrypted_credential_store(
    repo_root: Path,
    *,
    principal: DeskPrincipal | None = None,
    initialize: bool = False,
) -> Path:
    """Require a decryptable encrypted rclone config before any OAuth token is stored.

    When ``initialize`` is true, a new principal-local config is created and encrypted
    before the OAuth flow starts. Secrets are supplied only through rclone's password
    environment/command mechanism; they are never placed on the command line.
    """
    actor = _require_named_principal(principal)
    if not credential_password_configured():
        raise ValueError(
            "Connected storage requires encrypted credential storage. Configure "
            "RCLONE_CONFIG_PASS or RCLONE_PASSWORD_COMMAND on this Research Drive host."
        )
    config_path = _rclone_config_path(repo_root, actor)

    if not config_path.exists():
        if not initialize:
            raise ValueError("Encrypted connected-storage credential store is not initialized")
        touched = _run_config_command(config_path, "config", "touch")
        if touched.returncode != 0:
            raise ValueError("Research Drive could not initialize the connected-storage credential store")
        encrypted = _run_config_command(config_path, "config", "encryption", "set")
        if encrypted.returncode != 0:
            try:
                config_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise ValueError("Research Drive could not encrypt the connected-storage credential store")

    checked = _run_config_command(config_path, "config", "encryption", "check")
    if checked.returncode != 0:
        raise ValueError("Connected-storage credential store is not encrypted or cannot be decrypted")

    try:
        config_path.chmod(0o600)
    except OSError:
        pass
    return config_path


def public_connected_account(account: dict[str, Any] | None) -> dict[str, Any]:
    """Return only browser-safe connected-account metadata."""
    row = dict(account or {})
    for key in (
        "remote",
        "credential_ref",
        "token",
        "access_token",
        "refresh_token",
        "client_secret",
    ):
        row.pop(key, None)
    return row


def public_connected_accounts_document(document: dict[str, Any]) -> dict[str, Any]:
    """Redact implementation identifiers and expose encryption readiness honestly."""
    out = dict(document or {})
    out["accounts"] = [public_connected_account(row) for row in out.get("accounts") or []]
    password_ready = credential_password_configured()
    providers = []
    for provider in out.get("providers") or []:
        row = dict(provider)
        row["credential_password_configured"] = password_ready
        # Do not advertise a provider as connectable until encrypted storage can
        # be established. Actual config encryption is verified at OAuth start.
        row["credential_store_encrypted"] = bool(row.get("credential_store_encrypted") and password_ready)
        provider_id = str(row.get("id") or "").strip().lower()
        directory_ready = bool(
            provider_id in _DIRECTORY_BROWSE_PROVIDERS
            and row.get("configured")
            and row.get("rclone_available")
            and row.get("credential_store_encrypted")
        )
        capabilities = dict(row.get("capabilities") or {})
        capabilities["directory_browse"] = directory_ready
        row["capabilities"] = capabilities
        # Keep the explicit flat flag for older Library clients while the nested
        # capabilities object is the canonical forward-looking contract.
        row["directory_browse_available"] = directory_ready
        providers.append(row)
    out["providers"] = providers
    storage_model = dict(out.get("storage_model") or {})
    storage_model["credential_store_required_encrypted"] = True
    storage_model["internal_adapter_ids_returned_to_browser"] = False
    out["storage_model"] = storage_model
    return out
