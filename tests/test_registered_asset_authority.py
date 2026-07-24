from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_data_mcp.registered_asset_authority import list_verified_registration_receipts
from scripts.research_data_mcp.search import SearchService
from scripts.research_query_engine.engine import ResearchQueryEngine
from scripts.yzu_cluster.jobs import YzuJobStore


def _repo(tmp_path: Path, *, registry_rows: list[dict] | None = None) -> tuple[Path, Path, YzuJobStore]:
    (tmp_path / "config").mkdir()
    (tmp_path / "config/yzu_cluster.json").write_text(
        json.dumps(
            {
                "controller": {
                    "hostname": "optiplex-test",
                    "jobs_root": "data/jobs",
                    "status_root": "data/status",
                }
            }
        ),
        encoding="utf-8",
    )
    registry = tmp_path / "config/research_query_registry.json"
    registry.write_text(json.dumps({"datasets": registry_rows or []}), encoding="utf-8")
    return tmp_path, registry, YzuJobStore(tmp_path / "data/jobs/jobs.sqlite3")


def _registration_result(
    dataset_id: str,
    *,
    archive_verified: bool = True,
    registry_readback: bool = True,
    readiness: str = "registered",
) -> dict:
    return {
        "outputs": [dataset_id],
        "registration_evidence": {
            "dataset_id": dataset_id,
            "registry_id": dataset_id,
            "manifest_id": f"collection_manifest_{dataset_id}",
            "vault_path": f"gdrive:Research-Drive/{dataset_id}",
            "archive_verified": archive_verified,
            "registry_readback": registry_readback,
            "readiness": readiness,
            "title": f"Registered {dataset_id}",
            "grain": "file",
        },
    }


def _service(root: Path, registry: Path) -> SearchService:
    engine = ResearchQueryEngine(registry, repo_root=root)
    return SearchService(engine, registry, root)


def test_verified_receipt_recovers_missing_registered_asset(tmp_path: Path) -> None:
    root, registry, jobs = _repo(tmp_path)
    # Avoid ops-noise markers (smoke/canary/…) so professor list_datasets keeps the row.
    jobs.create(
        "Day-2 recovery asset",
        {"source": "discover_ui"},
        {"job_type": "http_manifest", "dataset_id": "day2_recovery_asset"},
        status="completed",
        job_id="day2-recovery-job",
    )
    jobs.update("day2-recovery-job", "completed", _registration_result("day2_recovery_asset"))

    service = _service(root, registry)
    listed = service.list_datasets()
    described = service.describe_dataset("day2_recovery_asset")

    assert listed["datasets"][0]["dataset_id"] == "day2_recovery_asset"
    assert listed["authority_summary"]["receipt_recovery_rows"] == 1
    assert described["analysis_readiness"] == "registered"
    assert described["manifest_id"] == "collection_manifest_day2_recovery_asset"
    assert described["archive_verified"] is True
    assert described["registry_readback"] is True
    assert described["catalog_reconciliation"]["state"] == "receipt_only"
    assert described["catalog_reconciliation"]["query_allowed"] is False

    # limit>100 disables the soft preview path so receipt-only stays non-queryable.
    with pytest.raises(ValueError, match="not present in the loaded query catalog"):
        service.query_dataset("day2_recovery_asset", {"limit": 200})


def test_completed_jobs_without_full_registration_proof_are_not_assets(tmp_path: Path) -> None:
    root, registry, jobs = _repo(tmp_path)
    jobs.create("Incomplete", {}, {"job_type": "http_manifest"}, status="completed", job_id="incomplete-job")
    jobs.update(
        "incomplete-job",
        "completed",
        _registration_result("incomplete_dataset", archive_verified=False),
    )
    jobs.create("No readback", {}, {"job_type": "http_manifest"}, status="completed", job_id="no-readback-job")
    jobs.update(
        "no-readback-job",
        "completed",
        _registration_result("no_readback_dataset", registry_readback=False),
    )
    jobs.create("Merely complete", {}, {"job_type": "http_manifest"}, status="completed", job_id="complete-only")
    jobs.update("complete-only", "completed", {"outputs": ["complete_only"]})

    assert list_verified_registration_receipts(root) == []
    assert _service(root, registry).list_datasets()["datasets"] == []


def test_loaded_registry_row_remains_primary_over_receipt(tmp_path: Path) -> None:
    registry_row = {
        "dataset_id": "canonical_dataset",
        "name": "Canonical registry row",
        "backend": "local_file",
        "local_path": "data/canonical.csv",
        "analysis_readiness": "registered",
        "access_shape": "local_file",
    }
    root, registry, jobs = _repo(tmp_path, registry_rows=[registry_row])
    jobs.create("Canonical", {}, {"job_type": "http_manifest"}, status="completed", job_id="canonical-job")
    jobs.update("canonical-job", "completed", _registration_result("canonical_dataset"))

    service = _service(root, registry)
    listed = service.list_datasets()
    described = service.describe_dataset("canonical_dataset")

    assert listed["authority_summary"]["receipt_recovery_rows"] == 0
    assert listed["datasets"][0]["backend"] == "local_file"
    assert described["name"] == "Canonical registry row"


def test_receipt_search_filters_are_applied(tmp_path: Path) -> None:
    root, registry, jobs = _repo(tmp_path)
    jobs.create("Filtered", {}, {"job_type": "http_manifest"}, status="completed", job_id="filtered-job")
    jobs.update("filtered-job", "completed", _registration_result("filtered_asset"))
    service = _service(root, registry)

    assert service.list_datasets(q="filtered")["returned"] == 1
    assert service.list_datasets(q="unrelated")["returned"] == 0
    assert service.list_datasets(readiness="registered")["returned"] == 1
    assert service.list_datasets(readiness="query_ready")["returned"] == 0
    assert service.list_datasets(access_shape="registered_archive")["returned"] == 1
