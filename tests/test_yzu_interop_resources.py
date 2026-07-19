from __future__ import annotations

import unittest

from scripts.yzu_cluster.interop_contract import InteropStore


class ResourceStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InteropStore()

    def tearDown(self) -> None:
        self.store.close()

    def test_capacity_aware_claim_reserves_declared_resources(self) -> None:
        self.store.upsert_worker("small", capabilities=["python"], capacity={"cpu_cores": 2, "memory_mb": 1024})
        self.store.upsert_worker("large", capabilities=["python"], capacity={"cpu_cores": 8, "memory_gb": 16})
        run = self.store.submit(
            job_id="large-job", job_type="pipeline", required_capabilities=["python"],
            resource_requirements={"cpu_cores": 4, "memory_mb": 4096},
        )
        self.assertIsNone(self.store.claim("small"))
        claim = self.store.claim("large")
        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim.run_id, run["run_id"])
        self.assertEqual(self.store.reservation(run["run_id"])["cpu_cores"], 4)
        self.assertEqual(self.store.resource_fit(run["run_id"], "small")["status"], "blocked")

    def test_reservation_prevents_overcommit_and_releases_on_completion(self) -> None:
        self.store.upsert_worker("worker", capabilities=["python"], capacity={"cpu_cores": 4, "memory_mb": 4096})
        first = self.store.submit(
            job_id="first", job_type="pipeline", required_capabilities=["python"],
            resource_requirements={"cpu_cores": 3},
        )
        second = self.store.submit(
            job_id="second", job_type="pipeline", required_capabilities=["python"],
            resource_requirements={"cpu_cores": 3},
        )
        self.store.claim("worker")
        self.assertIsNone(self.store.claim("worker"))
        self.store.record(first["run_id"], "completed", worker_id="worker")
        self.assertIsNone(self.store.reservation(first["run_id"]))
        claim = self.store.claim("worker")
        self.assertEqual(claim.run_id, second["run_id"])

    def test_unknown_capacity_does_not_claim_resource_demanding_job(self) -> None:
        self.store.upsert_worker("unknown", capabilities=["python"], capacity={})
        run = self.store.submit(
            job_id="demanding", job_type="pipeline", required_capabilities=["python"],
            resource_requirements={"memory_mb": 2048},
        )
        self.assertEqual(self.store.resource_fit(run["run_id"], "unknown")["status"], "unknown")
        self.assertIsNone(self.store.claim("unknown"))
        self.assertEqual(self.store.snapshot(run["run_id"])["status"], "queued")

    def test_usage_accounting_sums_consumption_and_peaks_memory(self) -> None:
        run = self.store.submit(job_id="metered", job_type="pipeline")
        self.store.record_usage(
            run["run_id"], worker_id="a", cpu_seconds=10,
            memory_peak_mb=512, network_bytes=1000, api_calls=2,
        )
        usage = self.store.record_usage(
            run["run_id"], worker_id="a", cpu_seconds=5,
            memory_peak_mb=768, network_bytes=500, api_calls=1,
        )
        self.assertEqual(usage["cpu_seconds"], 15)
        self.assertEqual(usage["memory_peak_mb"], 768)
        self.assertEqual(usage["network_bytes"], 1500)
        self.assertEqual(usage["api_calls"], 3)
        self.assertEqual(usage["samples"], 2)


if __name__ == "__main__":
    unittest.main()
