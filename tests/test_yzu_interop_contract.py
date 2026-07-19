from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.yzu_cluster.interop_contract import InteropStore, stage


class InteropStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = InteropStore(str(Path(self.tempdir.name) / "interop.sqlite"))

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    def test_stage_aliases(self) -> None:
        self.assertEqual(stage("verifying"), "validating")
        self.assertEqual(stage("materializing"), "registering")
        self.assertEqual(stage("success"), "completed")

    def test_capability_claim_chooses_eligible_work(self) -> None:
        self.store.upsert_worker("optiplex", pool="controller", capabilities=["python3", "rclone", "http"])
        self.store.submit(job_id="browser-job", job_type="scraper_run", required_capabilities=["browser"])
        pipeline = self.store.submit(
            job_id="pipeline-job",
            job_type="registered_pipeline",
            required_capabilities=["python", "archive"],
            inputs=["source-a"],
            outputs=["output-a"],
        )
        claim = self.store.claim("optiplex", lease_seconds=60)
        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim.run_id, pipeline["run_id"])
        self.assertEqual(claim.required_capabilities, ("archive", "python"))
        active = {item["id"]: item for item in self.store.active()}
        self.assertEqual(active["browser-job"]["status"], "queued")
        self.assertEqual(active["pipeline-job"]["status"], "assigned")
        self.assertEqual(active["pipeline-job"]["assigned_worker"]["id"], "optiplex")

    def test_progress_is_authoritative_and_heartbeat_extends_lease(self) -> None:
        self.store.upsert_worker("asus-01", pool="windows_lab", capabilities=["python"])
        run = self.store.submit(job_id="job-1", job_type="pipeline", required_capabilities=["python"])
        claim = self.store.claim("asus-01", lease_seconds=30, at="2026-07-19T10:00:00Z")
        assert claim is not None
        snapshot = self.store.heartbeat(
            run["run_id"],
            "asus-01",
            next_stage="running",
            current=2,
            total=5,
            lease_seconds=90,
            at="2026-07-19T10:00:10Z",
        )
        self.assertEqual(snapshot["status"], "running")
        self.assertEqual(snapshot["progress"], {"current": 2.0, "total": 5.0})
        self.assertEqual(snapshot["lease_expires_at"], "2026-07-19T10:01:40Z")
        self.assertEqual(snapshot["lifecycle"]["events"][-1]["event_type"], "running")

    def test_expired_lease_retries_then_eventually_fails(self) -> None:
        self.store.upsert_worker("worker", capabilities=["http"])
        run = self.store.submit(
            job_id="lease-job",
            job_type="http_manifest",
            required_capabilities=["http"],
            max_attempts=2,
        )
        first = self.store.claim("worker", lease_seconds=10, at="2026-07-19T10:00:00Z")
        assert first is not None
        expired = self.store.reap_expired(at="2026-07-19T10:00:11Z")
        self.assertEqual(expired, [run["run_id"]])
        self.assertEqual(self.store.snapshot(run["run_id"])["status"], "retrying")
        second = self.store.claim("worker", lease_seconds=10, at="2026-07-19T10:01:00Z")
        assert second is not None
        self.store.reap_expired(at="2026-07-19T10:01:11Z")
        final = self.store.snapshot(run["run_id"])
        self.assertEqual(final["status"], "failed")
        self.assertEqual(final["error"], "worker lease expired")
        self.assertEqual(final["attempt"], 2)

    def test_completed_is_not_registered(self) -> None:
        self.store.upsert_worker("optiplex", capabilities=["python", "archive"])
        run = self.store.submit(
            job_id="build",
            job_type="registered_pipeline",
            required_capabilities=["python", "archive"],
            inputs=["input-a"],
            outputs=["output-a"],
        )
        self.store.claim("optiplex")
        self.store.record(run["run_id"], "running", worker_id="optiplex")
        completed = self.store.record(
            run["run_id"],
            "completed",
            worker_id="optiplex",
            outputs=["output-a"],
            manifest_id="manifest-a",
            archive_verified=True,
            rows=100,
        )
        self.assertEqual(completed["status"], "completed")
        self.assertIsNone(completed["registration_id"])
        asset = self.store.register(
            run["run_id"],
            dataset_id="output-a",
            registry_id="registry:output-a",
            revision_id="rev-1",
            manifest_id="manifest-a",
            vault_path="gdrive:collection/output-a",
            archive_verified=True,
            verification_state="partial",
            verification_summary="9 of 10 entities matched",
            source={"label": "Derived evidence"},
            source_snapshots=["input-a@2026-07-19"],
            rows=100,
            fields=8,
            grain="entity-week",
        )
        registered = self.store.snapshot(run["run_id"])
        self.assertEqual(registered["status"], "registered")
        self.assertEqual(registered["registration_id"], "registry:output-a")
        self.assertEqual(asset["analysis_readiness"], "query_ready")
        self.assertTrue(asset["drive_verified"])
        self.assertEqual(asset["lineage"]["inputs"], ["input-a"])

    def test_registration_requires_archive_and_output_identity(self) -> None:
        run = self.store.submit(job_id="build-2", job_type="pipeline", outputs=["expected-output"])
        with self.assertRaisesRegex(ValueError, "verified archive"):
            self.store.register(
                run["run_id"],
                dataset_id="expected-output",
                registry_id="registry:x",
                revision_id=None,
                manifest_id="manifest-x",
                vault_path="gdrive:x",
                archive_verified=False,
            )
        with self.assertRaisesRegex(ValueError, "declared run output"):
            self.store.register(
                run["run_id"],
                dataset_id="wrong-output",
                registry_id="registry:x",
                revision_id=None,
                manifest_id="manifest-x",
                vault_path="gdrive:x",
                archive_verified=True,
            )

    def test_stage_regression_and_terminal_mutation_are_rejected(self) -> None:
        run = self.store.submit(job_id="ordered", job_type="pipeline")
        self.store.record(run["run_id"], "running")
        with self.assertRaisesRegex(ValueError, "regression"):
            self.store.record(run["run_id"], "queued")
        self.store.record(run["run_id"], "completed")
        with self.assertRaisesRegex(ValueError, "only advance to registered"):
            self.store.record(run["run_id"], "validating")

    def test_partial_snapshot_does_not_invent_progress_or_proof(self) -> None:
        run = self.store.submit(job_id="unknown", job_type="harvest_shard")
        snapshot = self.store.snapshot(run["run_id"])
        self.assertIsNone(snapshot["progress"])
        self.assertFalse(snapshot["drive_verified"])
        self.assertIsNone(snapshot["registration_id"])
        self.assertEqual(snapshot["outputs"], [])


if __name__ == "__main__":
    unittest.main()
