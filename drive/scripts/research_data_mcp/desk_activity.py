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


def read_recent(*, limit: int = 50, repo_root: Path | None = None) -> list[dict[str, Any]]:
    path = log_path(repo_root)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in reversed(lines[-limit * 2 :]):
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
