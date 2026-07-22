from __future__ import annotations

import json
from pathlib import Path

from scripts.yzu_cluster.scheduler import YzuScheduler


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def submit(self, title: str, plan: dict, request: dict, *, auto_approve: bool) -> dict:
        self.calls.append({"title": title, "plan": plan, "request": request, "auto_approve": auto_approve})
        return {"id": request["idempotency_key"], "status": "queued"}


def _scheduler(tmp_path: Path) -> YzuScheduler:
    cfg = {
        "controller": {"status_root": "status"},
        "schedules": [
            {
                "id": "tiny-refresh",
                "enabled": True,
                "interval_hours": 24,
                "auto_approve": True,
                "plan": {"title": "Tiny refresh", "job_type": "http_manifest", "url": "https://example.test"},
            }
        ],
    }
    return YzuScheduler(tmp_path, cfg)


def test_schedule_dry_run_exposes_owned_idempotent_emission(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)
    out = scheduler.emit(_FakeOrchestrator(), "tiny-refresh", dry_run=True)

    assert out["dry_run"] is True
    assert out["submitted"] is False
    assert out["schedule_id"] == "tiny-refresh"
    assert out["job_type"] == "http_manifest"
    assert out["idempotency_key"].startswith("sched:tiny-refresh:")
    assert out["ownership"]["emitter"] == "yzu_scheduler"


def test_schedule_emits_once_per_interval_and_persists_next_run(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)
    fake = _FakeOrchestrator()

    first = scheduler.emit(fake, "tiny-refresh")
    replay = scheduler.emit(fake, "tiny-refresh")
    state = json.loads((tmp_path / "status/scheduler_state.json").read_text(encoding="utf-8"))
    listed = scheduler.schedules()[0]

    assert first["submitted"] is True
    assert replay["submitted"] is False
    assert replay["skipped_reason"] == "not_due"
    assert len(fake.calls) == 1
    assert state["runs"]["tiny-refresh"]["idempotency_key"] == first["idempotency_key"]
    assert listed["last_job_id"] == first["idempotency_key"]
    assert listed["next_run_at"]


def test_disabled_schedule_is_not_due(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.cfg["schedules"][0]["enabled"] = False

    out = scheduler.build_emission("tiny-refresh")

    assert out["enabled"] is False
    assert out["due"] is False
