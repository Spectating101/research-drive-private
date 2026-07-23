from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.research_data_mcp.registry_promotion import RegistryPromoter


def _promoter(repo: Path) -> RegistryPromoter:
    config = repo / "config"
    config.mkdir(parents=True, exist_ok=True)
    registry = config / "research_query_registry.json"
    registry.write_text(json.dumps({"datasets": []}), encoding="utf-8")
    promoter = RegistryPromoter(repo, registry)

    def capture(spec, *, task_id, job_id, campaign_id=""):
        del task_id, job_id, campaign_id
        return dict(spec)

    promoter._upsert_dataset = capture  # type: ignore[method-assign]
    return promoter


def _datacite_job(destination: str, filename: str) -> dict:
    return {
        "id": "job_datacite",
        "status": "completed",
        "plan": {
            "job_type": "http_manifest",
            "datacite_doi": "10.1234/example",
            "destination": destination,
            "datacite_file": filename,
            "title": "DataCite fixture",
        },
        "result": {},
    }


def test_datacite_csv_requires_successful_query_smoke(tmp_path: Path):
    target = tmp_path / "data_lake/procured/datacite/data.csv"
    target.parent.mkdir(parents=True)
    target.write_text("id,value\n1,alpha\n2,beta\n", encoding="utf-8")
    promoter = _promoter(tmp_path)

    entry = promoter.promote_datacite_collect(
        _datacite_job("data_lake/procured/datacite", "data.csv"),
        doi="10.1234/example",
    )[0]

    assert entry["analysis_readiness"] == "query_ready"
    assert entry["query_smoke"]["ok"] is True
    assert entry["query_smoke"]["rows"] == 2
    assert entry["source_access_mode"] == "materialized_query_ready"


def test_datacite_empty_csv_remains_registered(tmp_path: Path):
    target = tmp_path / "data_lake/procured/datacite/empty.csv"
    target.parent.mkdir(parents=True)
    target.write_text("id,value\n", encoding="utf-8")
    promoter = _promoter(tmp_path)

    entry = promoter.promote_datacite_collect(
        _datacite_job("data_lake/procured/datacite", "empty.csv"),
        doi="10.1234/example",
    )[0]

    assert entry["analysis_readiness"] == "registered"
    assert entry["query_smoke"]["ok"] is False
    assert entry["query_smoke"]["rows"] == 0


def test_datacite_api_error_json_remains_registered(tmp_path: Path):
    target = tmp_path / "data_lake/procured/datacite/error.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps({"status": 429, "message": "API rate limit exceeded"}),
        encoding="utf-8",
    )
    promoter = _promoter(tmp_path)

    entry = promoter.promote_datacite_collect(
        _datacite_job("data_lake/procured/datacite", "error.json"),
        doi="10.1234/example",
    )[0]

    assert entry["analysis_readiness"] == "registered"
    assert entry["query_smoke"]["ok"] is False
    assert entry["query_smoke"]["error"] == "api_error_envelope"


def _hf_job(canonical_dir: str, dataset_id: str = "org/example") -> dict:
    return {
        "id": "job_hf",
        "status": "completed",
        "plan": {"job_type": "huggingface_collect", "hf_dataset_id": dataset_id},
        "result": {"materialized": {"canonical_dir": canonical_dir}},
    }


def test_huggingface_parquet_requires_successful_query_smoke(tmp_path: Path):
    canonical = Path("data_lake/procured/huggingface/org_example")
    root = tmp_path / canonical
    root.mkdir(parents=True)
    parquet = root / "data.parquet"
    pd.DataFrame([{"id": 1}, {"id": 2}]).to_parquet(parquet, index=False)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "title": "HF fixture",
                "primary_parquet": str(canonical / "data.parquet"),
                "files": [{"path": str(canonical / "data.parquet")}],
            }
        ),
        encoding="utf-8",
    )
    promoter = _promoter(tmp_path)

    entry = promoter.promote_huggingface_collect(
        _hf_job(str(canonical)),
        hf_dataset_id="org/example",
    )[0]

    assert entry["analysis_readiness"] == "query_ready"
    assert entry["query_smoke"]["ok"] is True
    assert entry["query_smoke"]["rows"] == 2
    assert entry["source_access_mode"] == "materialized_query_ready"
    assert "org/example" in entry["description"]


def test_huggingface_empty_parquet_remains_registered(tmp_path: Path):
    canonical = Path("data_lake/procured/huggingface/org_empty")
    root = tmp_path / canonical
    root.mkdir(parents=True)
    parquet = root / "data.parquet"
    pd.DataFrame(columns=["id"]).to_parquet(parquet, index=False)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "title": "HF empty fixture",
                "primary_parquet": str(canonical / "data.parquet"),
                "files": [{"path": str(canonical / "data.parquet")}],
            }
        ),
        encoding="utf-8",
    )
    promoter = _promoter(tmp_path)

    entry = promoter.promote_huggingface_collect(
        _hf_job(str(canonical), "org/empty"),
        hf_dataset_id="org/empty",
    )[0]

    assert entry["analysis_readiness"] == "registered"
    assert entry["query_smoke"]["ok"] is False
    assert entry["query_smoke"]["rows"] == 0
