"""Regression: store helpers must not leak SQLite FDs on Python 3.12+."""

from __future__ import annotations

from pathlib import Path

from scripts.yzu_cluster.jobs import YzuJobStore


def test_job_store_closes_connections(tmp_path: Path) -> None:
    store = YzuJobStore(tmp_path / "jobs.sqlite3")
    for i in range(200):
        store.create(f"job-{i}", {}, {"job_type": "http_manifest"}, status="completed")
        store.status_counts()

    # Living connections to this DB path should be ~0 after methods return.
    # Probe via a fresh connect count of open FDs pointing at the path is OS-specific;
    # instead assert the context manager closes by re-entering and checking not leaked
    # through sqlite3's connection tracker if available.
    import gc
    import sqlite3

    gc.collect()
    # Create one more and ensure we can still open (would fail at ulimit if leaked 200*2).
    store.create("final", {}, {"job_type": "http_manifest"}, status="queued")
    assert store.next_queued() is not None

    # Explicitly verify _db closes: after with-block, connection is unusable.
    with store._db() as db:
        conn = db
        conn.execute("SELECT 1").fetchone()
    try:
        conn.execute("SELECT 1")
        closed = False
    except sqlite3.ProgrammingError:
        closed = True
    assert closed, "YzuJobStore._db must close the connection on exit"
