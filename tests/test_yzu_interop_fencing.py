from __future__ import annotations

import unittest

from scripts.yzu_cluster.interop_api import InteropAPI
from scripts.yzu_cluster.interop_contract import InteropStore


class AttemptFenceTests(unittest.TestCase):
    def test_expired_attempt_cannot_write_after_same_worker_reclaims(self) -> None:
        store = InteropStore(worker_stale_after_seconds=300)
        self.addCleanup(store.close)
        store.upsert_worker(
            "worker-a", capabilities=["http"], heartbeat_at="2026-07-19T10:00:00Z"
        )
        run = store.submit(
            job_id="download",
            job_type="http_manifest",
            required_capabilities=["http"],
            max_attempts=2,
        )
        first = store.claim("worker-a", lease_seconds=10, at="2026-07-19T10:00:00Z")
        assert first is not None
        store.reap_expired(at="2026-07-19T10:00:11Z")
        store.upsert_worker(
            "worker-a", capabilities=["http"], heartbeat_at="2026-07-19T10:01:00Z"
        )
        second = store.claim("worker-a", lease_seconds=10, at="2026-07-19T10:01:00Z")
        assert second is not None
        self.assertEqual(second.attempt, 2)

        with self.assertRaisesRegex(PermissionError, "stale execution attempt"):
            store.heartbeat(
                run["run_id"],
                "worker-a",
                next_stage="running",
                expected_attempt=first.attempt,
                at="2026-07-19T10:01:01Z",
            )
        with self.assertRaisesRegex(PermissionError, "stale execution attempt"):
            store.record_usage(
                run["run_id"],
                worker_id="worker-a",
                cpu_seconds=1,
                expected_attempt=first.attempt,
            )

        current = store.heartbeat(
            run["run_id"],
            "worker-a",
            next_stage="running",
            expected_attempt=second.attempt,
            at="2026-07-19T10:01:01Z",
        )
        self.assertEqual(current["attempt"], 2)
        self.assertEqual(current["status"], "running")

    def test_terminal_event_replay_is_idempotent_but_conflicts_fail(self) -> None:
        store = InteropStore()
        self.addCleanup(store.close)
        store.upsert_worker("worker-a", capabilities=["http"])
        run = store.submit(
            job_id="collect",
            job_type="http_manifest",
            required_capabilities=["http"],
            outputs=["snapshot-a"],
        )
        claim = store.claim("worker-a")
        assert claim is not None
        proof = {
            "worker_id": "worker-a",
            "outputs": ["snapshot-a"],
            "manifest_id": "manifest-a",
            "archive_verified": True,
            "rows": 10,
            "expected_attempt": claim.attempt,
        }
        first = store.record(run["run_id"], "completed", **proof)
        replay = store.record(run["run_id"], "completed", **proof)
        self.assertEqual(replay["run_id"], first["run_id"])
        self.assertEqual(replay["status"], "completed")
        self.assertEqual(replay["manifest_id"], "manifest-a")
        self.assertEqual(replay["outputs"], ["snapshot-a"])
        completed_events = store.db.execute(
            "SELECT COUNT(*) FROM events WHERE run_id=? AND event_type='completed'",
            (run["run_id"],),
        ).fetchone()[0]
        self.assertEqual(completed_events, 1)

        with self.assertRaisesRegex(ValueError, "conflicting terminal event replay"):
            store.record(
                run["run_id"],
                "completed",
                **{**proof, "manifest_id": "manifest-other"},
            )

    def test_api_propagates_attempt_and_reports_stale_workers(self) -> None:
        store = InteropStore(worker_stale_after_seconds=300)
        self.addCleanup(store.close)
        api = InteropAPI(store)
        api.join_worker({
            "id": "stale-worker",
            "capabilities": ["http"],
            "heartbeat_at": "2000-01-01T00:00:00Z",
        })
        api.join_worker({"id": "live-worker", "capabilities": ["http"]})
        run = api.submit_job({"id": "job-a", "type": "http_manifest"})["job"]
        claimed = api.claim_job("live-worker")["job"]
        assert claimed is not None

        with self.assertRaisesRegex(PermissionError, "stale execution attempt"):
            api.heartbeat(
                run["run_id"],
                "live-worker",
                {"attempt": claimed["attempt"] + 1, "stage": "running"},
            )

        health = api.health()
        self.assertEqual(health["desk"]["worker_pools"]["stale"], 1)
        stale = next(worker for worker in health["cluster"]["workers"] if worker["id"] == "stale-worker")
        self.assertEqual(stale["status"], "stale")


if __name__ == "__main__":
    unittest.main()
