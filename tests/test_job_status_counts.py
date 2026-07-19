"""Job store status_counts — lifetime vs actionable windows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.yzu_cluster.jobs import YzuJobStore


def _stamp(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_status_counts_separates_lifetime_from_recent(tmp_path: Path) -> None:
    store = YzuJobStore(tmp_path / "jobs.sqlite3")
    store.create("pending now", {}, {"job_type": "scraper_run"}, status="pending_approval")
    store.create("done", {}, {"job_type": "http_manifest"}, status="completed")

    old_fail = store.create("old fail", {}, {"job_type": "scraper_run"}, status="queued")
    store.update(old_fail["id"], "failed", error="ancient")
    with store._db() as db:
        db.execute(
            "UPDATE jobs SET updated_at=? WHERE id=?",
            (_stamp(20), old_fail["id"]),
        )

    recent_fail = store.create("recent fail", {}, {"job_type": "scraper_run"}, status="queued")
    store.update(recent_fail["id"], "failed", error="yesterday")
    with store._db() as db:
        db.execute(
            "UPDATE jobs SET updated_at=? WHERE id=?",
            (_stamp(1), recent_fail["id"]),
        )

    old_cancel = store.create("old cancel", {}, {"job_type": "scraper_run"}, status="queued")
    store.update(old_cancel["id"], "cancelled")
    with store._db() as db:
        db.execute(
            "UPDATE jobs SET updated_at=? WHERE id=?",
            (_stamp(14), old_cancel["id"]),
        )

    counts = store.status_counts(recent_days=7)
    assert counts["pending_approval"] == 1
    assert counts["completed"] == 1
    assert counts["failed"] == 2  # lifetime
    assert counts["cancelled"] == 1  # lifetime
    assert counts["failed_recent"] == 1
    assert counts["cancelled_recent"] == 0
    assert counts["actionable"]["pending_approval"] == 1
    assert counts["actionable"]["failed_recent"] == 1
    assert counts["actionable"]["running"] == 0
    assert "lifetime" in counts
    assert "semantics" in counts
    assert counts["total"] == 5


def test_orchestrator_stats_delegates_to_store(tmp_path: Path) -> None:
    """stats() must use SQL status_counts, not a truncated list() scan."""
    from scripts.yzu_cluster.orchestrator import YzuOrchestrator

    store = YzuJobStore(tmp_path / "jobs.sqlite3")
    for i in range(3):
        store.create(f"p{i}", {}, {"job_type": "scraper_run"}, status="pending_approval")

    orch = object.__new__(YzuOrchestrator)
    orch.store = store
    stats = YzuOrchestrator.stats(orch)
    assert stats["pending_approval"] == 3
    assert stats["failed_recent"] == 0
    assert stats["actionable"]["pending_approval"] == 3
