#!/usr/bin/env python3
"""Canonical runtime adapters for Library federation.

This layer owns provider-native page semantics and the last ontology checks before
HTTP exposure. The lower-level federation module retains account/auth/storage
primitives; this module keeps provider quirks out of the generic authority.
"""

from __future__ import annotations

import json
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
from scripts.research_data_mcp.desk_principal import DeskPrincipal

_MAX_CURSOR_BYTES = 16_384


def _content_access(account: dict[str, Any]) -> str:
    mode = _text(account.get("access_mode"), limit=32).lower()
    return "metadata_only" if mode == "index" else "available"


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
        md5 = _text(raw.get("md5Checksum"), limit=256)
        row: dict[str, Any] = {
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
            "version_id": _text(raw.get("version"), limit=512),
            "content_hash": f"md5:{md5}" if md5 else "",
        }
        logical_id = identities.get(("google_drive", account_id, item_id))
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
        if not isinstance(raw, dict):
            continue
        item_id = _text(raw.get("id"), limit=1024)
        if not item_id:
            continue
        tag = _text(raw.get(".tag"), limit=32).lower()
        content_hash = _text(raw.get("content_hash"), limit=256)
        row: dict[str, Any] = {
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
            "version_id": _text(raw.get("rev"), limit=512),
            "content_hash": f"dropbox:{content_hash}" if content_hash else "",
        }
        logical_id = identities.get(("dropbox", account_id, item_id))
        if logical_id:
            row["logical_asset_id"] = logical_id
        items.append(row)
    next_cursor = _text(payload.get("cursor"), limit=_MAX_CURSOR_BYTES) if payload.get("has_more") else ""
    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": bool(payload.get("has_more") and next_cursor),
    }


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
    identities = _holding_identity_index(registry_path)
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
    return {
        "provider": key,
        "account_id": _text(account.get("id"), limit=256),
        "parent_id": parent,
        "items": page.get("items") or [],
        "next_cursor": _text(page.get("next_cursor"), limit=_MAX_CURSOR_BYTES),
        "has_more": bool(page.get("has_more")),
        "page_size": page_size,
    }


def _canonical_logical_ids(registry_path: Path) -> set[str]:
    try:
        document = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    rows = document.get("datasets") if isinstance(document, dict) else []
    return {
        logical_id
        for row in rows or []
        if isinstance(row, dict)
        and (
            logical_id := _text(
                row.get("logical_asset_id") or row.get("dataset_id") or row.get("registry_id"),
                limit=512,
            )
        )
    }


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
