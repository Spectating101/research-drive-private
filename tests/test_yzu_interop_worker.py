from __future__ import annotations

import unittest

from scripts.yzu_cluster.interop_contract import InteropStore
from scripts.yzu_cluster.interop_worker import WorkerRunner


class WorkerRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InteropStore()
        self.store.upsert_worker("optiplex", capabilities=["python", "pipeline", "archive"])

    def tearDown(self) -> None:
        self.store.close()

    def test_handler_can_progress_complete_and_register(self) -> None:
        run = self.store.submit(
            job_id="build-panel", job_type="registered_pipeline",
            required_capabilities=["python", "pipeline", "archive"],
            inputs=["source-a"], outputs=["panel-v1"],
        )

        def build(context):
            context.heartbeat(current=1, total=2, stage="validating")
            return {
                "outputs": ["panel-v1"], "manifest_id": "manifest-1",
                "archive_verified": True, "row_count": 20, "field_count": 5,
                "registration": {
                    "dataset_id": "panel-v1", "registry_id": "registry:panel-v1",
                    "vault_path": "gdrive:collection/panel-v1", "archive_verified": True,
                    "revision_id": "rev-1", "grain": "entity-week",
                },
            }

        result = WorkerRunner(self.store, "optiplex", {"registered_pipeline": build}).run_once()
        self.assertEqual(result["job"]["status"], "registered")
        self.assertEqual(result["asset"]["dataset_id"], "panel-v1")
        self.assertEqual(result["asset"]["row_count"], 20)
        events = self.store.snapshot(run["run_id"])["lifecycle"]["events"]
        self.assertIn("validating", [event["stage"] for event in events])

    def test_missing_handler_blocks_without_false_execution(self) -> None:
        self.store.submit(job_id="unknown", job_type="custom", required_capabilities=[])
        result = WorkerRunner(self.store, "optiplex", {}).run_once()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("unsupported job type", result["error"])
        self.assertFalse(result["retryable"])
        self.assertIsNone(result["started_at"])

    def test_handler_exception_is_recorded_as_retryable_failure(self) -> None:
        run = self.store.submit(job_id="explode", job_type="pipeline", required_capabilities=["pipeline"])

        def explode(_context):
            raise RuntimeError("boom")

        result = WorkerRunner(self.store, "optiplex", {"pipeline": explode}).run_once()
        self.assertEqual(result["status"], "failed")
        self.assertIn("RuntimeError: boom", result["error"])
        self.assertTrue(result["retryable"])
        self.assertIsNotNone(result["started_at"])
        self.assertEqual(self.store.snapshot(run["run_id"])["attempt"], 1)

    def test_connector_sync_checkpoint_is_committed_with_completed_job(self) -> None:
        self.store.upsert_connector({
            "connector_id": "datacite", "source_id": "datacite", "access": "public",
            "sync_mode": "incremental", "cursor_field": "updated",
        })
        self.store.submit(job_id="sync-datacite", job_type="pipeline", required_capabilities=["pipeline"])

        def sync(_context):
            return {
                "outputs": ["datacite-snapshot"],
                "connector_sync": {
                    "connector_id": "datacite", "state_token": "cursor-42",
                    "last_synced_at": "2026-07-19T14:00:00Z", "quota_remaining": 52,
                },
            }

        result = WorkerRunner(self.store, "optiplex", {"pipeline": sync}).run_once()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["connector"]["state_token"], "cursor-42")
        self.assertEqual(self.store.connector("datacite")["quota_remaining"], 52)


if __name__ == "__main__":
    unittest.main()
