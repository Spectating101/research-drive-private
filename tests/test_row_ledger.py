"""An aggregate must say how much data it was computed over.

A spec with drop_na discarded 900 of 1000 rows and the manifest recorded only
the input's bytes and the output's 2 group rows. Nothing said the mean was
taken over a tenth of the source, so a heavily-thinned result was
indistinguishable from a complete one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.research_data_mcp.synthesis_executor import execute

FRAME = pd.DataFrame({"g": ["a", "b"] * 500, "v": [1.0] * 100 + [None] * 900})


def _repo(tmp_path: Path, frame: pd.DataFrame = FRAME) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    frame.to_parquet(tmp_path / "data/a.parquet")
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "a", "name": "a",
                                  "local_path": "data/a.parquet", "grain": "row"}]}),
        encoding="utf-8")
    return tmp_path


def _spec(transforms):
    return {"input_dataset_id": "a", "output_dataset_id": "synthesis_ledger_probe",
            "group_by": ["g"], "metrics": [{"function": "mean", "column": "v", "as": "m"}],
            "transforms": transforms}


def test_the_rows_an_aggregate_covered_are_reported(tmp_path):
    result = execute(_repo(tmp_path), "job",
                     {"execution_spec": _spec([{"op": "drop_na", "columns": ["v"]}]), "thread_id": "t"})
    assert result["source_rows"] == 1000
    assert result["rows_aggregated"] == 100


def test_each_step_records_what_it_removed(tmp_path):
    spec = _spec([{"op": "drop_na", "columns": ["v"]},
                  {"op": "filter", "column": "g", "cmp": "eq", "value": "a"}])
    result = execute(_repo(tmp_path), "job", {"execution_spec": spec, "thread_id": "t"})
    assert result["row_ledger"] == [
        {"step": 1, "op": "drop_na", "rows_in": 1000, "rows_out": 100},
        {"step": 2, "op": "filter", "rows_in": 100, "rows_out": 50},
    ]


def test_a_step_that_removes_nothing_still_appears(tmp_path):
    """Silence would be ambiguous between 'kept everything' and 'not recorded'."""
    spec = _spec([{"op": "select", "columns": ["g", "v"]}])
    result = execute(_repo(tmp_path), "job", {"execution_spec": spec, "thread_id": "t"})
    assert result["row_ledger"] == [{"step": 1, "op": "select", "rows_in": 1000, "rows_out": 1000}]


def test_a_spec_with_no_transforms_aggregates_every_source_row(tmp_path):
    result = execute(_repo(tmp_path), "job", {"execution_spec": _spec([]), "thread_id": "t"})
    assert result["source_rows"] == result["rows_aggregated"] == 1000
    assert result["row_ledger"] == []


def test_head_is_recorded_as_the_truncation_it_is(tmp_path):
    spec = _spec([{"op": "head", "n": 7}])
    result = execute(_repo(tmp_path), "job", {"execution_spec": spec, "thread_id": "t"})
    assert result["row_ledger"][0]["rows_out"] == 7
    assert result["rows_aggregated"] == 7


def test_drop_duplicates_is_recorded(tmp_path):
    repo = _repo(tmp_path, pd.DataFrame({"g": ["a", "a", "a", "b"], "v": [1.0, 1.0, 1.0, 2.0]}))
    spec = _spec([{"op": "drop_duplicates", "columns": ["g"]}])
    result = execute(repo, "job", {"execution_spec": spec, "thread_id": "t"})
    assert result["row_ledger"] == [{"step": 1, "op": "drop_duplicates", "rows_in": 4, "rows_out": 2}]


def test_the_ledger_is_written_to_the_manifest(tmp_path):
    repo = _repo(tmp_path)
    execute(repo, "job", {"execution_spec": _spec([{"op": "drop_na", "columns": ["v"]}]),
                          "thread_id": "t"})
    manifest = json.loads((repo / "data_lake/synthesis/thread_outputs/t/job/manifest.json").read_text())
    assert manifest["rows"]["source"] == 1000
    assert manifest["rows"]["aggregated"] == 100
    assert manifest["rows"]["by_step"][0]["op"] == "drop_na"


def test_the_output_row_count_is_still_the_group_count(tmp_path):
    """rows_aggregated counts input rows; output rows counts groups. Both are kept."""
    result = execute(_repo(tmp_path), "job",
                     {"execution_spec": _spec([{"op": "drop_na", "columns": ["v"]}]), "thread_id": "t"})
    assert result["rows"] == 2
    assert result["rows_aggregated"] == 100
