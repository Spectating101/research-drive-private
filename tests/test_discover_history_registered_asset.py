from __future__ import annotations

from scripts.research_data_mcp.discover_history import build_discover_history


def _job(*, verified: bool = True) -> dict:
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
                "readiness": "registered",
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
    assert row["status"] == "registered"
    assert row["archive_verified"] is True
    assert row["registry_readback"] is True
    assert out["filters_applied"]["excludes_raw_global_jobs"] is True


def test_unverified_global_job_remains_excluded() -> None:
    out = build_discover_history(jobs=[_job(verified=False)])
    assert out["items"] == []


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
