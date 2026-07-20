#!/usr/bin/env python3
"""Append-only faculty activity log — browse, query, procure, jobs (not meter totals)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from sharpe_kernel.paths import repo_root_from_file


def log_path(repo_root: Path | None = None) -> Path:
    root = repo_root or repo_root_from_file(__file__)
    return root / "data_lake/procurement_memory/desk_activity.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_target(target: str) -> str:
    text = str(target)
    if text.startswith("[context:") and "]" in text:
        return text.split("]", 1)[1].strip()
    return text


def record_activity(
    action: str,
    target: str,
    *,
    repo_root: Path | None = None,
    session_id: str | None = None,
    bq_gib: float | None = None,
    tavily_calls: int | None = None,
    composer_turns: int | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one activity event. Cost fields are optional attribution for Spending drill-down."""
    path = log_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    cost: dict[str, Any] = {}
    if bq_gib:
        cost["bq_gib"] = round(float(bq_gib), 4)
    if tavily_calls:
        cost["tavily"] = int(tavily_calls)
    if composer_turns:
        cost["composer"] = int(composer_turns)

    event = {
        "id": uuid.uuid4().hex[:12],
        "ts": _utc_now(),
        "action": str(action),
        "target": _clean_target(str(target))[:500],
        "session_id": session_id,
        "cost": cost or None,
        "meta": meta or {},
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def _logged_events(*, limit: int, repo_root: Path) -> list[dict[str, Any]]:
    path = log_path(repo_root)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in reversed(lines[-max(limit * 2, 20) :]):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except Exception:
            continue
        if len(out) >= limit:
            break
    return out


def _registered_asset_events(repo_root: Path, *, limit: int) -> list[dict[str, Any]]:
    """Project verified receipts into Resources without writing duplicate log rows."""
    try:
        from scripts.research_data_mcp.registered_asset_authority import list_verified_registration_receipts

        receipts = list_verified_registration_receipts(repo_root, limit=max(limit, 50))
    except Exception:
        return []

    events: list[dict[str, Any]] = []
    for receipt in receipts[:limit]:
        dataset_id = str(receipt.get("dataset_id") or "").strip()
        job_id = str(receipt.get("job_id") or "").strip()
        if not dataset_id or not job_id:
            continue
        name = str(receipt.get("name") or dataset_id).strip()
        events.append(
            {
                "id": f"registered-{job_id}",
                "ts": receipt.get("updated_at") or receipt.get("created_at") or "",
                "action": "Registered",
                "target": f"Registered · {name}",
                "session_id": None,
                "cost": None,
                "meta": {
                    "action": "Registered Library asset",
                    "dataset_id": dataset_id,
                    "registry_id": receipt.get("registry_id") or dataset_id,
                    "manifest_id": receipt.get("manifest_id"),
                    "job_id": job_id,
                    "readiness": receipt.get("analysis_readiness"),
                    "archive_verified": receipt.get("archive_verified") is True,
                    "registry_readback": receipt.get("registry_readback") is True,
                    "lifecycle": receipt.get("lifecycle") or receipt.get("analysis_readiness"),
                    "vault_path": receipt.get("vault_path"),
                    "catalog_reconciliation": receipt.get("catalog_reconciliation") or {},
                },
            }
        )
    return events


def read_recent(*, limit: int = 50, repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Return append-only activity plus verified registered-asset outcomes.

    Registered outcomes are a read-only projection of durable receipts, not new
    activity-log writes.  They are deduplicated by event ID and sorted with the
    ordinary feed so Resources can resolve the same job/dataset through the live
    identity endpoint.
    """
    root = (repo_root or repo_root_from_file(__file__)).resolve()
    bounded = max(1, min(int(limit or 50), 500))
    rows = [
        *_logged_events(limit=bounded, repo_root=root),
        *_registered_asset_events(root, limit=bounded),
    ]
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: str(item.get("ts") or ""), reverse=True):
        event_id = str(row.get("id") or "")
        if event_id and event_id in seen:
            continue
        if event_id:
            seen.add(event_id)
        merged.append(row)
        if len(merged) >= bounded:
            break
    return merged


def top_bq_drivers(*, limit: int = 5, repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Sum BQ GiB by target from recent activity."""
    totals: dict[str, float] = {}
    for ev in read_recent(limit=200, repo_root=repo_root):
        cost = ev.get("cost") or {}
        gib = cost.get("bq_gib")
        if not gib:
            continue
        key = str(ev.get("target") or "unknown")
        totals[key] = totals.get(key, 0.0) + float(gib)
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    return [{"target": t, "bq_gib": round(g, 4)} for t, g in ranked[:limit]]
