"""Durable Discover connector and incremental-sync state."""
from __future__ import annotations

from typing import Any, Mapping

from ._interop_common import dumps, loads, now_utc

ACCESS = {"available", "credential_required", "rate_limited", "unavailable", "unknown"}
SYNC = {"incremental", "snapshot", "stream", "unknown"}


def _access(value: Any, credential_required: bool = False) -> str:
    if credential_required:
        return "credential_required"
    raw = str(value or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in ACCESS:
        return raw
    if raw in {"public", "configured", "ready", "reachable", "ok"}:
        return "available"
    if raw in {"needs_auth", "required_auth", "unauthorized"}:
        return "credential_required"
    if raw in {"quota_exceeded", "throttled"}:
        return "rate_limited"
    if raw in {"blocked", "forbidden", "offline"}:
        return "unavailable"
    return "unknown"


def _sync(value: Any, cursor_field: str | None = None) -> str:
    raw = str(value or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
    if cursor_field or raw in {"incremental", "cursor", "cdc"}:
        return "incremental"
    if raw in {"snapshot", "full", "batch"}:
        return "snapshot"
    if raw in {"stream", "continuous"}:
        return "stream"
    return "unknown"


def _fields(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        return [str(key) for key in value]
    result: list[str] = []
    for field in value or []:
        name = field if isinstance(field, str) else field.get("name") or field.get("field") if isinstance(field, Mapping) else None
        if name and str(name) not in result:
            result.append(str(name))
    return result


class ConnectorMixin:
    def _init_connectors(self) -> None:
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS connectors(
          connector_id TEXT PRIMARY KEY,source_id TEXT,name TEXT,endpoint TEXT,access_state TEXT NOT NULL,
          credential_required INTEGER NOT NULL,credential_profile TEXT,license TEXT,terms_url TEXT,
          sync_mode TEXT NOT NULL,cursor_field TEXT,state_token TEXT,refresh_policy TEXT,last_synced_at TEXT,
          schema_fields TEXT NOT NULL,primary_key TEXT NOT NULL,rate_limit TEXT,quota_remaining REAL,
          estimated_bytes INTEGER,max_retries INTEGER,probe_required INTEGER NOT NULL,retryable INTEGER NOT NULL,
          supported INTEGER NOT NULL,updated_at TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_connector_source ON connectors(source_id) WHERE source_id IS NOT NULL;
        """)

    def upsert_connector(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        connector = payload.get("connector") if isinstance(payload.get("connector"), Mapping) else {}
        connector_id = str(payload.get("connector_id") or payload.get("desk_connector_id") or connector.get("id") or "").strip()
        source_id = str(payload.get("source_id") or connector.get("source_id") or connector_id).strip()
        if not connector_id:
            raise ValueError("connector_id is required")
        credential_required = bool(payload.get("credential_required") or connector.get("credential_required"))
        access_state = _access(
            connector.get("access_state") or connector.get("status") or payload.get("access_state")
            or payload.get("access") or payload.get("availability"),
            credential_required,
        )
        cursor_field = connector.get("cursor_field") or payload.get("cursor_field")
        sync_mode = _sync(connector.get("sync_mode") or payload.get("sync_mode") or payload.get("refresh_mode"), cursor_field)
        schema = connector.get("schema") or payload.get("schema") or payload.get("fields") or []
        if isinstance(schema, Mapping) and "fields" in schema:
            schema = schema["fields"]
        schema_fields = _fields(schema)
        primary_key = connector.get("primary_key") or payload.get("primary_key") or []
        primary_key = [str(value) for value in (primary_key if isinstance(primary_key, list) else [primary_key]) if value]
        retryable = bool(connector.get("retryable") or payload.get("retryable") or access_state == "rate_limited")
        supported = access_state != "unavailable"
        probe_required = bool(connector.get("probe_required") or payload.get("probe_required") or access_state == "unknown")
        at = str(payload.get("updated_at") or now_utc())
        values = (
            connector_id, source_id or None, connector.get("name") or payload.get("source_name") or payload.get("provider"),
            connector.get("endpoint") or connector.get("url") or payload.get("endpoint") or payload.get("url"),
            access_state, int(credential_required), connector.get("credential_profile") or payload.get("credential_profile"),
            connector.get("license") or payload.get("license"), connector.get("terms_url") or payload.get("terms_url"),
            sync_mode, cursor_field, connector.get("state_token") or connector.get("cursor") or payload.get("state_token"),
            connector.get("refresh_policy") or payload.get("refresh_policy"),
            connector.get("last_synced_at") or payload.get("last_synced_at"), dumps(schema_fields), dumps(primary_key),
            connector.get("rate_limit") or payload.get("rate_limit"),
            connector.get("quota_remaining") if connector.get("quota_remaining") is not None else payload.get("quota_remaining"),
            connector.get("estimated_bytes") or payload.get("estimated_bytes") or payload.get("size_bytes"),
            connector.get("max_retries") or payload.get("max_retries"), int(probe_required), int(retryable), int(supported), at,
        )
        self.db.execute("""INSERT INTO connectors VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(connector_id) DO UPDATE SET source_id=excluded.source_id,name=excluded.name,endpoint=excluded.endpoint,
          access_state=excluded.access_state,credential_required=excluded.credential_required,
          credential_profile=excluded.credential_profile,license=excluded.license,terms_url=excluded.terms_url,
          sync_mode=excluded.sync_mode,cursor_field=excluded.cursor_field,state_token=excluded.state_token,
          refresh_policy=excluded.refresh_policy,last_synced_at=excluded.last_synced_at,schema_fields=excluded.schema_fields,
          primary_key=excluded.primary_key,rate_limit=excluded.rate_limit,quota_remaining=excluded.quota_remaining,
          estimated_bytes=excluded.estimated_bytes,max_retries=excluded.max_retries,probe_required=excluded.probe_required,
          retryable=excluded.retryable,supported=excluded.supported,updated_at=excluded.updated_at""", values)
        return self.connector(connector_id)

    def connector(self, connector_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM connectors WHERE connector_id=? OR source_id=?", (connector_id, connector_id)
        ).fetchone()
        if row is None:
            raise KeyError(connector_id)
        return {
            "connector_id": row["connector_id"], "source_id": row["source_id"], "source_name": row["name"],
            "endpoint": row["endpoint"], "access_state": row["access_state"],
            "credential_required": bool(row["credential_required"]), "credential_profile": row["credential_profile"],
            "license": row["license"], "terms_url": row["terms_url"], "sync_mode": row["sync_mode"],
            "cursor_field": row["cursor_field"], "state_token": row["state_token"],
            "refresh_policy": row["refresh_policy"], "last_synced_at": row["last_synced_at"],
            "schema_discovered": bool(loads(row["schema_fields"], [])), "schema_fields": loads(row["schema_fields"], []),
            "primary_key": loads(row["primary_key"], []), "rate_limit": row["rate_limit"],
            "quota_remaining": row["quota_remaining"], "estimated_bytes": row["estimated_bytes"],
            "max_retries": row["max_retries"], "probe_required": bool(row["probe_required"]),
            "retryable": bool(row["retryable"]), "supported": bool(row["supported"]), "updated_at": row["updated_at"],
        }

    def record_probe(self, connector_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
        current = self.connector(connector_id)
        return self.upsert_connector({
            **current,
            "access_state": result.get("access_state") or result.get("status") or current["access_state"],
            "credential_required": result.get("credential_required", current["credential_required"]),
            "schema": result.get("schema") or result.get("fields") or current["schema_fields"],
            "primary_key": result.get("primary_key") or current["primary_key"],
            "estimated_bytes": result.get("estimated_bytes", current["estimated_bytes"]),
            "probe_required": False,
            "updated_at": result.get("timestamp") or result.get("updated_at") or now_utc(),
        })

    def record_sync(self, connector_id: str, *, state_token: str | None = None,
                    last_synced_at: str | None = None, quota_remaining: float | None = None) -> dict[str, Any]:
        current = self.connector(connector_id)
        return self.upsert_connector({
            **current, "state_token": state_token or current["state_token"],
            "last_synced_at": last_synced_at or now_utc(),
            "quota_remaining": quota_remaining if quota_remaining is not None else current["quota_remaining"],
        })

    def list_connectors(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT connector_id FROM connectors ORDER BY source_id,connector_id").fetchall()
        return [self.connector(row["connector_id"]) for row in rows]
