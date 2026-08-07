#!/usr/bin/env python3
"""Shape is measured from the file, and a failed probe never breaks a search."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drive"))

import scripts.research_data_mcp.dataset_shape as dataset_shape  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_cache():
    dataset_shape.reset_cache()
    yield
    dataset_shape.reset_cache()


class FakeGateway:
    def __init__(self, path: str, columns: list[str]):
        self.path = path
        self.columns = columns
        self.calls = 0

    def query_dataset(self, dataset_id, params=None):
        self.calls += 1
        return {
            "dataset_id": dataset_id,
            "rows": [{c: 1 for c in self.columns}],
            "meta": {"source_path": self.path, "mode": "local_sample"},
        }


def _parquet(tmp_path: Path) -> str:
    path = tmp_path / "panel.parquet"
    pd.DataFrame(
        {"date": ["2020-01", "2020-02", "2020-03"], "value": [1.0, 2.0, 3.0]}
    ).to_parquet(path, index=False)
    return str(path)


def test_row_count_and_extent_come_from_the_file(tmp_path: Path):
    gw = FakeGateway(_parquet(tmp_path), ["date", "value"])
    shape = dataset_shape.measure_shape(gw, "panel", {"time_field": "date"})
    assert shape["row_count"] == 3
    assert shape["column_count"] == 2
    assert shape["earliest"] == "2020-01"
    assert shape["latest"] == "2020-03"


def test_facts_line_states_it_is_measured(tmp_path: Path):
    gw = FakeGateway(_parquet(tmp_path), ["date", "value"])
    lines = dataset_shape.shape_facts_lines(
        gw, [{"dataset_id": "panel", "local_ready": True}], {"panel": {"time_field": "date"}}
    )
    assert len(lines) == 1
    assert "3 rows" in lines[0]
    assert "2020-01 to 2020-03" in lines[0]
    assert "(measured)" in lines[0]


def test_rows_not_held_locally_are_not_probed(tmp_path: Path):
    gw = FakeGateway(_parquet(tmp_path), ["date", "value"])
    lines = dataset_shape.shape_facts_lines(gw, [{"dataset_id": "panel", "local_ready": False}])
    assert lines == []
    assert gw.calls == 0


def test_a_failing_probe_is_silent():
    class Broken:
        def query_dataset(self, *_a, **_k):
            raise RuntimeError("engine down")

    assert dataset_shape.measure_shape(Broken(), "panel") is None
    assert dataset_shape.shape_facts_lines(Broken(), [{"dataset_id": "panel", "local_ready": True}]) == []


def test_missing_parquet_yields_no_invented_numbers():
    gw = FakeGateway("/nonexistent/none.parquet", ["date"])
    shape = dataset_shape.measure_shape(gw, "panel", {"time_field": "date"})
    assert shape is None or shape.get("row_count") is None
