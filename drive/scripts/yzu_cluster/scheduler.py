#!/usr/bin/env python3
"""Interval scheduler for recurring YZU jobs."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator import YzuOrchestrator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _period_bucket(ts: float, interval_hours: float) -> str:
    """Stable idempotency window for a schedule interval."""
    interval_s = max(float(interval_hours), 1.0 / 60.0) * 3600.0
    bucket = int(ts // interval_s)
    return f"{bucket}"


def _sanitize_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._:-]+", "-", value).strip("-")[:180]


class YzuScheduler:
    def __init__(self, repo_root: Path, cfg: dict[str, Any]):
        self.repo_root = repo_root
        self.cfg = cfg
        self.state_path = repo_root / cfg["controller"]["status_root"] / "scheduler_state.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"runs": {}}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"runs": {}}

    def _write_state(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _item(self, schedule_id: str) -> dict[str, Any]:
        for item in self.cfg.get("schedules", []):
            if item.get("id") == schedule_id:
                return item
        raise KeyError(schedule_id)

    def schedules(
        self,
        *,
        status_lookup: Callable[[str], str | None] | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        state = self._read_state()
        now_ts = time.time()
        for item in self.cfg.get("schedules", []):
            last = (state.get("runs") or {}).get(item["id"], {})
            interval_hours = float(item.get("interval_hours", 24))
            last_ts = float(last.get("ts_unix", 0) or 0)
            next_ts = (last_ts + interval_hours * 3600) if last_ts else now_ts
            last_status = last.get("status")
            if status_lookup and last.get("job_id"):
                try:
                    resolved_status = status_lookup(str(last["job_id"]))
                except Exception:  # noqa: BLE001
                    resolved_status = None
                if resolved_status:
                    last_status = resolved_status
            rows.append(
                {
                    "id": item["id"],
                    "enabled": bool(item.get("enabled", True)),
                    "interval_hours": interval_hours,
                    "title": item.get("plan", {}).get("title", item["id"]),
                    "job_type": item.get("plan", {}).get("job_type"),
                    "last_run_at": last.get("at"),
                    "last_job_id": last.get("job_id"),
                    "last_status": last_status,
                    "last_idempotency_key": last.get("idempotency_key"),
                    "next_run_at": datetime.fromtimestamp(next_ts, timezone.utc).isoformat(),
                    "due": bool(item.get("enabled", True)) and now_ts >= next_ts,
                }
            )
        return rows

    def build_emission(
        self,
        schedule_id: str,
        *,
        now_ts: float | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Build the durable emit contract without mutating state or submitting."""
        item = self._item(schedule_id)
        now = time.time() if now_ts is None else float(now_ts)
        interval_hours = float(item.get("interval_hours", 24))
        state = self._read_state()
        last = (state.get("runs") or {}).get(schedule_id, {})
        last_ts = float(last.get("ts_unix", 0) or 0)
        due = force or (bool(item.get("enabled", True)) and (now - last_ts >= interval_hours * 3600))
        plan = dict(item.get("plan") or {})
        plan.setdefault("launchable", True)
        title = plan.get("title") or f"Scheduled {schedule_id}"
        if force:
            # A manual run is an explicit retry/one-off and must be able to
            # recover a failed period without defeating automatic replay safety.
            bucket = f"manual-{int(now * 1000)}"
        else:
            bucket = _period_bucket(now if not last_ts else max(now, last_ts + 1), interval_hours)
        idempotency_key = _sanitize_key(f"sched:{schedule_id}:{bucket}")
        return {
            "schedule_id": schedule_id,
            "enabled": bool(item.get("enabled", True)),
            "due": due,
            "interval_hours": interval_hours,
            "title": title,
            "job_type": plan.get("job_type"),
            "plan": plan,
            "request": {
                "schedule_id": schedule_id,
                "idempotency_key": idempotency_key,
                "source": "yzu_scheduler",
                # Trusted controller path — never client-supplied ops_privileged.
                "_ops_internal": True,
            },
            "idempotency_key": idempotency_key,
            "auto_approve": bool(item.get("auto_approve", True)),
            "last_run_at": last.get("at"),
            "last_job_id": last.get("job_id"),
            "last_status": last.get("status"),
            "ownership": {
                "controller": (self.cfg.get("controller") or {}).get("hostname") or "optiplex",
                "emitter": "yzu_scheduler",
            },
        }

    def emit(
        self,
        orchestrator: YzuOrchestrator,
        schedule_id: str,
        *,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """Emit one schedule once. Replay with the same period key is idempotent."""
        emission = self.build_emission(schedule_id, force=force)
        if dry_run:
            return {**emission, "dry_run": True, "submitted": False}
        if not emission["due"] and not force:
            return {**emission, "submitted": False, "skipped_reason": "not_due"}
        job = orchestrator.submit(
            emission["title"],
            dict(emission["plan"]),
            dict(emission["request"]),
            auto_approve=bool(emission["auto_approve"]),
        )
        state = self._read_state()
        runs = state.setdefault("runs", {})
        runs[schedule_id] = {
            "ts_unix": time.time(),
            "at": _now(),
            "job_id": job["id"],
            "status": job["status"],
            "idempotency_key": emission["idempotency_key"],
        }
        self._write_state(state)
        return {
            **emission,
            "dry_run": False,
            "submitted": True,
            "job": job,
            "replay_safe": True,
        }

    def tick(self, orchestrator: YzuOrchestrator, *, dry_run: bool = False) -> dict[str, Any] | None:
        for item in self.cfg.get("schedules", []):
            if not item.get("enabled", True):
                continue
            sid = item["id"]
            emission = self.build_emission(sid)
            if not emission["due"]:
                continue
            return self.emit(orchestrator, sid, dry_run=dry_run, force=False)
        return None
