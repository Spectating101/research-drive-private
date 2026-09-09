from __future__ import annotations

import json

from scripts.research_data_mcp.backfill_library_provenance import backfill_registry_document
from scripts.research_data_mcp.library_provenance import provenance_from_job, stamp_spec_with_job_provenance
from scripts.research_data_mcp.registry_promotion import RegistryPromoter


def test_provenance_from_job_keeps_exact_recorded_source_and_reproduction_route():
    job = {
        "id": "job-1",
        "plan": {
            "job_type": "http_manifest",
            "url": "https://data.example.org/releases/panel.csv?version=7",
            "collect_via": "http_manifest",
            "command": ["python3", "scripts/fetch_panel.py", "--release", "7"],
            "script_path": "scripts/fetch_panel.py",
            "connector_id": "src_example_panel",
        },
        "result": {
            "webfetch": {
                "fetched_at": "2026-08-27T12:00:00Z",
                "content_sha256": "a" * 64,
            }
        },
    }

    receipt = provenance_from_job(job)

    assert receipt["source_url"] == "https://data.example.org/releases/panel.csv?version=7"
    assert receipt["collection_method"] == "http_manifest"
    assert receipt["collection_script"] == "scripts/fetch_panel.py"
    assert receipt["collection_command"] == "python3 scripts/fetch_panel.py --release 7"
    assert receipt["source_route"] == "src_example_panel"
    assert receipt["fetched_at"] == "2026-08-27T12:00:00Z"
    assert receipt["content_sha256"] == "a" * 64


def test_provenance_never_manufactures_or_leaks_a_source_url():
    provider_only = provenance_from_job({"plan": {"source": "GDELT", "job_type": "registered_pipeline"}})
    credential_url = provenance_from_job(
        {"plan": {"url": "https://alice:secret@example.org/private.csv", "job_type": "http_manifest"}}
    )

    assert provider_only["source_url"] == ""
    assert credential_url["source_url"] == ""


def test_stamp_preserves_existing_authority_and_adds_nested_procurement_receipt():
    spec = {
        "dataset_id": "held_panel",
        "source_url": "https://archive.example.org/canonical.csv",
        "procurement": {"source_task_id": "existing-task"},
    }
    job = {
        "plan": {
            "job_type": "http_manifest",
            "url": "https://mirror.example.org/run.csv",
            "collect_via": "http_manifest",
            "pipeline_script": "scripts/fetch_run.py",
        }
    }

    stamped = stamp_spec_with_job_provenance(spec, job)

    assert stamped["source_url"] == "https://archive.example.org/canonical.csv"
    assert stamped["collection_method"] == "http_manifest"
    assert stamped["collection_script"] == "scripts/fetch_run.py"
    assert stamped["procurement"]["source_task_id"] == "existing-task"
    assert stamped["procurement"]["source_url"] == "https://mirror.example.org/run.csv"
    assert stamped["procurement"]["collect_via"] == "http_manifest"


def test_registry_promotion_keeps_reproduction_receipt(monkeypatch, tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"version": 1, "datasets": []}), encoding="utf-8")
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"tasks": {}, "connectors": {}, "pipelines": {}}), encoding="utf-8")

    promoter = RegistryPromoter(tmp_path, registry_path, map_path)
    monkeypatch.setattr("scripts.research_data_mcp.registry_promotion.is_drive_first", lambda _root: True)
    monkeypatch.setattr("scripts.yzu_cluster.acquisitions.prove_query_smoke", lambda *_args, **_kwargs: {"ok": True, "rows": 3})
    monkeypatch.setattr(promoter, "_task_ids_from_job", lambda _job: ["procured_src_example"])
    monkeypatch.setattr(promoter, "_artifact_exists", lambda _path: True)
    monkeypatch.setattr(
        promoter,
        "_spec_for_task",
        lambda _task_id, _job, _campaign_id="": {
            "dataset_id": "example_panel",
            "name": "Example panel",
            "backend": "local_csv_file",
            "analysis_readiness": "registered",
            "local_path": "data/example.csv",
        },
    )

    promoter.promote_job(
        {
            "id": "job-promote",
            "status": "completed",
            "plan": {
                "job_type": "http_manifest",
                "url": "https://data.example.org/example.csv",
                "collect_via": "http_manifest",
                "script_path": "scripts/fetch_example.py",
                "command": ["python3", "scripts/fetch_example.py"],
                "connector_id": "src_example",
            },
        }
    )

    row = json.loads(registry_path.read_text(encoding="utf-8"))["datasets"][0]
    assert row["source_url"] == "https://data.example.org/example.csv"
    assert row["collection_method"] == "http_manifest"
    assert row["collection_script"] == "scripts/fetch_example.py"
    assert row["collection_command"] == "python3 scripts/fetch_example.py"
    assert row["source_route"] == "src_example"
    assert row["procurement"]["source_url"] == "https://data.example.org/example.csv"
    assert row["procurement"]["collect_via"] == "http_manifest"
    assert row["procurement"]["promoted_from_job"] == "job-promote"


def test_backfill_uses_only_linked_jobs_and_does_not_mutate_input():
    registry = {
        "version": 1,
        "datasets": [
            {
                "dataset_id": "old_panel",
                "source": "GDELT GKG",
                "procurement": {"promoted_from_job": "old-job"},
            },
            {
                "dataset_id": "manual_asset",
                "source": "Self provided",
            },
        ],
    }
    jobs = {
        "old-job": {
            "id": "old-job",
            "plan": {
                "job_type": "http_manifest",
                "url": "https://data.gdeltproject.org/gkg/20260827.gkg.csv.zip",
                "collect_via": "http_manifest",
                "script_path": "scripts/run_news_shock_gkg_queue.py",
            },
        }
    }

    enriched, report = backfill_registry_document(registry, jobs.__getitem__)

    assert "source_url" not in registry["datasets"][0]
    row = enriched["datasets"][0]
    assert row["source_url"] == "https://data.gdeltproject.org/gkg/20260827.gkg.csv.zip"
    assert row["collection_method"] == "http_manifest"
    assert row["collection_script"] == "scripts/run_news_shock_gkg_queue.py"
    assert report["changed_dataset_ids"] == ["old_panel"]
    assert report["missing_recorded_job_id_dataset_ids"] == ["manual_asset"]
