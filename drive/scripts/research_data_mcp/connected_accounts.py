#!/usr/bin/env python3
"""Principal-bound cloud storage accounts for Research Drive.

The account registry contains metadata only. OAuth credentials live solely in a
principal-local rclone config, which is never returned through the HTTP API.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.desk_auth import current_desk_principal
from scripts.research_data_mcp.desk_principal import DeskPrincipal

_ACCOUNT_ROOT = Path("data_lake/research_drive/accounts")
_PENDING_TTL_SECONDS = 600

_PROVIDERS: dict[str, dict[str, Any]] = {
    "google_drive": {
        "label": "Google Drive",
        "rclone_type": "drive",
        "client_id_env": "YZU_GOOGLE_DRIVE_CLIENT_ID",
        "client_secret_env": "YZU_GOOGLE_DRIVE_CLIENT_SECRET",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "supports_index_only": True,
        "scopes": {
            "index": [
                "openid",
                "email",
                "profile",
                "https://www.googleapis.com/auth/drive.metadata.readonly",
            ],
            "read": [
                "openid",
                "email",
                "profile",
                "https://www.googleapis.com/auth/drive.readonly",
            ],
            "write": [
                "openid",
                "email",
                "profile",
                "https://www.googleapis.com/auth/drive",
            ],
        },
        "rclone_scopes": {
            "index": "drive.metadata.readonly",
            "read": "drive.readonly",
            "write": "drive",
        },
    },
    "dropbox": {
        "label": "Dropbox",
        "rclone_type": "dropbox",
        "client_id_env": "YZU_DROPBOX_CLIENT_ID",
        "client_secret_env": "YZU_DROPBOX_CLIENT_SECRET",
        "authorize_url": "https://www.dropbox.com/oauth2/authorize",
        "token_url": "https://api.dropboxapi.com/oauth2/token",
        "userinfo_url": "https://api.dropboxapi.com/2/users/get_current_account",
        "supports_index_only": True,
        "scopes": {
            "index": ["account_info.read", "files.metadata.read"],
            "read": ["account_info.read", "files.metadata.read", "files.content.read"],
            "write": [
                "account_info.read",
                "files.metadata.read",
                "files.content.read",
                "files.metadata.write",
                "files.content.write",
            ],
        },
    },
    "onedrive": {
        "label": "OneDrive",
        "rclone_type": "onedrive",
        "client_id_env": "YZU_ONEDRIVE_CLIENT_ID",
        "client_secret_env": "YZU_ONEDRIVE_CLIENT_SECRET",
        "supports_index_only": False,
        "scopes": {
            "index": ["openid", "profile", "email", "offline_access", "Files.Read"],
            "read": ["openid", "profile", "email", "offline_access", "Files.Read"],
            "write": ["openid", "profile", "email", "offline_access", "Files.ReadWrite"],
        },
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_principal_id(principal_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(principal_id or "").strip())[:96]
    if not cleaned:
        raise ValueError("principal id is required")
    suffix = hashlib.sha256(str(principal_id).encode("utf-8")).hexdigest()[:10]
    return f"{cleaned}-{suffix}"


def _require_named_principal(principal: DeskPrincipal | None = None) -> DeskPrincipal:
    actor = principal or current_desk_principal()
    if actor is None:
        raise PermissionError("Connected accounts require an authenticated Research Drive account")
    if actor.role not in {"member", "operator"}:
        raise PermissionError("Connected accounts are available only to named member or operator accounts")
    return actor


def _principal_dir(repo_root: Path, principal: DeskPrincipal) -> Path:
    root = Path(repo_root).resolve() / _ACCOUNT_ROOT / _safe_principal_id(principal.principal_id)
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root


def _registry_path(repo_root: Path, principal: DeskPrincipal) -> Path:
    return _principal_dir(repo_root, principal) / "registry.json"


def _pending_path(repo_root: Path, principal: DeskPrincipal) -> Path:
    return _principal_dir(repo_root, principal) / "oauth_pending.json"


def _rclone_config_path(repo_root: Path, principal: DeskPrincipal) -> Path:
    return _principal_dir(repo_root, principal) / "rclone.conf"


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def rclone_ready() -> bool:
    return bool(shutil.which("rclone"))


def _public_base_url() -> str:
    raw = str(
        os.getenv("YZU_CONNECTED_ACCOUNTS_PUBLIC_BASE_URL")
        or os.getenv("YZU_DESK_PUBLIC_BASE_URL")
        or ""
    ).strip().rstrip("/")
    if not raw:
        raise ValueError("Connected-account OAuth requires YZU_CONNECTED_ACCOUNTS_PUBLIC_BASE_URL")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Connected-account public base URL must be an absolute http(s) origin")
    if parsed.params or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Connected-account public base URL must not contain a path, query, or fragment")
    return f"{parsed.scheme}://{parsed.netloc}"


def _provider(provider: str) -> dict[str, Any]:
    key = str(provider or "").strip().lower()
    if key not in _PROVIDERS:
        raise ValueError(f"unsupported connected-account provider: {provider}")
    row = dict(_PROVIDERS[key])
    if key == "onedrive":
        tenant = str(os.getenv("YZU_ONEDRIVE_TENANT") or "common").strip() or "common"
        safe_tenant = urllib.parse.quote(tenant, safe="")
        row["authorize_url"] = f"https://login.microsoftonline.com/{safe_tenant}/oauth2/v2.0/authorize"
        row["token_url"] = f"https://login.microsoftonline.com/{safe_tenant}/oauth2/v2.0/token"
        row["userinfo_url"] = "https://graph.microsoft.com/v1.0/me"
        row["drive_url"] = "https://graph.microsoft.com/v1.0/me/drive"
    return row


def _client_credentials(provider: str) -> tuple[str, str]:
    cfg = _provider(provider)
    client_id = str(os.getenv(cfg["client_id_env"]) or "").strip()
    client_secret = str(os.getenv(cfg["client_secret_env"]) or "").strip()
    return client_id, client_secret


def provider_catalog() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    rclone = rclone_ready()
    encrypted = bool(
        str(os.getenv("RCLONE_CONFIG_PASS") or "").strip()
        or str(os.getenv("RCLONE_PASSWORD_COMMAND") or "").strip()
    )
    for provider, raw in _PROVIDERS.items():
        client_id, client_secret = _client_credentials(provider)
        out.append(
            {
                "id": provider,
                "label": raw["label"],
                "configured": bool(client_id and client_secret),
                "rclone_available": rclone,
                "credential_store_encrypted": encrypted,
                "access_modes": ["index", "read", "write"],
                "default_access_mode": "read",
                "supports_index_only": bool(raw.get("supports_index_only")),
                "index_effective_access": "metadata_only" if raw.get("supports_index_only") else "read_only",
            }
        )
    return out


def list_connected_accounts(repo_root: Path, *, principal: DeskPrincipal | None = None) -> list[dict[str, Any]]:
    actor = _require_named_principal(principal)
    payload = _load_json(_registry_path(repo_root, actor), {"accounts": []})
    rows = payload.get("accounts") if isinstance(payload, dict) else []
    return [dict(row) for row in rows or [] if isinstance(row, dict)]


def _save_accounts(repo_root: Path, principal: DeskPrincipal, accounts: list[dict[str, Any]]) -> None:
    _save_json(
        _registry_path(repo_root, principal),
        {
            "version": 1,
            "principal_id": principal.principal_id,
            "updated_at": _utc_now(),
            "accounts": accounts,
        },
    )


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _oauth_redirect_uri(provider: str) -> str:
    base = _public_base_url()
    query = urllib.parse.urlencode({"tab": "settings", "rd_storage_oauth": provider})
    return f"{base}/?{query}"


def _pending_rows(repo_root: Path, principal: DeskPrincipal) -> dict[str, Any]:
    payload = _load_json(_pending_path(repo_root, principal), {"pending": {}})
    rows = payload.get("pending") if isinstance(payload, dict) else {}
    now = int(time.time())
    clean = {
        key: row
        for key, row in (rows or {}).items()
        if isinstance(row, dict) and int(row.get("expires_at") or 0) >= now
    }
    if clean != rows:
        _save_json(_pending_path(repo_root, principal), {"pending": clean})
    return clean


def start_oauth(
    repo_root: Path,
    *,
    provider: str,
    access_mode: str = "read",
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_named_principal(principal)
    key = str(provider or "").strip().lower()
    cfg = _provider(key)
    mode = str(access_mode or "read").strip().lower()
    if mode not in cfg["scopes"]:
        raise ValueError("access_mode must be index, read, or write")
    client_id, client_secret = _client_credentials(key)
    if not client_id or not client_secret:
        raise ValueError(f"{cfg['label']} OAuth app is not configured on this Research Drive host")
    if not rclone_ready():
        raise ValueError("rclone is required before cloud storage accounts can be connected")

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    redirect_uri = _oauth_redirect_uri(key)
    state_key = hashlib.sha256(state.encode("utf-8")).hexdigest()

    pending = _pending_rows(repo_root, actor)
    pending[state_key] = {
        "principal_id": actor.principal_id,
        "provider": key,
        "access_mode": mode,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "expires_at": int(time.time()) + _PENDING_TTL_SECONDS,
    }
    _save_json(_pending_path(repo_root, actor), {"pending": pending})

    params: dict[str, str] = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(cfg["scopes"][mode]),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if key == "google_drive":
        params.update({"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"})
    elif key == "dropbox":
        params["token_access_type"] = "offline"
    elif key == "onedrive":
        params["response_mode"] = "query"

    return {
        "provider": key,
        "access_mode": mode,
        "authorize_url": f"{cfg['authorize_url']}?{urllib.parse.urlencode(params)}",
        "redirect_uri": redirect_uri,
        "expires_in": _PENDING_TTL_SECONDS,
    }


def _take_pending(repo_root: Path, principal: DeskPrincipal, *, provider: str, state: str) -> dict[str, Any]:
    state_key = hashlib.sha256(str(state or "").encode("utf-8")).hexdigest()
    rows = _pending_rows(repo_root, principal)
    row = rows.pop(state_key, None)
    _save_json(_pending_path(repo_root, principal), {"pending": rows})
    if not isinstance(row, dict):
        raise ValueError("OAuth state is invalid or expired")
    if row.get("provider") != provider or row.get("principal_id") != principal.principal_id:
        raise ValueError("OAuth state does not belong to this account/provider")
    if int(row.get("expires_at") or 0) < int(time.time()):
        raise ValueError("OAuth state has expired")
    return row


def _http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    form: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = None
    request_headers = dict(headers or {})
    if form is not None:
        body = urllib.parse.urlencode(form).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request_headers.setdefault("Accept", "application/json")
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise ValueError(f"OAuth provider returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ValueError("OAuth provider is unreachable") from exc
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("OAuth provider returned an invalid response") from exc
    if not isinstance(data, dict):
        raise ValueError("OAuth provider returned an invalid response")
    return data


def _exchange_code(provider: str, *, code: str, pending: dict[str, Any]) -> dict[str, Any]:
    cfg = _provider(provider)
    client_id, client_secret = _client_credentials(provider)
    form = {
        "grant_type": "authorization_code",
        "code": str(code or "").strip(),
        "redirect_uri": str(pending["redirect_uri"]),
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": str(pending["code_verifier"]),
    }
    token = _http_json(cfg["token_url"], method="POST", form=form)
    if not str(token.get("access_token") or "").strip():
        raise ValueError("OAuth provider did not return an access token")
    return token


def _bearer(token: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {str(token.get('access_token') or '').strip()}"}


def _provider_identity(provider: str, token: dict[str, Any]) -> dict[str, Any]:
    cfg = _provider(provider)
    if provider == "dropbox":
        profile = _http_json(
            cfg["userinfo_url"], method="POST", headers={**_bearer(token), "Content-Type": "application/json"}
        )
        name = profile.get("name") if isinstance(profile.get("name"), dict) else {}
        return {
            "provider_account_id": str(profile.get("account_id") or token.get("account_id") or ""),
            "email": str(profile.get("email") or ""),
            "display_name": str(name.get("display_name") or profile.get("email") or "Dropbox"),
        }
    profile = _http_json(cfg["userinfo_url"], headers=_bearer(token))
    if provider == "google_drive":
        return {
            "provider_account_id": str(profile.get("sub") or profile.get("email") or ""),
            "email": str(profile.get("email") or ""),
            "display_name": str(profile.get("name") or profile.get("email") or "Google Drive"),
        }
    drive = _http_json(cfg["drive_url"], headers=_bearer(token))
    return {
        "provider_account_id": str(profile.get("id") or profile.get("userPrincipalName") or ""),
        "email": str(profile.get("mail") or profile.get("userPrincipalName") or ""),
        "display_name": str(profile.get("displayName") or profile.get("userPrincipalName") or "OneDrive"),
        "drive_id": str(drive.get("id") or ""),
        "drive_type": str(drive.get("driveType") or "business"),
    }


def _rclone_token(token: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "access_token": str(token.get("access_token") or ""),
        "token_type": str(token.get("token_type") or "Bearer"),
    }
    if token.get("refresh_token"):
        out["refresh_token"] = str(token["refresh_token"])
    try:
        expires_in = int(token.get("expires_in") or 0)
    except (TypeError, ValueError):
        expires_in = 0
    if expires_in > 0:
        expiry = datetime.now(timezone.utc) + timedelta(seconds=max(1, expires_in - 30))
        out["expiry"] = expiry.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return out


def _run_rclone(config_path: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    if not rclone_ready():
        raise ValueError("rclone is not installed on this Research Drive host")
    cmd = ["rclone", *args, "--config", str(config_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("rclone could not complete the storage operation") from exc
    if proc.returncode != 0:
        raise ValueError(f"rclone operation failed with exit code {proc.returncode}")
    if config_path.exists():
        try:
            config_path.chmod(0o600)
        except OSError:
            pass
    return proc


def _remote_name(principal: DeskPrincipal, provider: str, account_id: str) -> str:
    principal_hash = hashlib.sha256(principal.principal_id.encode("utf-8")).hexdigest()[:10]
    account_suffix = re.sub(r"[^A-Za-z0-9]", "", account_id)[-10:]
    return f"rd_{principal_hash}_{provider}_{account_suffix}"


def _create_rclone_remote(
    repo_root: Path,
    principal: DeskPrincipal,
    *,
    provider: str,
    access_mode: str,
    account_id: str,
    token: dict[str, Any],
    identity: dict[str, Any],
) -> str:
    cfg = _provider(provider)
    client_id, client_secret = _client_credentials(provider)
    remote = _remote_name(principal, provider, account_id)
    config_path = _rclone_config_path(repo_root, principal)
    args = [
        "config", "create", remote, str(cfg["rclone_type"]),
        "token", json.dumps(_rclone_token(token), separators=(",", ":")),
        "client_id", client_id,
        "client_secret", client_secret,
    ]
    if provider == "google_drive":
        args.extend(["scope", str(cfg["rclone_scopes"][access_mode])])
    elif provider == "onedrive":
        drive_id = str(identity.get("drive_id") or "")
        drive_type = str(identity.get("drive_type") or "")
        if not drive_id:
            raise ValueError("OneDrive did not report a drive id")
        args.extend(["drive_id", drive_id, "drive_type", drive_type or "business"])
    args.append("--non-interactive")
    _run_rclone(config_path, *args, timeout=60)
    return remote


def complete_oauth(
    repo_root: Path,
    *,
    provider: str,
    state: str,
    code: str,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_named_principal(principal)
    key = str(provider or "").strip().lower()
    _provider(key)
    if not str(code or "").strip():
        raise ValueError("OAuth authorization code is required")
    pending = _take_pending(repo_root, actor, provider=key, state=state)
    token = _exchange_code(key, code=code, pending=pending)
    identity = _provider_identity(key, token)
    external_id = str(identity.get("provider_account_id") or "").strip()
    if not external_id:
        raise ValueError("OAuth provider did not return a stable account identity")

    accounts = list_connected_accounts(repo_root, principal=actor)
    existing = next(
        (
            row for row in accounts
            if row.get("provider") == key and row.get("provider_account_id") == external_id
        ),
        None,
    )
    account_id = (
        str(existing.get("id"))
        if isinstance(existing, dict) and existing.get("id")
        else f"acc_{secrets.token_urlsafe(12)}"
    )
    remote = _create_rclone_remote(
        repo_root,
        actor,
        provider=key,
        access_mode=str(pending["access_mode"]),
        account_id=account_id,
        token=token,
        identity=identity,
    )

    now = _utc_now()
    row = {
        "id": account_id,
        "provider": key,
        "provider_account_id": external_id,
        "label": str(identity.get("display_name") or identity.get("email") or _provider(key)["label"]),
        "email": str(identity.get("email") or ""),
        "access_mode": str(pending["access_mode"]),
        "remote": remote,
        "status": "connected",
        "created_at": str(existing.get("created_at") if isinstance(existing, dict) else "") or now,
        "updated_at": now,
        "verified_at": None,
    }
    accounts = [a for a in accounts if a.get("id") != account_id]
    accounts.append(row)
    _save_accounts(repo_root, actor, accounts)
    return dict(row)


def verify_connected_account(
    repo_root: Path,
    *,
    account_id: str,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_named_principal(principal)
    accounts = list_connected_accounts(repo_root, principal=actor)
    row = next((a for a in accounts if a.get("id") == account_id), None)
    if not row:
        raise KeyError(account_id)
    config_path = _rclone_config_path(repo_root, actor)
    _run_rclone(config_path, "lsf", f"{row['remote']}:", "--max-depth", "1", timeout=45)
    now = _utc_now()
    updated = {**row, "status": "connected", "verified_at": now, "updated_at": now}
    accounts = [updated if a.get("id") == account_id else a for a in accounts]
    _save_accounts(repo_root, actor, accounts)
    return dict(updated)


def disconnect_connected_account(
    repo_root: Path,
    *,
    account_id: str,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_named_principal(principal)
    accounts = list_connected_accounts(repo_root, principal=actor)
    row = next((a for a in accounts if a.get("id") == account_id), None)
    if not row:
        raise KeyError(account_id)
    config_path = _rclone_config_path(repo_root, actor)
    if config_path.exists() and rclone_ready():
        _run_rclone(config_path, "config", "delete", str(row["remote"]), timeout=30)
    accounts = [a for a in accounts if a.get("id") != account_id]
    _save_accounts(repo_root, actor, accounts)
    return {
        "ok": True,
        "disconnected": account_id,
        "provider": row.get("provider"),
        "note": "Research Drive removed its local credential and binding. Provider-side grants can also be revoked from the provider account.",
    }


def connected_accounts_document(
    repo_root: Path, *, principal: DeskPrincipal | None = None
) -> dict[str, Any]:
    actor = _require_named_principal(principal)
    return {
        "version": 1,
        "principal": actor.public_dict(),
        "accounts": list_connected_accounts(repo_root, principal=actor),
        "providers": provider_catalog(),
        "storage_model": {
            "mode": "federated",
            "bytes_move_by_default": False,
            "default_connection_access": "read",
            "credentials_returned_to_browser": False,
            "multiple_accounts_per_provider": True,
        },
    }
