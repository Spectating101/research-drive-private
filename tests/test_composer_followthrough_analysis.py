"""Composer follow-through pipes — bounded analyze + hydrate helpers."""

from __future__ import annotations

from scripts.research_data_mcp.composer_followthrough_analysis import (
    resolve_analyze_handle,
    run_bounded_analyze,
)
from scripts.research_data_mcp.registry_access import QUERY_INSTANT, access_tier


def test_resolve_analyze_handle_dataset() -> None:
    assert resolve_analyze_handle(dataset_id="gdelt_asia_daily_country_panel") == "dataset:gdelt_asia_daily_country_panel"


def test_access_tier_sample_when_local(tmp_path) -> None:
    root = tmp_path
    d = root / "data_lake/twse"
    d.mkdir(parents=True)
    (d / "snap.json").write_text('{"ticker":"2330"}', encoding="utf-8")
    row = {
        "analysis_readiness": "sample_now_full_later",
        "backend": "local_json_glob",
        "local_path": "data_lake/twse/*.json",
    }
    assert access_tier(row, repo_root=root) == QUERY_INSTANT





def test_run_bounded_analyze_no_handle() -> None:
    from unittest.mock import MagicMock

    handlers = MagicMock()
    out = run_bounded_analyze(handlers, query="stats", handle="")
    assert out.get("skipped") is True
