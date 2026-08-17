#!/usr/bin/env python3
"""A directory is never a data row.

glob() returns directories as well as files, and st_size on a directory is 4096. The
glob query handler stat'd whatever matched, so an empty directory named `*` produced
`{"path": ".../taiwan_twse/*", "file": "*", "bytes": 4096}` — a fabricated row that
also stopped the engine falling through to the real data root.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.research_query_engine.engine import ResearchQueryEngine


def _engine(tmp_path: Path, rows: list[dict]) -> ResearchQueryEngine:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "research_query_registry.json").write_text(
        json.dumps({"version": "0.1", "datasets": rows}), encoding="utf-8"
    )
    return ResearchQueryEngine(repo_root=tmp_path)


def test_a_directory_matching_the_glob_is_not_returned_as_a_row(tmp_path: Path) -> None:
    holdings = tmp_path / "data_lake/official_disclosures/taiwan_twse"
    holdings.mkdir(parents=True)
    (holdings / "20260521T071150Z").mkdir()          # a real timestamped landing dir
    (holdings / "*").mkdir()                          # the phantom that shadowed the root
    engine = _engine(
        tmp_path,
        [
            {
                "dataset_id": "twse_openapi_taiwan_market_layer",
                "backend": "local_json_glob",
                "local_path": "data_lake/official_disclosures/taiwan_twse/*",
            }
        ],
    )
    result = engine.query("twse_openapi_taiwan_market_layer", limit=10)
    assert result.rows == []
    assert result.meta["matched"] == 0
    for row in result.rows:
        assert row.get("bytes") != 4096


def test_real_files_under_the_glob_still_return(tmp_path: Path) -> None:
    holdings = tmp_path / "data_lake/official_disclosures/taiwan_twse"
    holdings.mkdir(parents=True)
    (holdings / "BWIBBU_ALL.json").write_text(json.dumps([{"code": "2330"}]), encoding="utf-8")
    (holdings / "nested").mkdir()
    engine = _engine(
        tmp_path,
        [
            {
                "dataset_id": "twse_openapi_taiwan_market_layer",
                "backend": "local_json_glob",
                "local_path": "data_lake/official_disclosures/taiwan_twse/*",
            }
        ],
    )
    result = engine.query("twse_openapi_taiwan_market_layer", limit=10)
    assert result.meta["matched"] == 1
    names = {str(row.get("file")) for row in result.rows}
    assert "nested" not in names
