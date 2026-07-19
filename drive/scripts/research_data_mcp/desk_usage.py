#!/usr/bin/env python3
"""Append-only daily counters for desk consumption (Tavily, BQ bytes, Composer turns)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from sharpe_kernel.paths import repo_root_from_file


def repo_root_default() -> Path:
    return repo_root_from_file(__file__)


def ledger_path(repo_root: Path | None = None) -> Path:
    root = repo_root or repo_root_default()
    return root / "data_lake/procurement_memory/desk_usage.json"


def _today_key() -> str:
    return date.today().isoformat()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_ledger(repo_root: Path | None = None) -> dict[str, Any]:
    path = ledger_path(repo_root)
    if not path.is_file():
        return {"version": 1, "days": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "days": {}}


def save_ledger(payload: dict[str, Any], repo_root: Path | None = None) -> None:
    path = ledger_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _empty_day() -> dict[str, int]:
    return {
        "tavily_calls": 0,
        "bq_bytes_billed": 0,
        "composer_turns": 0,
        "probe_calls": 0,
    }


def record_counter(name: str, amount: int = 1, *, repo_root: Path | None = None) -> dict[str, Any]:
    if amount <= 0:
        return today_summary(repo_root)
    store = load_ledger(repo_root)
    days: dict[str, Any] = store.setdefault("days", {})
    day = days.setdefault(_today_key(), _empty_day())
    if name not in day:
        day[name] = 0
    day[name] = int(day.get(name) or 0) + int(amount)
    store["updated_at"] = _utc_now()
    save_ledger(store, repo_root)
    return today_summary(repo_root)


def record_tavily_call(*, repo_root: Path | None = None) -> dict[str, Any]:
    return record_counter("tavily_calls", 1, repo_root=repo_root)


def record_bq_bytes(bytes_billed: int, *, repo_root: Path | None = None) -> dict[str, Any]:
    return record_counter("bq_bytes_billed", max(0, int(bytes_billed)), repo_root=repo_root)


def record_composer_turn(*, repo_root: Path | None = None) -> dict[str, Any]:
    return record_counter("composer_turns", 1, repo_root=repo_root)


def record_probe_call(*, repo_root: Path | None = None) -> dict[str, Any]:
    return record_counter("probe_calls", 1, repo_root=repo_root)


def today_summary(repo_root: Path | None = None) -> dict[str, Any]:
    store = load_ledger(repo_root)
    day = (store.get("days") or {}).get(_today_key()) or _empty_day()
    return _day_summary(_today_key(), day)


def _day_summary(date_key: str, day: dict[str, Any]) -> dict[str, Any]:
    bq_bytes = int(day.get("bq_bytes_billed") or 0)
    return {
        "date": date_key,
        "tavily_calls": int(day.get("tavily_calls") or 0),
        "bq_bytes_billed": bq_bytes,
        "bq_gib_billed": round(bq_bytes / 1024**3, 4) if bq_bytes else 0.0,
        "composer_turns": int(day.get("composer_turns") or 0),
        "probe_calls": int(day.get("probe_calls") or 0),
    }


def period_summary(*, days: int = 30, repo_root: Path | None = None) -> dict[str, Any]:
    """Roll up daily counters for Spending charts."""
    from datetime import timedelta

    store = load_ledger(repo_root)
    all_days: dict[str, Any] = store.get("days") or {}
    end = date.today()
    daily: list[dict[str, Any]] = []
    totals = _empty_day()
    for offset in range(days - 1, -1, -1):
        d = (end - timedelta(days=offset)).isoformat()
        raw = all_days.get(d) or _empty_day()
        row = _day_summary(d, raw)
        daily.append(row)
        for key in totals:
            totals[key] = int(totals.get(key) or 0) + int(raw.get(key) or 0)
    bq_bytes = int(totals.get("bq_bytes_billed") or 0)
    return {
        "days": days,
        "start": daily[0]["date"] if daily else _today_key(),
        "end": daily[-1]["date"] if daily else _today_key(),
        "daily": daily,
        "totals": {
            "tavily_calls": int(totals.get("tavily_calls") or 0),
            "bq_bytes_billed": bq_bytes,
            "bq_gib_billed": round(bq_bytes / 1024**3, 4) if bq_bytes else 0.0,
            "composer_turns": int(totals.get("composer_turns") or 0),
            "probe_calls": int(totals.get("probe_calls") or 0),
        },
    }
