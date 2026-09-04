#!/usr/bin/env python3
"""Principal-local provider holding bindings for canonical Library assets.

Canonical research identity remains in the shared Library registry. A connected
storage holding is private to the principal who owns that provider account, so
provider/account/item bindings are persisted separately and never promoted into
the shared registry merely because a cloud account is connected.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from scripts.research_data_mcp.connected_accounts import (
    _principal_dir,
    _require_named_principal,
    list_connected_accounts,
)
from scripts.research_data_mcp.desk_principal import DeskPrincipal


def _text(value: Any, *, limit: int = 4096) -> str:
    return str(value or "").strip()[:limit]


def _provider_key(value: Any) -> str:
    return _text(value, limit=64).lower().replace("-", "_").replace(" ", "_")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _holdings_db_path(repo_root: Path, actor: DeskPrincipal) -> Path:
    return _principal_dir(repo_root, actor) / "library_federation_holdings.sqlite3"


@contextmanager
def _holdings_db(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute(
            """CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                account_id TEXT NOT NULL,
                provider_item_id TEXT NOT NULL,
                logical_asset_id TEXT NOT NULL,
                parent_item_id TEXT NOT NULL,
                path TEXT NOT NULL,
                version_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                content_access TEXT NOT NULL,
                created_at TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                UNIQUE(provider, account_id, provider_item_id)
            )"""
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_federation_holding_asset "
            "ON holdings(logical_asset_id, observed_at DESC)"
        )
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


def _account_for_principal(
    repo_root: Path,
    *,
    provider: str,
    account_id: str,
    principal: DeskPrincipal,
) -> dict[str, Any]:
    key = _provider_key(provider)
    wanted = _text(account_id, limit=256)
    row = next(
        (
            dict(item)
            for item in list_connected_accounts(repo_root, principal=principal)
            if _text(item.get("id"), limit=256) == wanted
            and _provider_key(item.get("provider")) == key
            and _text(item.get("status"), limit=32).lower()
            not in {"disconnected", "revoked", "expired", "error"}
        ),
        None,
    )
    if row is None:
        raise KeyError(wanted or f"{key}:missing-account")
    return row


def bind_provider_holding(
    repo_root: Path,
    *,
    registry_path: Path,
    provider: str,
    account_id: str,
    provider_item_id: str,
    logical_asset_id: str,
    observation: dict[str, Any] | None = None,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_named_principal(principal)
    key = _provider_key(provider)
    account = _account_for_principal(
        repo_root,
        provider=key,
        account_id=account_id,
        principal=actor,
    )
    item_id = _text(provider_item_id, limit=1024)
    logical_id = _text(logical_asset_id, limit=512)
    if not item_id:
        raise ValueError("provider_item_id is required")
    if not logical_id or logical_id not in _canonical_logical_ids(registry_path):
        raise ValueError("logical_asset_id is not a canonical Library asset")

    observed = dict(observation or {})
    observed_item = _text(observed.get("provider_item_id"), limit=1024)
    observed_account = _text(observed.get("account_id"), limit=256)
    if observed_item and observed_item != item_id:
        raise ValueError("Provider observation does not match provider_item_id")
    if observed_account and observed_account != _text(account.get("id"), limit=256):
        raise ValueError("Provider observation does not match account_id")
    if _text(observed.get("kind"), limit=32).lower() == "folder":
        raise ValueError("Folders cannot be bound as Library evidence holdings")

    now = _utc_now()
    path = _holdings_db_path(repo_root, actor)
    with _holdings_db(path) as db:
        existing = db.execute(
            "SELECT * FROM holdings WHERE provider = ? AND account_id = ? AND provider_item_id = ?",
            (key, _text(account.get("id"), limit=256), item_id),
        ).fetchone()
        if existing is not None and str(existing["logical_asset_id"]) != logical_id:
            raise ValueError("Provider holding is already bound to a different canonical Library asset")
        created_at = str(existing["created_at"]) if existing is not None else now
        values = (
            key,
            _text(account.get("id"), limit=256),
            item_id,
            logical_id,
            _text(observed.get("parent_item_id"), limit=1024),
            _text(observed.get("path"), limit=8192),
            _text(observed.get("version_id"), limit=512),
            _text(observed.get("content_hash"), limit=512),
            _text(observed.get("content_access"), limit=64),
            created_at,
            now,
        )
        db.execute(
            """INSERT INTO holdings(
                provider, account_id, provider_item_id, logical_asset_id,
                parent_item_id, path, version_id, content_hash, content_access,
                created_at, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, account_id, provider_item_id) DO UPDATE SET
                logical_asset_id = excluded.logical_asset_id,
                parent_item_id = excluded.parent_item_id,
                path = excluded.path,
                version_id = excluded.version_id,
                content_hash = excluded.content_hash,
                content_access = excluded.content_access,
                observed_at = excluded.observed_at""",
            values,
        )
        row = db.execute(
            "SELECT * FROM holdings WHERE provider = ? AND account_id = ? AND provider_item_id = ?",
            (key, _text(account.get("id"), limit=256), item_id),
        ).fetchone()
    return _public_row(row)


def unbind_provider_holding(
    repo_root: Path,
    *,
    provider: str,
    account_id: str,
    provider_item_id: str,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_named_principal(principal)
    key = _provider_key(provider)
    account = _account_for_principal(
        repo_root,
        provider=key,
        account_id=account_id,
        principal=actor,
    )
    item_id = _text(provider_item_id, limit=1024)
    if not item_id:
        raise ValueError("provider_item_id is required")
    path = _holdings_db_path(repo_root, actor)
    if not path.is_file():
        return {"ok": True, "removed": False}
    with _holdings_db(path) as db:
        cursor = db.execute(
            "DELETE FROM holdings WHERE provider = ? AND account_id = ? AND provider_item_id = ?",
            (key, _text(account.get("id"), limit=256), item_id),
        )
        removed = cursor.rowcount > 0
    return {"ok": True, "removed": removed}


def _public_row(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "holding_id": int(row["id"]),
        "provider": str(row["provider"]),
        "account_id": str(row["account_id"]),
        "provider_item_id": str(row["provider_item_id"]),
        "logical_asset_id": str(row["logical_asset_id"]),
        "parent_item_id": str(row["parent_item_id"]),
        "path": str(row["path"]),
        "version_id": str(row["version_id"]),
        "content_hash": str(row["content_hash"]),
        "content_access": str(row["content_access"]),
        "created_at": str(row["created_at"]),
        "observed_at": str(row["observed_at"]),
    }


def list_provider_holdings(
    repo_root: Path,
    *,
    registry_path: Path,
    provider: str = "",
    account_id: str = "",
    logical_asset_id: str = "",
    limit: int = 200,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_named_principal(principal)
    path = _holdings_db_path(repo_root, actor)
    if not path.is_file():
        return {"holdings": [], "count": 0}
    canonical = _canonical_logical_ids(registry_path)
    clauses: list[str] = []
    params: list[Any] = []
    if provider:
        clauses.append("provider = ?")
        params.append(_provider_key(provider))
    if account_id:
        clauses.append("account_id = ?")
        params.append(_text(account_id, limit=256))
    if logical_asset_id:
        clauses.append("logical_asset_id = ?")
        params.append(_text(logical_asset_id, limit=512))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    try:
        safe_limit = max(1, min(500, int(limit or 200)))
    except (TypeError, ValueError):
        safe_limit = 200
    params.append(safe_limit)
    with _holdings_db(path) as db:
        rows = db.execute(
            f"SELECT * FROM holdings{where} ORDER BY observed_at DESC, id DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    holdings = [_public_row(row) for row in rows if str(row["logical_asset_id"]) in canonical]
    return {"holdings": holdings, "count": len(holdings)}


def provider_holding_identity_index(
    repo_root: Path,
    *,
    registry_path: Path,
    provider: str,
    account_id: str,
    principal: DeskPrincipal | None = None,
) -> dict[tuple[str, str, str], str]:
    actor = _require_named_principal(principal)
    document = list_provider_holdings(
        repo_root,
        registry_path=registry_path,
        provider=provider,
        account_id=account_id,
        limit=500,
        principal=actor,
    )
    return {
        (
            _provider_key(row.get("provider")),
            _text(row.get("account_id"), limit=256),
            _text(row.get("provider_item_id"), limit=1024),
        ): _text(row.get("logical_asset_id"), limit=512)
        for row in document["holdings"]
    }


def refresh_bound_holding_observations(
    repo_root: Path,
    *,
    provider: str,
    account_id: str,
    items: list[dict[str, Any]],
    principal: DeskPrincipal | None = None,
) -> None:
    actor = _require_named_principal(principal)
    path = _holdings_db_path(repo_root, actor)
    if not path.is_file() or not items:
        return
    key = _provider_key(provider)
    wanted_account = _text(account_id, limit=256)
    now = _utc_now()
    with _holdings_db(path) as db:
        for item in items:
            if not isinstance(item, dict) or _text(item.get("kind"), limit=32) == "folder":
                continue
            item_id = _text(item.get("provider_item_id"), limit=1024)
            if not item_id:
                continue
            db.execute(
                """UPDATE holdings SET
                    parent_item_id = ?, path = ?, version_id = ?, content_hash = ?,
                    content_access = ?, observed_at = ?
                   WHERE provider = ? AND account_id = ? AND provider_item_id = ?""",
                (
                    _text(item.get("parent_item_id"), limit=1024),
                    _text(item.get("path"), limit=8192),
                    _text(item.get("version_id"), limit=512),
                    _text(item.get("content_hash"), limit=512),
                    _text(item.get("content_access"), limit=64),
                    now,
                    key,
                    wanted_account,
                    item_id,
                ),
            )
