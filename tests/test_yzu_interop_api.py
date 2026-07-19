from __future__ import annotations

import unittest

from scripts.yzu_cluster.interop_api import InteropAPI
from scripts.yzu_cluster.interop_contract import InteropStore


class InteropAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InteropStore()
        self.api = InteropAPI(self.store)

    def tearDown(self) -> None:
        self.store.close()

    def test_submit_infers_capabilities_and_claims_correct_worker(self) -> None:
        self.api.join_worker({"id": "optiplex", "pool": "controller", "capabilities": ["python", "rclone"]})
        self.api.join_worker({"id": "spectator", "pool": "browser", "capabilities": ["cdp", "python"]})
        submitted = self.api.submit_job({"id": "scrape-1", "type": "scraper_run", "title": "Probe source"})
        self.assertEqual(submitted["job"]["required_capabilities"], ["browser"])
        self.assertIsNone(self.api.claim_job("optiplex")["job"])
        claimed = self.api.claim_job("spectator")["job"]
        self.assertEqual(claimed["id"], "scrape-1")
        self.assertEqual(claimed["assigned_worker"]["id"], "spectator")

    def test_health_and_jobs_match_frontend_shapes(self) -> None:
        self.api.join_worker({"id": "asus-01", "pool": "windows_lab", "capabilities": ["python"]})
        self.api.submit_job({"id": "job-1", "type": "pipeline", "outputs": ["panel-v1"]})
        health = self.api.health()
        jobs = self.api.jobs()
        self.assertEqual(health["cluster"]["workers"][0]["id"], "asus-01")
        self.assertEqual(health["desk"]["jobs"]["queued"], 1)
        self.assertEqual(jobs["jobs"][0]["id"], "job-1")
        self.assertIn("lifecycle", jobs["jobs"][0])

    def test_registration_returns_job_and_library_asset(self) -> None:
        self.api.join_worker({"id": "optiplex", "capabilities": ["python", "pipeline", "archive"]})
        run = self.api.submit_job({
            "id": "build-1", "type": "registered_pipeline",
            "inputs": ["source-a"], "outputs": ["panel-v1"],
            "required_capabilities": ["archive"],
        })["job"]
        self.api.claim_job("optiplex")
        self.api.record_event(run["run_id"], {"stage": "running", "worker_id": "optiplex"})
        self.api.record_event(run["run_id"], {
            "stage": "completed", "worker_id": "optiplex", "outputs": ["panel-v1"],
            "manifest_id": "manifest-1", "drive_verified": True, "row_count": 12,
        })
        result = self.api.register_output(run["run_id"], {
            "dataset_id": "panel-v1", "registry_id": "registry:panel-v1",
            "manifest_id": "manifest-1", "vault_path": "gdrive:collection/panel-v1",
            "drive_verified": True, "revision_id": "rev-1", "inputs": ["source-a"],
            "row_count": 12, "field_count": 4, "grain": "entity-week",
        })
        self.assertEqual(result["job"]["status"], "registered")
        self.assertEqual(result["asset"]["analysis_readiness"], "query_ready")
        self.assertEqual(result["asset"]["lineage"]["inputs"], ["source-a"])

    def test_heartbeat_rejects_wrong_worker(self) -> None:
        self.api.join_worker({"id": "worker-a", "capabilities": ["http"]})
        run = self.api.submit_job({"id": "download-1", "type": "http_manifest"})["job"]
        self.api.claim_job("worker-a")
        with self.assertRaises(PermissionError):
            self.api.heartbeat(run["run_id"], "worker-b", {"stage": "running"})

    def test_connector_endpoints_preserve_probe_and_sync_truth(self) -> None:
        created = self.api.upsert_connector({
            "connector_id": "datacite", "source_id": "datacite", "access_state": "unknown",
        })["connector"]
        self.assertTrue(created["probe_required"])
        probed = self.api.record_connector_probe("datacite", {
            "status": "available", "fields": ["doi", "updated"],
        })["connector"]
        self.assertEqual(probed["access_state"], "available")
        synced = self.api.record_connector_sync("datacite", {
            "state_token": "cursor-9", "timestamp": "2026-07-19T13:00:00Z", "quota_remaining": 77,
        })["connector"]
        self.assertEqual(synced["state_token"], "cursor-9")
        self.assertEqual(self.api.connectors()["connectors"][0]["quota_remaining"], 77)
        self.assertEqual(self.api.health()["desk"]["connectors"]["available"], 1)


if __name__ == "__main__":
    unittest.main()
