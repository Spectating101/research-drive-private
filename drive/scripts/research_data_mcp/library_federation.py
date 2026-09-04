#!/usr/bin/env python3
"""Principal-bound connected-storage browsing and Library usage memory.

This module deliberately keeps provider identity separate from canonical Library
identity. Remote files become known Library evidence only when the canonical
registry contains an explicit holding matching provider + account + provider
item id. Filenames and paths are never used as identity heuristics.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from scripts.research_data_mcp.connected_accounts import (
    _client_credentials,
    _principal_dir,
    _provider,
    _rclone_config_path,
    _rclone_token,
    _require_named_principal,
    _run_rclone,
    list_connected_accounts,
)
from scripts.research_data_mcp.desk_principal import DeskPrincipal

DIRECTORY_BROWSE_PROVIDERS = frozenset({"google_drive", "dropbox"})
_MAX_DIRECTORY_PAGE = 200
_DEFAULT_DIRECTORY_PAGE = 50
_MAX_CURSOR_BYTES = 16_384
_MAX_CONTEXT_BYTES = 65_536


def _text(value: Any, *, limit: int = 4096) -> str:
    return str(value or "").strip()[:limit]


def _provider_key(value: Any) -> str:
    return _text(value, limit=64).lower().replace("-", "_").replace(" ", "_")


def _safe_limit(value: Any, *, default: int = _DEFAULT_DIRECTORY_PAGE) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(_MAX_DIRECTORY_PAGE, parsed))


def _selected_account(
    repo_root: Path,
    *,
    provider: str,
    account_id: str = "",
    principal: DeskPrincipal | None = None,
) -> tuple[DeskPrincipal, dict[str, Any]]:
    actor = _require_named_principal(principal)
    key = _provider_key(provider)
    if key not in DIRECTORY_BROWSE_PROVIDERS:
        raise ValueError(f"Directory browsing is not implemented for provider: {provider}")

    rows = [
        row
        for row in list_connected_accounts(repo_root, principal=actor)
        if _provider_key(row.get("provider")) == key
        and _text(row.get("status"), limit=32).lower() not in {"disconnected", "revoked", "expired", "error"}
    ]
    wanted = _text(account_id, limit=256)
    if wanted:
        row = next((item for item in rows if _text(item.get("id"), limit=256) == wanted), None)
        if row is None:
            raise KeyError(wanted)
    elif len(rows) == 1:
        row = rows[0]
    elif not rows:
        raise ValueError(f"No connected {key} account is available")
    else:
        raise ValueError("account_id is required when multiple accounts are connected for this provider")

    if not _text(row.get("remote"), limit=256):
        raise ValueError("Connected account is missing its private storage binding")
    return actor, dict(row)


def _remote_config(repo_root: Path, actor: DeskPrincipal, account: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    """Read only this principal's encrypted rclone config into process memory.

    The returned token never crosses the HTTP boundary. ``config dump`` is used
    because rclone owns refresh-token storage; the browser never receives remote
    names, client credentials, access tokens, or refresh tokens.
    """
    config_path = _rclone_config_path(repo_root, actor)
    proc = _run_rclone(config_path, "config", "dump", timeout=30)
    try:
        document = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Connected-storage credential store returned invalid configuration") from exc
    remote = document.get(_text(account.get("remote"), limit=256)) if isinstance(document, dict) else None
    if not isinstance(remote, dict):
        raise ValueError("Connected account credential binding is unavailable")
    return config_path, remote


def _token_document(remote: dict[str, Any]) -> dict[str, Any]:
    raw = remote.get("token")
    if isinstance(raw, dict):
        token = dict(raw)
    else:
        try:
            token = json.loads(str(raw or "{}"))
        except json.JSONDecodeError as exc:
            raise ValueError("Connected account token metadata is invalid") from exc
    if not isinstance(token, dict) or not _text(token.get("access_token"), limit=16_384):
        raise ValueError("Connected account has no usable access token")
    return token


def _expiry(token: dict[str, Any]) -> datetime | None:
    raw = _text(token.get("expiry"), limit=128)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    query: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    form: dict[str, str] | None = None,
) -> dict[str, Any]:
    target = url
    if query:
        encoded = urllib.parse.urlencode({key: value for key, value in query.items() if value not in {None, ""}})
        target = f"{url}{'&' if '?' in url else '?'}{encoded}" if encoded else url
    request_headers = {"Accept": "application/json", **(headers or {})}
    body: bytes | None = None
    if json_body is not None:
        body = json.dumps(json_body, separators=(",", ":")).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        body = urllib.parse.urlencode(form).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request = urllib.request.Request(target, data=body, headers=request_headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Connected-storage provider returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Connected-storage provider returned an invalid response")
    return payload


def _refresh_token(provider: str, token: dict[str, Any]) -> dict[str, Any]:
    refresh = _text(token.get("refresh_token"), limit=16_384)
    if not refresh:
        raise ValueError("Connected account needs reauthorization because no refresh token is available")
    cfg = _provider(provider)
    client_id, client_secret = _client_credentials(provider)
    if not client_id or not client_secret:
        raise ValueError("Connected-storage OAuth client is not configured on this host")
    refreshed = _request_json(
        str(cfg["token_url"]),
        method="POST",
        form={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    if not _text(refreshed.get("access_token"), limit=16_384):
        raise ValueError("Connected-storage provider did not return a refreshed access token")
    if not refreshed.get("refresh_token"):
        refreshed["refresh_token"] = refresh
    return refreshed


def _persist_refreshed_token(
    config_path: Path,
    *,
    account: dict[str, Any],
    token: dict[str, Any],
) -> dict[str, Any]:
    normalized = _rclone_token(token)
    _run_rclone(
        config_path,
        "config",
        "update",
        _text(account.get("remote"), limit=256),
        "token",
        json.dumps(normalized, separators=(",", ":")),
        "--non-interactive",
        timeout=30,
    )
    return normalized


def _access_token(
    repo_root: Path,
    *,
    actor: DeskPrincipal,
    account: dict[str, Any],
    provider: str,
    force_refresh: bool = False,
) -> str:
    config_path, remote = _remote_config(repo_root, actor, account)
    token = _token_document(remote)
    expires = _expiry(token)
    should_refresh = force_refresh or (
        expires is not None and expires <= datetime.now(timezone.utc) + timedelta(minutes=2)
    )
    if should_refresh:
        token = _persist_refreshed_token(
            config_path,
            account=account,
            token=_refresh_token(provider, token),
        )
    return _text(token.get("access_token"), limit=16_384)


def _with_auth_retry(
    repo_root: Path,
    *,
    actor: DeskPrincipal,
    account: dict[str, Any],
    provider: str,
    operation: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    token = _access_token(repo_root, actor=actor, account=account, provider=provider)
    try:
        return operation(token)
    except urllib.error.HTTPError as exc:
        if int(getattr(exc, "code", 0) or 0) != 401:
            raise
    token = _access_token(
        repo_root,
        actor=actor,
        account=account,
        provider=provider,
        force_refresh=True,
    )
    return operation(token)


def _raw_holdings(row: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("holdings", "storage_holdings", "replicas", "storage_locations"):
        value = row.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _holding_identity_index(registry_path: Path | None) -> dict[tuple[str, str, str], str]:
    """Return only explicit provider/account/item → logical-asset bindings."""
    if registry_path is None or not Path(registry_path).is_file():
        return {}
    try:
        document = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    datasets = document.get("datasets") if isinstance(document, dict) else []
    index: dict[tuple[str, str, str], str] = {}
    ambiguous: set[tuple[str, str, str]] = set()
    for dataset in datasets or []:
        if not isinstance(dataset, dict):
            continue
        logical_id = _text(
            dataset.get("logical_asset_id") or dataset.get("dataset_id") or dataset.get("registry_id"),
            limit=512,
        )
        if not logical_id:
            continue
        for holding in _raw_holdings(dataset):
            provider = _provider_key(
                holding.get("provider")
                or holding.get("storage_provider")
                or holding.get("service")
                or holding.get("system")
                or holding.get("backend")
            )
            account_id = _text(
                holding.get("account_id")
                or holding.get("storage_account_id")
                or holding.get("principal_id"),
                limit=256,
            )
            item_id = _text(
                holding.get("provider_item_id")
                or holding.get("remote_item_id")
                or holding.get("file_id")
                or holding.get("object_id"),
                limit=1024,
            )
            if not (provider and account_id and item_id):
                continue
            key = (provider, account_id, item_id)
            prior = index.get(key)
            if prior and prior != logical_id:
                ambiguous.add(key)
            else:
                index[key] = logical_id
    for key in ambiguous:
        index.pop(key, None)
    return index


def _content_access(account: dict[str, Any]) -> str:
    mode = _text(account.get("access_mode"), limit=32).lower()
    return "metadata_only" if mode == "index" else "available"


def _google_directory_page(
    *,
    token: str,
    account: dict[str, Any],
    parent_id: str,
    cursor: str,
    limit: int,
    identities: dict[tuple[str, str, str], str],
) -> dict[str, Any]:
    parent = parent_id or "root"
    escaped = parent.replace("\\", "\\\\").replace("'", "\\'")
    payload = _request_json(
        "https://www.googleapis.com/drive/v3/files",
        headers={"Authorization": f"Bearer {token}"},
        query={
            "q": f"'{escaped}' in parents and trashed = false",
            "spaces": "drive",
            "pageSize": limit,
            "pageToken": cursor,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "fields": "nextPageToken,files(id,name,mimeType,parents,size,modifiedTime,md5Checksum,version)",
        },
    )
    account_id = _text(account.get("id"), limit=256)
    items = []
    for raw in payload.get("files") or []:
        if not isinstance(raw, dict):
            continue
        item_id = _text(raw.get("id"), limit=1024)
        if not item_id:
            continue
        mime = _text(raw.get("mimeType"), limit=512)
        parents = raw.get("parents") if isinstance(raw.get("parents"), list) else []
        try:
            size = int(raw["size"]) if raw.get("size") not in {None, ""} else None
        except (TypeError, ValueError):
            size = None
        row = {
            "provider_item_id": item_id,
            "parent_item_id": _text(parents[0] if parents else parent, limit=1024),
            "account_id": account_id,
            "name": _text(raw.get("name"), limit=4096) or "Untitled",
            "kind": "folder" if mime == "application/vnd.google-apps.folder" else "file",
            "path": "",
            "metadata_visible": True,
            "content_access": _content_access(account),
            "modified_at": _text(raw.get("modifiedTime"), limit=128),
            "mime_type": mime,
            "size_bytes": size,
        }
        logical_id = identities.get(("google_drive", account_id, item_id))
        if logical_id:
            row["logical_asset_id"] = logical_id
        items.append(row)
    next_cursor = _text(payload.get("nextPageToken"), limit=_MAX_CURSOR_BYTES)
    return {"items": items, "next_cursor": next_cursor, "has_more": bool(next_cursor)}


def _dropbox_directory_page(
    *,
    token: str,
    account: dict[str, Any],
    parent_id: str,
    cursor: str,
    limit: int,
    identities: dict[tuple[str, str, str], str],
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    if cursor:
        payload = _request_json(
            "https://api.dropboxapi.com/2/files/list_folder/continue",
            method="POST",
            headers=headers,
            json_body={"cursor": cursor},
        )
    else:
        path = f"id:{parent_id}" if parent_id else ""
        payload = _request_json(
            "https://api.dropboxapi.com/2/files/list_folder",
            method="POST",
            headers=headers,
            json_body={
                "path": path,
                "recursive": False,
                "include_deleted": False,
                "include_mounted_folders": True,
                "limit": limit,
            },
        )
    account_id = _text(account.get("id"), limit=256)
    items = []
    for raw in payload.get("entries") or []:
        if not isinstance(raw, dict):
            continue
        item_id = _text(raw.get("id"), limit=1024)
        if not item_id:
            continue
        tag = _text(raw.get(".tag"), limit=32).lower()
        row = {
            "provider_item_id": item_id,
            "parent_item_id": _text(parent_id, limit=1024),
            "account_id": account_id,
            "name": _text(raw.get("name"), limit=4096) or "Untitled",
            "kind": "folder" if tag == "folder" else "file",
            "path": _text(raw.get("path_display") or raw.get("path_lower"), limit=8192),
            "metadata_visible": True,
            "content_access": _content_access(account),
            "modified_at": _text(raw.get("server_modified"), limit=128),
            "mime_type": "",
            "size_bytes": int(raw.get("size")) if str(raw.get("size") or "").isdigit() else None,
        }
        logical_id = identities.get(("dropbox", account_id, item_id))
        if logical_id:
            row["logical_asset_id"] = logical_id
        items.append(row)
    next_cursor = _text(payload.get("cursor"), limit=_MAX_CURSOR_BYTES) if payload.get("has_more") else ""
    return {"items": items, "next_cursor": next_cursor, "has_more": bool(payload.get("has_more") and next_cursor)}


def list_provider_directory(
    repo_root: Path,
    *,
    provider: str,
    account_id: str = "",
    parent_id: str = "",
    cursor: str = "",
    limit: int = _DEFAULT_DIRECTORY_PAGE,
    registry_path: Path | None = None,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    key = _provider_key(provider)
    if len(str(cursor or "").encode("utf-8")) > _MAX_CURSOR_BYTES:
        raise ValueError("Provider cursor is too large")
    actor, account = _selected_account(
        repo_root,
        provider=key,
        account_id=account_id,
        principal=principal,
    )
    identities = _holding_identity_index(registry_path)
    page_size = _safe_limit(limit)
    parent = _text(parent_id, limit=1024)
    page_cursor = _text(cursor, limit=_MAX_CURSOR_BYTES)

    def operation(token: str) -> dict[str, Any]:
        if key == "google_drive":
            return _google_directory_page(
                token=token,
                account=account,
                parent_id=parent,
                cursor=page_cursor,
                limit=page_size,
                identities=identities,
            )
        return _dropbox_directory_page(
            token=token,
            account=account,
            parent_id=parent,
            cursor=page_cursor,
            limit=page_size,
            identities=identities,
        )

    page = _with_auth_retry(
        repo_root,
        actor=actor,
        account=account,
        provider=key,
        operation=operation,
    )
    return {
        "provider": key,
        "account_id": _text(account.get("id"), limit=256),
        "parent_id": parent,
        "items": page.get("items") or [],
        "next_cursor": _text(page.get("next_cursor"), limit=_MAX_CURSOR_BYTES),
        "has_more": bool(page.get("has_more")),
        "page_size": page_size,
    }


def _usage_db_path(repo_root: Path, actor: DeskPrincipal) -> Path:
    return _principal_dir(repo_root, actor) / "library_evidence_usage.sqlite3"


@contextmanager
def _usage_db(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute(
            """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_hash TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                logical_asset_id TEXT NOT NULL,
                version_id TEXT NOT NULL,
                action TEXT NOT NULL,
                project_id TEXT NOT NULL,
                related_asset_ids_json TEXT NOT NULL,
                output_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                context_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_usage_asset_time ON events(logical_asset_id, occurred_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_usage_project_time ON events(project_id, occurred_at DESC)")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        try:
            path.chmod(0o600)
        except OSError:
            pass


def _bounded_id(value: Any, field: str, *, required: bool = False) -> str:
    raw = str(value or "").strip()
    if required and not raw:
        raise ValueError(f"{field} is required")
    if len(raw) > 512:
        raise ValueError(f"{field} is too long")
    return raw


def normalize_usage_event(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError("Library usage event must be an object")
    event_type = _bounded_id(event.get("event_type"), "event_type", required=True)
    if event_type != "library_evidence_usage":
        raise ValueError("event_type must be library_evidence_usage")
    occurred_at = _text(event.get("occurred_at"), limit=128)
    if not occurred_at:
        raise ValueError("occurred_at is required")
    try:
        parsed = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("occurred_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("occurred_at must include a timezone")

    related = event.get("related_asset_ids") or []
    if not isinstance(related, list):
        raise ValueError("related_asset_ids must be an array")
    related_ids: list[str] = []
    for value in related[:100]:
        item = _bounded_id(value, "related_asset_ids")
        if item and item not in related_ids:
            related_ids.append(item)

    context = event.get("context") or {}
    if not isinstance(context, dict):
        raise ValueError("context must be an object")
    try:
        context_json = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("context must be JSON-serializable") from exc
    if len(context_json.encode("utf-8")) > _MAX_CONTEXT_BYTES:
        raise ValueError("context is too large")

    return {
        "event_type": event_type,
        "logical_asset_id": _bounded_id(event.get("logical_asset_id"), "logical_asset_id", required=True),
        "version_id": _bounded_id(event.get("version_id"), "version_id", required=True),
        "action": _bounded_id(event.get("action"), "action", required=True),
        "project_id": _bounded_id(event.get("project_id"), "project_id"),
        "related_asset_ids": related_ids,
        "output_id": _bounded_id(event.get("output_id"), "output_id"),
        "occurred_at": parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "context": context,
    }


def persist_library_usage_event(
    repo_root: Path,
    event: dict[str, Any],
    *,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_named_principal(principal)
    normalized = normalize_usage_event(event)
    canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    recorded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    path = _usage_db_path(repo_root, actor)
    with _usage_db(path) as db:
        before = db.total_changes
        db.execute(
            """INSERT OR IGNORE INTO events(
                event_hash, event_type, logical_asset_id, version_id, action,
                project_id, related_asset_ids_json, output_id, occurred_at,
                context_json, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_hash,
                normalized["event_type"],
                normalized["logical_asset_id"],
                normalized["version_id"],
                normalized["action"],
                normalized["project_id"],
                json.dumps(normalized["related_asset_ids"], ensure_ascii=False),
                normalized["output_id"],
                normalized["occurred_at"],
                json.dumps(normalized["context"], ensure_ascii=False, sort_keys=True),
                recorded_at,
            ),
        )
        inserted = db.total_changes > before
        row = db.execute("SELECT id, recorded_at FROM events WHERE event_hash = ?", (event_hash,)).fetchone()
    return {
        "ok": True,
        "event_id": int(row["id"]),
        "deduplicated": not inserted,
        "recorded_at": str(row["recorded_at"]),
        "event": normalized,
    }


def list_library_usage_events(
    repo_root: Path,
    *,
    logical_asset_id: str = "",
    project_id: str = "",
    limit: int = 100,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_named_principal(principal)
    asset = _bounded_id(logical_asset_id, "logical_asset_id")
    project = _bounded_id(project_id, "project_id")
    safe_limit = max(1, min(200, int(limit or 100)))
    path = _usage_db_path(repo_root, actor)
    if not path.is_file():
        return {"events": [], "count": 0}
    clauses: list[str] = []
    params: list[Any] = []
    if asset:
        clauses.append("logical_asset_id = ?")
        params.append(asset)
    if project:
        clauses.append("project_id = ?")
        params.append(project)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(safe_limit)
    with _usage_db(path) as db:
        rows = db.execute(
            f"SELECT * FROM events{where} ORDER BY occurred_at DESC, id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    events = []
    for row in rows:
        events.append(
            {
                "event_id": int(row["id"]),
                "event_type": row["event_type"],
                "logical_asset_id": row["logical_asset_id"],
                "version_id": row["version_id"],
                "action": row["action"],
                "project_id": row["project_id"],
                "related_asset_ids": json.loads(row["related_asset_ids_json"] or "[]"),
                "output_id": row["output_id"],
                "occurred_at": row["occurred_at"],
                "context": json.loads(row["context_json"] or "{}"),
                "recorded_at": row["recorded_at"],
            }
        )
    return {"events": events, "count": len(events)}
