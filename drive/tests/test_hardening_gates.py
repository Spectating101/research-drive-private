from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.research_data_mcp.craft_collect import enforce_submit_doctrine
from scripts.yzu_cluster.acquisitions import materialize_job, prove_query_smoke


def _write_empty_registry(repo: Path) -> None:
    config = repo / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "research_query_registry.json").write_text(
        json.dumps({"datasets": []}),
        encoding="utf-8",
    )


def _json_smoke(repo: Path, payload: object, *, revision_id: str = "rev_test") -> dict:
    _write_empty_registry(repo)
    path = repo / "panel.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return prove_query_smoke(
        repo,
        {
            "dataset_id": "smoke_json",
            "backend": "local_json_file",
            "local_path": str(path),
            "revision_id": revision_id,
        },
    )


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

    plan2 = dict(plan)
    plan2["revision_id"] = "rev_j2"
    artifact2 = json.dumps([{"a": 9}])
    zip_path2 = repo / "data_lake/yzu_cluster/jobs/j2/art.zip"
    zip_path2.parent.mkdir(parents=True)
    with zipfile.ZipFile(zip_path2, "w") as zf:
        zf.writestr("raw/sample.json", artifact2)
    materialize_job(
        repo,
        "j2",
        plan2,
        {"artifacts": [{"artifact": "data_lake/yzu_cluster/jobs/j2/art.zip"}], "collect_mode": "local"},
    )
    first = repo / "data_lake/procured/harden_ds_rev/revisions/rev_j1/sample.json"
    second = repo / "data_lake/procured/harden_ds_rev/revisions/rev_j2/sample.json"
    assert first.is_file()
    assert second.is_file()
    assert first.read_text() != second.read_text()
    assert json.loads((repo / "data_lake/procured/harden_ds_rev/CURRENT.json").read_text())["revision_id"] == "rev_j2"


def test_materialize_same_revision_same_bytes_is_idempotent(tmp_path: Path):
    repo = tmp_path
    zip_path = repo / "data_lake/yzu_cluster/jobs/j1/art.zip"
    zip_path.parent.mkdir(parents=True)
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("raw/sample.json", json.dumps([{"a": 1}]))
    plan = {
        "job_type": "http_manifest",
        "dataset_id": "stable_revision",
        "destination": "data_lake/procured/stable_revision",
        "revision_id": "rev_fixed",
    }
    result = {"artifacts": [{"artifact": "data_lake/yzu_cluster/jobs/j1/art.zip"}]}
    first = materialize_job(repo, "j1", dict(plan), result)
    second = materialize_job(repo, "j1", dict(plan), result)
    assert first["materialized"]["files"] == second["materialized"]["files"]


def test_materialize_same_revision_different_bytes_is_rejected(tmp_path: Path):
    repo = tmp_path
    first_zip = repo / "data_lake/yzu_cluster/jobs/j1/a.zip"
    first_zip.parent.mkdir(parents=True)
    with zipfile.ZipFile(first_zip, "w") as zf:
        zf.writestr("raw/sample.json", json.dumps([{"a": 1}]))
    plan = {
        "job_type": "http_manifest",
        "dataset_id": "collision_ds",
        "destination": "data_lake/procured/collision_ds",
        "revision_id": "rev_fixed",
    }
    materialize_job(repo, "j1", dict(plan), {"artifacts": [{"artifact": "data_lake/yzu_cluster/jobs/j1/a.zip"}]})

    second_zip = repo / "data_lake/yzu_cluster/jobs/j2/b.zip"
    second_zip.parent.mkdir(parents=True)
    with zipfile.ZipFile(second_zip, "w") as zf:
        zf.writestr("raw/sample.json", json.dumps([{"a": 2}]))
    with pytest.raises(RuntimeError, match="immutable revision collision"):
        materialize_job(
            repo,
            "j2",
            dict(plan),
            {"artifacts": [{"artifact": "data_lake/yzu_cluster/jobs/j2/b.zip"}]},
        )


def test_query_smoke_requires_real_nonzero_rows(tmp_path: Path):
    smoke = _json_smoke(tmp_path, [{"id": 1}, {"id": 2}], revision_id="rev_rows")
    assert smoke == {
        "revision_id": "rev_rows",
        "dataset_id": "smoke_json",
        "backend": "local_json_file",
        "ok": True,
        "rows": 2,
        "error": None,
    }


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ([], "empty_payload"),
        ({}, "empty_payload"),
        ({"results": []}, "empty_collection"),
        ({"data": []}, "empty_collection"),
        ({"status": 429, "message": "API rate limit exceeded"}, "api_error_envelope"),
        ({"success": False, "error": "unauthorized"}, "api_error_envelope"),
        ({"status": {"error_code": 10005, "error_message": "invalid API key"}}, "api_error_envelope"),
    ],
)
def test_query_smoke_rejects_empty_and_error_envelopes(tmp_path: Path, payload: object, expected_error: str):
    smoke = _json_smoke(tmp_path, payload)
    assert smoke["ok"] is False
    assert smoke["rows"] == 0
    assert smoke["error"] == expected_error
    assert smoke["revision_id"] == "rev_test"


def test_query_smoke_rejects_malformed_json(tmp_path: Path):
    _write_empty_registry(tmp_path)
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    smoke = prove_query_smoke(
        tmp_path,
        {
            "dataset_id": "broken",
            "backend": "local_json_file",
            "local_path": str(path),
            "revision_id": "rev_broken",
        },
    )
    assert smoke["ok"] is False
    assert smoke["rows"] == 0
    assert smoke["revision_id"] == "rev_broken"
    assert smoke["error"]


def test_query_smoke_does_not_promote_metadata_only_file_tree(tmp_path: Path):
    _write_empty_registry(tmp_path)
    path = tmp_path / "artifact.pdf"
    path.write_bytes(b"%PDF-placeholder")
    smoke = prove_query_smoke(
        tmp_path,
        {
            "dataset_id": "metadata_only",
            "backend": "local_file",
            "local_path": str(path),
            "revision_id": "rev_pdf",
        },
    )
    assert smoke["ok"] is False
    assert smoke["rows"] == 0
    assert smoke["error"] == "metadata_only_backend"
    assert smoke["revision_id"] == "rev_pdf"


def test_faculty_and_ops_submit_doctrine_are_structural():
    with pytest.raises(ValueError, match="Faculty/desk"):
        enforce_submit_doctrine({"job_type": "registered_pipeline", "pipeline_id": "generic_name"})
    with pytest.raises(ValueError, match="Ops submit rejects unknown"):
        enforce_submit_doctrine(
            {"job_type": "future_vendor_lane", "ops_privileged": True},
            scope="ops",
        )
    allowed = enforce_submit_doctrine(
        {"job_type": "archive_upload", "local_path": "/tmp/archive", "ops_privileged": True},
        scope="ops",
    )
    assert allowed["job_type"] == "archive_upload"
