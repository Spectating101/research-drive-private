#!/usr/bin/env python3
"""Canonical runtime adapters for Library federation.

Provider quirks live here. Canonical Library identity stays shared; connected
storage holding identity stays principal-local. No filename/path heuristic is
permitted to turn an arbitrary provider file into Library evidence.
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.library_federation import (
    _holding_identity_index,
    _provider_key,
    _request_json,
    _safe_limit,
    _selected_account,
    _text,
    _with_auth_retry,
    persist_library_usage_event,
)
from scripts.research_data_mcp.library_federation_holdings import (
    _canonical_logical_ids,
    provider_holding_identity_index,
    refresh_bound_holding_observations,
)
from scripts.research_data_mcp.desk_principal import DeskPrincipal

_MAX_CURSOR_BYTES = 16_384


def _content_access(account: dict[str, Any]) -> str:
    mode = _text(account.get("access_mode"), limit=32).lower()
    return "metadata_only" if mode == "index" else "available"


def _google_row(raw: dict[str, Any], *, account: dict[str, Any], fallback_parent: str = "") -> dict[str, Any]:
    item_id = _text(raw.get("id"), limit=1024)
    mime = _text(raw.get("mimeType"), limit=512)
    parents = raw.get("parents") if isinstance(raw.get("parents"), list) else []
    try:
        size = int(raw["size"]) if raw.get("size") not in {None, ""} else None
    except (TypeError, ValueError):
        size = None
    md5 = _text(raw.get("md5Checksum"), limit=256)
    return {
        "provider_item_id": item_id,
        "parent_item_id": _text(parents[0] if parents else fallback_parent, limit=1024),
        "account_id": _text(account.get("id"), limit=256),
        "name": _text(raw.get("name"), limit=4096) or "Untitled",
        "kind": "folder" if mime == "application/vnd.google-apps.folder" else "file",
        "path": "",
        "metadata_visible": True,
        "content_access": _content_access(account),
        "modified_at": _text(raw.get("modifiedTime"), limit=128),
        "mime_type": mime,
        "size_bytes": size,
        "version_id": _text(raw.get("version"), limit=512),
        "content_hash": f"md5:{md5}" if md5 else "",
    }


def _dropbox_row(raw: dict[str, Any], *, account: dict[str, Any], parent_id: str = "") -> dict[str, Any]:
    tag = _text(raw.get(".tag"), limit=32).lower()
    content_hash = _text(raw.get("content_hash"), limit=256)
    return {
        "provider_item_id": _text(raw.get("id"), limit=1024),
        "parent_item_id": _text(parent_id, limit=1024),
        "account_id": _text(account.get("id"), limit=256),
        "name": _text(raw.get("name"), limit=4096) or "Untitled",
        "kind": "folder" if tag == "folder" else "file",
        "path": _text(raw.get("path_display") or raw.get("path_lower"), limit=8192),
        "metadata_visible": True,
        "content_access": _content_access(account),
        "modified_at": _text(raw.get("server_modified"), limit=128),
        "mime_type": "",
        "size_bytes": int(raw.get("size")) if str(raw.get("size") or "").isdigit() else None,
        "version_id": _text(raw.get("rev"), limit=512),
        "content_hash": f"dropbox:{content_hash}" if content_hash else "",
    }


def _google_page(
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
            "fields": (
                "nextPageToken,"
                "files(id,name,mimeType,parents,size,modifiedTime,md5Checksum,version)"
            ),
        },
    )
    account_id = _text(account.get("id"), limit=256)
    items: list[dict[str, Any]] = []
    for raw in payload.get("files") or []:
        if not isinstance(raw, dict) or not _text(raw.get("id"), limit=1024):
            continue
        row = _google_row(raw, account=account, fallback_parent=parent)
        logical_id = identities.get(("google_drive", account_id, row["provider_item_id"]))
        if logical_id:
            row["logical_asset_id"] = logical_id
        items.append(row)
    next_cursor = _text(payload.get("nextPageToken"), limit=_MAX_CURSOR_BYTES)
    return {"items": items, "next_cursor": next_cursor, "has_more": bool(next_cursor)}


def _dropbox_parent_path(parent_id: str) -> str:
    """Dropbox IDs already include ``id:``; never double-prefix them."""
    parent = _text(parent_id, limit=1024)
    if not parent:
        return ""
    return parent if parent.startswith("id:") else f"id:{parent}"


def _dropbox_page(
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
        payload = _request_json(
            "https://api.dropboxapi.com/2/files/list_folder",
            method="POST",
            headers=headers,
            json_body={
                "path": _dropbox_parent_path(parent_id),
                "recursive": False,
                "include_deleted": False,
                "include_mounted_folders": True,
                "limit": limit,
            },
        )
    account_id = _text(account.get("id"), limit=256)
    items: list[dict[str, Any]] = []
    for raw in payload.get("entries") or []:
        if not isinstance(raw, dict) or not _text(raw.get("id"), limit=1024):
            continue
        row = _dropbox_row(raw, account=account, parent_id=parent_id)
        logical_id = identities.get(("dropbox", account_id, row["provider_item_id"]))
        if logical_id:
            row["logical_asset_id"] = logical_id
        items.append(row)
    next_cursor = _text(payload.get("cursor"), limit=_MAX_CURSOR_BYTES) if payload.get("has_more") else ""
    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": bool(payload.get("has_more") and next_cursor),
    }


def _identity_authority(
    repo_root: Path,
    *,
    registry_path: Path | None,
    provider: str,
    account_id: str,
    principal: DeskPrincipal,
) -> dict[tuple[str, str, str], str]:
    if registry_path is None:
        return {}
    key = _provider_key(provider)
    wanted_account = _text(account_id, limit=256)
    identities = provider_holding_identity_index(
        repo_root,
        registry_path=registry_path,
        provider=key,
        account_id=wanted_account,
        principal=principal,
    )
    # Read legacy explicit registry holdings only for this exact principal-owned
    # account. They remain a backwards-compatible seed, never a provider/path
    # heuristic and never override a conflicting private binding.
    for legacy_key, logical_id in _holding_identity_index(registry_path).items():
        if legacy_key[0] != key or legacy_key[1] != wanted_account:
            continue
        if legacy_key in identities and identities[legacy_key] != logical_id:
            identities.pop(legacy_key, None)
            continue
        identities.setdefault(legacy_key, logical_id)
    return identities


def list_provider_directory_runtime(
    repo_root: Path,
    *,
    provider: str,
    account_id: str = "",
    parent_id: str = "",
    cursor: str = "",
    limit: int = 50,
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
    resolved_account_id = _text(account.get("id"), limit=256)
    identities = _identity_authority(
        repo_root,
        registry_path=registry_path,
        provider=key,
        account_id=resolved_account_id,
        principal=actor,
    )
    page_size = _safe_limit(limit)
    parent = _text(parent_id, limit=1024)
    page_cursor = _text(cursor, limit=_MAX_CURSOR_BYTES)

    def operation(token: str) -> dict[str, Any]:
        adapter = _google_page if key == "google_drive" else _dropbox_page
        return adapter(
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
    if registry_path is not None:
        refresh_bound_holding_observations(
            repo_root,
            provider=key,
            account_id=resolved_account_id,
            items=page.get("items") or [],
            principal=actor,
        )
    return {
        "provider": key,
        "account_id": resolved_account_id,
        "parent_id": parent,
        "items": page.get("items") or [],
        "next_cursor": _text(page.get("next_cursor"), limit=_MAX_CURSOR_BYTES),
        "has_more": bool(page.get("has_more")),
        "page_size": page_size,
    }


def _google_item(token: str, account: dict[str, Any], provider_item_id: str) -> dict[str, Any]:
    item_id = _text(provider_item_id, limit=1024)
    payload = _request_json(
        f"https://www.googleapis.com/drive/v3/files/{urllib.parse.quote(item_id, safe='')}",
        headers={"Authorization": f"Bearer {token}"},
        query={
            "supportsAllDrives": "true",
            "fields": "id,name,mimeType,parents,size,modifiedTime,md5Checksum,version,trashed",
        },
    )
    if payload.get("trashed") is True or _text(payload.get("id"), limit=1024) != item_id:
        raise ValueError("Google Drive item is unavailable")
    return _google_row(payload, account=account)


def _dropbox_item(token: str, account: dict[str, Any], provider_item_id: str) -> dict[str, Any]:
    item_id = _text(provider_item_id, limit=1024)
    payload = _request_json(
        "https://api.dropboxapi.com/2/files/get_metadata",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"path": _dropbox_parent_path(item_id), "include_deleted": False},
    )
    if _text(payload.get("id"), limit=1024) != item_id:
        raise ValueError("Dropbox item is unavailable")
    return _dropbox_row(payload, account=account)


def inspect_provider_item_runtime(
    repo_root: Path,
    *,
    provider: str,
    account_id: str,
    provider_item_id: str,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    key = _provider_key(provider)
    item_id = _text(provider_item_id, limit=1024)
    if not item_id:
        raise ValueError("provider_item_id is required")
    actor, account = _selected_account(
        repo_root,
        provider=key,
        account_id=account_id,
        principal=principal,
    )

    def operation(token: str) -> dict[str, Any]:
        if key == "google_drive":
            return _google_item(token, account, item_id)
        return _dropbox_item(token, account, item_id)

    return _with_auth_retry(
        repo_root,
        actor=actor,
        account=account,
        provider=key,
        operation=operation,
    )


def persist_canonical_library_usage_event(
    repo_root: Path,
    event: dict[str, Any],
    *,
    registry_path: Path,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    logical_id = _text(event.get("logical_asset_id") if isinstance(event, dict) else "", limit=512)
    if not logical_id or logical_id not in _canonical_logical_ids(registry_path):
        raise ValueError("logical_asset_id is not a canonical Library asset")
    return persist_library_usage_event(repo_root, event, principal=principal)
