from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_data_mcp.craft_collect import enforce_submit_doctrine
from scripts.yzu_cluster.acquisitions import materialize_job, prove_query_smoke


def test_named_pipelines_quarantined_in_config():
    root = Path(__file__).resolve().parents[2]
    cfg = json.loads((root / "config/yzu_cluster.json").read_text(encoding="utf-8"))
    pipes = cfg.get("pipelines") or {}
    for key in ("skynet_stablecoin_harvest", "coingecko_daily", "ethereum_usdt_rpc_pilot"):
        assert pipes[key].get("enabled") is False
        assert pipes[key].get("procurement_triggered") is False
        assert pipes[key].get("legacy_quarantine") is True


def test_materialize_writes_immutable_revision(tmp_path: Path):
    repo = tmp_path
    (repo / "data_lake/yzu_cluster/jobs/j1").mkdir(parents=True)
    staging_src = repo / "data_lake/yzu_cluster/jobs/j1/raw"
    staging_src.mkdir(parents=True)
    artifact = staging_src / "sample.json"
    artifact.write_text(json.dumps([{"a": 1}, {"a": 2}]), encoding="utf-8")
    # Build a fake zip artifact path expected by materialize
    import zipfile
    zip_path = repo / "data_lake/yzu_cluster/jobs/j1/art.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("raw/sample.json", artifact.read_text(encoding="utf-8"))

    plan = {
        "job_type": "http_manifest",
        "dataset_id": "harden_ds_rev",
        "destination": "data_lake/procured/harden_ds_rev",
        "url": "https://example.com/x.json",
    }
    result = {
        "artifacts": [{"artifact": "data_lake/yzu_cluster/jobs/j1/art.zip"}],
        "collect_mode": "local",
    }
    out = materialize_job(repo, "j1", plan, result)
    mat = out["materialized"]
    assert mat["revision_id"] == "rev_j1"
    rev_dir = repo / mat["canonical_dir"]
    assert rev_dir.is_dir()
    assert (rev_dir / "sample.json").is_file()
    assert (repo / "data_lake/procured/harden_ds_rev/CURRENT.json").is_file()
    ptr = json.loads((repo / "data_lake/procured/harden_ds_rev/CURRENT.json").read_text())
    assert ptr["revision_id"] == "rev_j1"

    # Second collect with different bytes → new revision, old preserved
    plan2 = dict(plan)
    plan2["revision_id"] = "rev_j2"
    artifact2 = json.dumps([{"a": 9}])
    zip_path2 = repo / "data_lake/yzu_cluster/jobs/j2/art.zip"
    zip_path2.parent.mkdir(parents=True)
    with zipfile.ZipFile(zip_path2, "w") as zf:
        zf.writestr("raw/sample.json", artifact2)
    out2 = materialize_job(
        repo,
        "j2",
        plan2,
        {"artifacts": [{"artifact": "data_lake/yzu_cluster/jobs/j2/art.zip"}], "collect_mode": "local"},
    )
    assert (repo / "data_lake/procured/harden_ds_rev/revisions/rev_j1/sample.json").is_file()
    assert (repo / "data_lake/procured/harden_ds_rev/revisions/rev_j2/sample.json").is_file()
    old = (repo / "data_lake/procured/harden_ds_rev/revisions/rev_j1/sample.json").read_text()
    new = (repo / "data_lake/procured/harden_ds_rev/revisions/rev_j2/sample.json").read_text()
    assert old != new
    assert json.loads((repo / "data_lake/procured/harden_ds_rev/CURRENT.json").read_text())["revision_id"] == "rev_j2"


def test_query_smoke_requires_nonzero_rows(tmp_path: Path):
    repo = tmp_path
    path = repo / "panel.json"
    path.write_text(json.dumps([{"id": 1}, {"id": 2}]), encoding="utf-8")
    smoke = prove_query_smoke(
        repo,
        {"dataset_id": "smoke_ok", "backend": "local_json_file", "local_path": str(path)},
    )
    assert smoke["ok"] is True
    assert smoke["rows"] == 2


def test_query_smoke_rejects_empty_and_error_envelope(tmp_path: Path):
    repo = tmp_path
    empty = repo / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    smoke_empty = prove_query_smoke(
        repo,
        {"dataset_id": "smoke_empty", "backend": "local_json_file", "local_path": str(empty)},
    )
    assert smoke_empty["ok"] is False
    assert smoke_empty["rows"] == 0

    err = repo / "err.json"
    err.write_text(json.dumps({"error": "rate limit exceeded", "status": 429}), encoding="utf-8")
    smoke_err = prove_query_smoke(
        repo,
        {"dataset_id": "smoke_err", "backend": "local_json_file", "local_path": str(err)},
    )
    assert smoke_err["ok"] is False
    assert smoke_err.get("envelope") or smoke_err.get("error")


def test_execution_policy_strips_client_ops_and_blocks_auto_approve():
    from scripts.research_data_mcp.execution_policy import enforce_execution_submit

    plan, auto = enforce_execution_submit(
        {
            "job_type": "http_manifest",
            "url": "https://example.com/a.json",
            "items": [{"url": "https://example.com/a.json"}],
            "ops_privileged": True,
            "launchable": True,
        },
        {"ops_privileged": True},
        auto_approve=True,
    )
    assert plan.get("ops_privileged") is not True
    assert auto is False
    assert plan["execution_policy"]["scope"] == "faculty"

    with pytest.raises(ValueError):
        enforce_execution_submit(
            {"job_type": "registered_pipeline", "pipeline_id": "collection_queue", "ops_privileged": True},
            {},
            auto_approve=True,
        )


def test_ops_internal_allows_auto_approve_for_generic_http():
    from scripts.research_data_mcp.execution_policy import enforce_execution_submit

    plan, auto = enforce_execution_submit(
        {
            "job_type": "http_manifest",
            "url": "https://example.com/a.json",
            "items": [{"url": "https://example.com/a.json"}],
            "launchable": True,
        },
        {"_ops_internal": True},
        auto_approve=True,
    )
    assert plan.get("ops_privileged") is True
    assert auto is True
    assert plan["execution_policy"]["scope"] == "ops"
    assert plan["execution_policy"]["internal_ops"] is True


def test_scheduler_request_carries_ops_internal():
    from scripts.yzu_cluster.scheduler import YzuScheduler

    cfg = {
        "controller": {"status_root": "data_lake/yzu_runtime", "hostname": "test"},
        "schedules": [
            {
                "id": "demo_http",
                "enabled": True,
                "interval_hours": 24,
                "auto_approve": True,
                "plan": {
                    "title": "Demo",
                    "job_type": "http_manifest",
                    "url": "https://example.com/x.json",
                    "items": [{"url": "https://example.com/x.json"}],
                    "launchable": True,
                },
            }
        ],
    }
    sched = YzuScheduler(Path("/tmp"), cfg)
    emission = sched.build_emission("demo_http", force=True)
    assert emission["request"].get("_ops_internal") is True
    assert emission["auto_approve"] is True
