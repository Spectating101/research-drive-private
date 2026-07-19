#!/usr/bin/env python3
"""Interval scheduler for recurring YZU jobs."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator import YzuOrchestrator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    def schedules(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        state = self._read_state()
        for item in self.cfg.get("schedules", []):
            last = (state.get("runs") or {}).get(item["id"], {})
            rows.append(
                {
                    "id": item["id"],
                    "enabled": bool(item.get("enabled", True)),
                    "interval_hours": float(item.get("interval_hours", 24)),
                    "title": item.get("plan", {}).get("title", item["id"]),
                    "job_type": item.get("plan", {}).get("job_type"),
                    "last_run_at": last.get("at"),
                    "last_job_id": last.get("job_id"),
                    "last_status": last.get("status"),
                }
            )
        return rows

    def tick(self, orchestrator: YzuOrchestrator) -> dict[str, Any] | None:
        state = self._read_state()
        runs = state.setdefault("runs", {})
        now_ts = time.time()
        for item in self.cfg.get("schedules", []):
            if not item.get("enabled", True):
                continue
            sid = item["id"]
            interval_s = float(item.get("interval_hours", 24)) * 3600
            last = runs.get(sid, {})
            last_ts = float(last.get("ts_unix", 0))
            if now_ts - last_ts < interval_s:
                continue
            plan = dict(item.get("plan") or {})
            plan.setdefault("launchable", True)
            title = plan.get("title") or f"Scheduled {sid}"
            job = orchestrator.submit(title, plan, {"schedule_id": sid}, auto_approve=bool(item.get("auto_approve", True)))
            runs[sid] = {"ts_unix": now_ts, "at": _now(), "job_id": job["id"], "status": job["status"]}
            self._write_state(state)
            return {"schedule_id": sid, "job": job}
        return None
