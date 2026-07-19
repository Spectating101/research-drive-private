from __future__ import annotations

import unittest

from scripts.yzu_cluster.interop_contract import InteropStore


class ConnectorStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InteropStore()

    def tearDown(self) -> None:
        self.store.close()

    def test_incremental_connector_preserves_schema_and_cursor(self) -> None:
        connector = self.store.upsert_connector({
            "connector_id": "mops-api", "source_id": "mops", "access": "public",
            "sync_mode": "incremental", "cursor_field": "published_at",
            "schema": {"fields": [{"name": "issuer_id"}, {"name": "published_at"}]},
            "primary_key": ["issuer_id", "published_at"], "rate_limit": "60/min",
        })
        self.assertEqual(connector["access_state"], "available")
        self.assertEqual(connector["sync_mode"], "incremental")
        self.assertEqual(connector["schema_fields"], ["issuer_id", "published_at"])
        self.assertEqual(connector["primary_key"], ["issuer_id", "published_at"])

    def test_credential_required_overrides_unknown_status(self) -> None:
        connector = self.store.upsert_connector({
            "connector_id": "licensed", "source_id": "licensed-feed",
            "credential_required": True, "credential_profile": "faculty-license",
        })
        self.assertEqual(connector["access_state"], "credential_required")
        self.assertTrue(connector["credential_required"])
        self.assertTrue(connector["supported"])

    def test_probe_resolves_unknown_without_inventing_sync_state(self) -> None:
        initial = self.store.upsert_connector({"connector_id": "new-source", "source_id": "new"})
        self.assertEqual(initial["access_state"], "unknown")
        self.assertTrue(initial["probe_required"])
        probed = self.store.record_probe("new-source", {
            "status": "available", "fields": ["id", "date"], "estimated_bytes": 1024,
        })
        self.assertEqual(probed["access_state"], "available")
        self.assertFalse(probed["probe_required"])
        self.assertEqual(probed["sync_mode"], "unknown")
        self.assertEqual(probed["estimated_bytes"], 1024)

    def test_sync_checkpoint_is_durable(self) -> None:
        self.store.upsert_connector({
            "connector_id": "datacite", "source_id": "datacite", "access": "public",
            "sync_mode": "incremental", "cursor_field": "updated",
        })
        synced = self.store.record_sync(
            "datacite", state_token="cursor-22",
            last_synced_at="2026-07-19T12:00:00Z", quota_remaining=88,
        )
        self.assertEqual(synced["state_token"], "cursor-22")
        self.assertEqual(synced["quota_remaining"], 88)
        self.assertEqual(self.store.connector("datacite")["last_synced_at"], "2026-07-19T12:00:00Z")


if __name__ == "__main__":
    unittest.main()
