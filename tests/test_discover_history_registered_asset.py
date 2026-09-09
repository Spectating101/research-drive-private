from __future__ import annotations

from scripts.research_data_mcp.discover_history import build_discover_history


def _job(*, verified: bool = True, readiness: str = "registered") -> dict:
    return {
        "id": "research-acquisition-20260720a",
        "title": "Research acquisition",
        "status": "completed",
        "created_at": "2026-07-20T08:00:00+00:00",
        "updated_at": "2026-07-20T08:05:00+00:00",
        "request": {"source": "research_import"},
        "plan": {"job_type": "http_manifest"},
        "result": {
            "registration_evidence": {
                "dataset_id": "research_acquisition_20260720",
                "registry_id": "research_acquisition_20260720",
                "manifest_id": "collection_manifest_research-acquisition-20260720a",
                "vault_path": "gdrive:Research-Drive/research_acquisition_20260720",
                "archive_verified": verified,
                "registry_readback": verified,
                "readiness": readiness,
            }
        },
    }


def test_verified_registration_receipt_enters_history_without_discover_link() -> None:
    out = build_discover_history(jobs=[_job()])

    assert out["total"] == 1
    row = out["items"][0]
    assert row["kind"] == "registered_asset"
    assert row["dataset_id"] == "research_acquisition_20260720"
    assert row["manifest_id"] == "collection_manifest_research-acquisition-20260720a"
    assert row["status"] == "registered_not_queryable"
    assert row["readiness"] == "registered"
    assert row["query_ready"] is False
    assert row["archive_verified"] is True
    assert row["registry_readback"] is True
    assert out["filters_applied"]["excludes_raw_global_jobs"] is True


def test_unverified_global_job_remains_excluded() -> None:
    out = build_discover_history(jobs=[_job(verified=False)])
    assert out["items"] == []


def test_receipt_readiness_cannot_override_failed_catalog_reconciliation() -> None:
    """A receipt is proof of registration, not current query authority."""
    out = build_discover_history(jobs=[_job(readiness="query_ready")])

    row = out["items"][0]
    assert row["readiness"] == "query_ready"
    assert row["catalog_reconciliation"]["state"] == "receipt_only"
    assert row["catalog_reconciliation"]["query_allowed"] is False
    assert row["status"] == "registered_not_queryable"
    assert row["query_ready"] is False
    assert row["usable"] is False
    assert row["holding_status"] == "archived"
    assert "not query-ready" in row["summary"]


def test_current_loaded_catalog_overrides_stale_receipt_after_hydration() -> None:
    out = build_discover_history(
        jobs=[_job(readiness="query_ready")],
        current_datasets={
            "research_acquisition_20260720": {
                "dataset_id": "research_acquisition_20260720",
                "analysis_readiness": "query_ready",
                "materialization": {"query_ready": True},
            }
        },
    )

    row = out["items"][0]
    assert row["catalog_reconciliation"]["state"] == "catalog_loaded"
    assert row["catalog_reconciliation"]["registry_row_loaded"] is True
    assert row["catalog_reconciliation"]["query_allowed"] is True
    assert row["status"] == "query_ready"
    assert row["query_ready"] is True
    assert row["holding_status"] == "held"


def test_current_loaded_catalog_preserves_hydrate_required_truth() -> None:
    out = build_discover_history(
        jobs=[_job(readiness="query_ready")],
        current_datasets={
            "research_acquisition_20260720": {
                "dataset_id": "research_acquisition_20260720",
                "analysis_readiness": "registered",
                "hydrate_required": True,
                "runtime_readiness_reason": "local_bytes_missing",
                "materialization": {"query_ready": False},
            }
        },
    )

    row = out["items"][0]
    assert row["catalog_reconciliation"]["query_allowed"] is False
    assert row["status"] == "registered_not_queryable"
    assert row["query_ready"] is False


def test_registered_filter_returns_only_registered_asset_outcomes() -> None:
    linked_run = {
        "id": "discover-run",
        "title": "Discover run",
        "status": "running",
        "created_at": "2026-07-20T09:00:00+00:00",
        "request": {"source": "discover_ui"},
        "plan": {"job_type": "http_manifest"},
        "result": {},
    }
    out = build_discover_history(jobs=[linked_run, _job()], kind="registered")

    assert [row["kind"] for row in out["items"]] == ["registered_asset"]
