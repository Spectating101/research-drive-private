from __future__ import annotations

from scripts.research_data_mcp.discover_history import build_discover_history


def _job(*, verified: bool = True) -> dict:
    return {
        "id": "day2-deploy-smoke-20260720a",
        "title": "Day-2 deploy smoke",
        "status": "completed",
        "created_at": "2026-07-20T08:00:00+00:00",
        "updated_at": "2026-07-20T08:05:00+00:00",
        "request": {"source": "host_acceptance"},
        "plan": {"job_type": "http_manifest"},
        "result": {
            "registration_evidence": {
                "dataset_id": "day2_deploy_smoke_20260720",
                "registry_id": "day2_deploy_smoke_20260720",
                "manifest_id": "collection_manifest_day2-deploy-smoke-20260720a",
                "vault_path": "gdrive:Research-Drive/day2_deploy_smoke_20260720",
                "archive_verified": verified,
                "registry_readback": verified,
                "readiness": "registered",
            }
        },
    }


def test_verified_registration_receipt_enters_history_without_discover_link() -> None:
    out = build_discover_history(jobs=[_job()], include_ops=True)

    assert out["total"] == 1
    row = out["items"][0]
    assert row["kind"] == "registered_asset"
    assert row["dataset_id"] == "day2_deploy_smoke_20260720"
    assert row["manifest_id"] == "collection_manifest_day2-deploy-smoke-20260720a"
    assert row["status"] == "registered_not_queryable"
    assert row["usable"] is False
    assert row["query_ready"] is False
    assert row["holding_status"] == "archived"
    assert "not queryable" in str(row["progress"]["label"]).lower()
    assert row["archive_verified"] is True
    assert row["registry_readback"] is True
    assert out["filters_applied"]["excludes_raw_global_jobs"] is True


def test_unverified_global_job_remains_excluded() -> None:
    out = build_discover_history(jobs=[_job(verified=False)], include_ops=True)
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
    out = build_discover_history(jobs=[linked_run, _job()], kind="registered", include_ops=True)

    assert [row["kind"] for row in out["items"]] == ["registered_asset"]


def test_ready_filter_excludes_registered_but_not_queryable() -> None:
    out = build_discover_history(jobs=[_job()], kind="ready", include_ops=True)
    assert out["items"] == []


def test_ops_canaries_hidden_by_default() -> None:
    out = build_discover_history(jobs=[_job()], include_ops=False)
    assert out["items"] == []
