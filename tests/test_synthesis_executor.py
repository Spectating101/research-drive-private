"""Bounded synthesis execution must materialise a real local asset, never code."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    pd.DataFrame(
        {
            "week": ["2024-01", "2024-01", "2024-02"],
            "asset": ["USDT", "USDC", "USDT"],
            "score": [1.0, 2.0, 3.0],
        }
    ).to_csv(tmp_path / "data/input.csv", index=False)
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "input_panel", "local_path": "data/input.csv"}]}),
        encoding="utf-8",
    )
    return tmp_path


def test_execute_materialises_bounded_local_aggregate(tmp_path: Path):
    from scripts.research_data_mcp.synthesis_executor import execute

    result = execute(
        _repo(tmp_path),
        "job-1",
        {
            "thread_id": "thread-1",
            "execution_spec": {
                "input_dataset_id": "input_panel",
                "output_dataset_id": "synthesis_weekly_asset_score",
                "group_by": ["week"],
                "metrics": [{"function": "mean", "column": "score", "as": "mean_score"}],
            },
        },
    )
    path = tmp_path / result["materialized"]["files"][0]["path"]
    assert path.is_file()
    output = pd.read_parquet(path)
    assert output.to_dict("records") == [
        {"week": "2024-01", "mean_score": 1.5},
        {"week": "2024-02", "mean_score": 3.0},
    ]


def test_execute_rejects_unbounded_or_missing_columns(tmp_path: Path):
    from scripts.research_data_mcp.synthesis_executor import execute, validate_execution_spec

    with pytest.raises(ValueError, match="metrics only support"):
        validate_execution_spec(
            {
                "input_dataset_id": "input_panel",
                "output_dataset_id": "synthesis_bad",
                "group_by": [],
                "metrics": [{"function": "eval", "as": "bad"}],
            }
        )

    with pytest.raises(ValueError, match="output_dataset_id"):
        validate_execution_spec(
            {
                "input_dataset_id": "input_panel",
                "output_dataset_id": "../../collision",
                "group_by": [],
                "metrics": [{"function": "count", "as": "rows"}],
            }
        )
    with pytest.raises(ValueError, match="missing columns"):
        execute(
            _repo(tmp_path),
            "job-2",
            {
                "execution_spec": {
                    "input_dataset_id": "input_panel",
                    "output_dataset_id": "synthesis_bad",
                    "group_by": ["not_a_column"],
                    "metrics": [{"function": "count", "as": "rows"}],
                }
            },
        )


def test_execute_applies_gated_filter_transform(tmp_path: Path):
    from scripts.research_data_mcp.synthesis_executor import execute

    result = execute(
        _repo(tmp_path),
        "job-filter",
        {
            "thread_id": "thread-1",
            "execution_spec": {
                "input_dataset_id": "input_panel",
                "output_dataset_id": "synthesis_usdt_only",
                "transforms": [
                    {"op": "filter", "column": "asset", "cmp": "eq", "value": "USDT"},
                    {"op": "select", "columns": ["week", "asset", "score"]},
                ],
                "group_by": ["week"],
                "metrics": [{"function": "sum", "column": "score", "as": "score_sum"}],
            },
        },
    )
    output = __import__("pandas").read_parquet(tmp_path / result["materialized"]["files"][0]["path"])
    assert output.to_dict("records") == [
        {"week": "2024-01", "score_sum": 1.0},
        {"week": "2024-02", "score_sum": 3.0},
    ]


def test_execute_hydrates_missing_local_via_registry(tmp_path: Path, monkeypatch):
    """When local file is absent but hydrate restores it, execute continues."""
    from scripts.research_data_mcp import synthesis_executor as se

    repo = _repo(tmp_path)
    target = repo / "data/input.csv"
    target.unlink()

    def fake_hydrate(repo_root, source, *, dry_run=False):
        import pandas as pd

        pd.DataFrame({"week": ["2024-01"], "asset": ["USDT"], "score": [9.0]}).to_csv(
            repo_root / "data/input.csv", index=False
        )
        return {"ok": True, "restored": True}

    monkeypatch.setattr(se, "ensure_registry_local_bytes", fake_hydrate, raising=False)
    # patch the import site used inside _ensure_local_file
    import scripts.research_data_mcp.registry_hydrate as rh

    monkeypatch.setattr(rh, "ensure_registry_local_bytes", fake_hydrate)

    result = se.execute(
        repo,
        "job-hydrate",
        {
            "execution_spec": {
                "input_dataset_id": "input_panel",
                "output_dataset_id": "synthesis_hydrated",
                "group_by": [],
                "metrics": [{"function": "count", "as": "rows"}],
            }
        },
    )
    assert result["rows"] == 1


def test_validate_rejects_unknown_transform():
    from scripts.research_data_mcp.synthesis_executor import validate_execution_spec
    import pytest

    with pytest.raises(ValueError, match="unsupported transform"):
        validate_execution_spec(
            {
                "input_dataset_id": "input_panel",
                "output_dataset_id": "synthesis_bad_transform",
                "transforms": [{"op": "sql", "query": "drop table"}],
                "group_by": [],
                "metrics": [{"function": "count", "as": "rows"}],
            }
        )


def test_read_frame_sec_company_tickers_shape(tmp_path: Path):
    """SEC company_tickers is {idx: {cik_str,ticker,title}} — must not transpose wide."""
    import json
    from scripts.research_data_mcp.synthesis_executor import _read_frame

    path = tmp_path / "company_tickers.json"
    path.write_text(
        json.dumps(
            {
                "0": {"cik_str": 1, "ticker": "AAA", "title": "A"},
                "1": {"cik_str": 2, "ticker": "BBB", "title": "B"},
            }
        ),
        encoding="utf-8",
    )
    frame = _read_frame(path)
    assert list(frame.columns) == ["cik_str", "ticker", "title"]
    assert len(frame) == 2
