from __future__ import annotations

import unittest

from scripts.yzu_cluster.interop_contract import InteropStore


class ReliabilityPolicyTests(unittest.TestCase):
    def test_stale_worker_cannot_claim_until_heartbeat_refreshes(self) -> None:
        store = InteropStore(worker_stale_after_seconds=30)
        self.addCleanup(store.close)
        store.upsert_worker(
            "worker-a",
            capabilities=["http"],
            heartbeat_at="2026-07-19T10:00:00Z",
        )
        store.submit(job_id="download-a", job_type="http_manifest", required_capabilities=["http"])

        self.assertIsNone(store.claim("worker-a", at="2026-07-19T10:00:31Z"))
        stale = store.worker("worker-a", at="2026-07-19T10:00:31Z")
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["freshness"]["state"], "stale")
        self.assertEqual(stale["freshness"]["age_seconds"], 31.0)

        store.upsert_worker(
            "worker-a",
            capabilities=["http"],
            heartbeat_at="2026-07-19T10:00:32Z",
        )
        claim = store.claim("worker-a", at="2026-07-19T10:00:33Z")
        self.assertIsNotNone(claim)

    def test_repeated_submission_returns_same_run_but_conflicts_fail(self) -> None:
        store = InteropStore()
        self.addCleanup(store.close)
        request = {
            "job_id": "stable-request-key",
            "job_type": "pipeline",
            "title": "Build panel",
            "required_capabilities": ["python", "pipeline"],
            "inputs": ["source-a"],
            "outputs": ["panel-a"],
            "resource_requirements": {"cpu_cores": 2, "memory_mb": 1024, "priority": 70},
        }
        first = store.submit(**request)
        replay = store.submit(**request)

        self.assertEqual(replay["run_id"], first["run_id"])
        event_count = store.db.execute(
            "SELECT COUNT(*) FROM events WHERE run_id=?", (first["run_id"],)
        ).fetchone()[0]
        self.assertEqual(event_count, 1)

        with self.assertRaisesRegex(ValueError, "different request"):
            store.submit(**{**request, "outputs": ["panel-b"]})

    def test_priority_claiming_uses_fifo_as_tie_breaker(self) -> None:
        store = InteropStore()
        self.addCleanup(store.close)
        store.upsert_worker("optiplex", capabilities=["python"])
        store.submit(
            job_id="low-priority",
            job_type="pipeline",
            required_capabilities=["python"],
            resource_requirements={"priority": 10},
        )
        high_first = store.submit(
            job_id="high-priority-first",
            job_type="pipeline",
            required_capabilities=["python"],
            resource_requirements={"priority": 90},
        )
        store.submit(
            job_id="high-priority-second",
            job_type="pipeline",
            required_capabilities=["python"],
            resource_requirements={"priority": 90},
        )

        claim = store.claim("optiplex")
        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim.run_id, high_first["run_id"])
        assigned = store.snapshot(claim.run_id)
        self.assertEqual(assigned["lifecycle"]["events"][-1]["priority"], 90)

    def test_registration_replay_is_idempotent_and_conflicts_fail(self) -> None:
        store = InteropStore()
        self.addCleanup(store.close)
        store.upsert_worker("optiplex", capabilities=["python", "archive"])
        run = store.submit(
            job_id="build-panel",
            job_type="registered_pipeline",
            required_capabilities=["python", "archive"],
            inputs=["source-a"],
            outputs=["panel-a"],
        )
        store.claim("optiplex")
        store.record(
            run["run_id"],
            "completed",
            worker_id="optiplex",
            outputs=["panel-a"],
            manifest_id="manifest-a",
            archive_verified=True,
        )
        proof = {
            "dataset_id": "panel-a",
            "registry_id": "registry:panel-a",
            "revision_id": "rev-1",
            "manifest_id": "manifest-a",
            "vault_path": "gdrive:collection/panel-a",
            "archive_verified": True,
            "lineage_inputs": ["source-a"],
            "checksum": "sha256:abc",
            "rows": 20,
            "fields": 5,
            "grain": "entity-week",
        }
        first = store.register(run["run_id"], **proof)
        replay = store.register(run["run_id"], **proof)

        self.assertEqual(replay, first)
        registered_events = store.db.execute(
            "SELECT COUNT(*) FROM events WHERE run_id=? AND event_type='registered'",
            (run["run_id"],),
        ).fetchone()[0]
        self.assertEqual(registered_events, 1)

        with self.assertRaisesRegex(ValueError, "conflicting registration proof"):
            store.register(run["run_id"], **{**proof, "manifest_id": "manifest-other"})


if __name__ == "__main__":
    unittest.main()
