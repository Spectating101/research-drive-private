"""Panel path resolution — CRSP-style local_file with subpaths."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_resolve_panel_path_does_not_use_raw_as_run_dir(tmp_path: Path) -> None:
    from scripts.research_query_engine.engine import ResearchQueryEngine

    root = tmp_path
    (root / "data_lake/crsp/raw").mkdir(parents=True)
    (root / "data_lake/crsp/processed").mkdir(parents=True)
    reg = root / "config/research_query_registry.json"
    reg.parent.mkdir(parents=True)
    reg.write_text(
        """{
  "datasets": [{
    "dataset_id": "crsp_us_index_history",
    "backend": "local_parquet_panel",
    "local_root": "data_lake/crsp",
    "local_file": "processed/us_index_history.parquet"
  }]
}""",
        encoding="utf-8",
    )
    eng = ResearchQueryEngine(reg, repo_root=root)
    ds = eng.datasets["crsp_us_index_history"]
    with pytest.raises(FileNotFoundError, match="missing panel file"):
        eng._resolve_panel_path(ds, {})
