from __future__ import annotations

import json
from pathlib import Path

from scripts.research_data_mcp.search import SearchService
from scripts.research_query_engine.engine import ResearchQueryEngine


def _service(tmp_path: Path, dataset: dict) -> SearchService:
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"datasets": [dataset]}), encoding="utf-8")
    engine = ResearchQueryEngine(registry, repo_root=tmp_path)
    return SearchService(engine, registry, tmp_path)


def test_raw_registered_tree_returns_fast_hydration_guidance(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        {
            "dataset_id": "raw-canary",
            "backend": "local_file",
            "analysis_readiness": "metadata_search",
            "local_path": "data/raw-canary",
            "source_of_truth": "gdrive",
            "canonical_remote": "gdrive:archive/raw-canary",
        },
    )

    out = service.query_dataset("raw-canary")

    assert out["rows"] == []
    assert out["meta"]["error"] == "not_query_ready"
    assert out["meta"]["required_action"] == "hydrate"
    assert out["meta"]["canonical_remote"] == "gdrive:archive/raw-canary"


def test_single_csv_materialization_is_queryable(tmp_path: Path) -> None:
    data = tmp_path / "data" / "panel.csv"
    data.parent.mkdir()
    data.write_text("id,value\na,1\n", encoding="utf-8")
    service = _service(
        tmp_path,
        {
            "dataset_id": "small-panel",
            "backend": "local_csv_file",
            "analysis_readiness": "instant",
            "local_path": "data/panel.csv",
        },
    )

    out = service.query_dataset("small-panel", {"limit": 1})

    assert out["rows"] == [{"id": "a", "value": 1}]
