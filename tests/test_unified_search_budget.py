"""Unified search wall-clock budget."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import scripts.research_data_mcp.unified_search as unified_search_mod
from scripts.research_data_mcp.unified_search import _run_remote_layers, unified_search


def test_run_remote_layers_respects_budget(monkeypatch):
    def slow_datacite(*_args, **_kwargs):
        time.sleep(0.35)
        return (
            [{"kind": "datacite", "id": "1", "title": "slow"}],
            {"id": "datacite_vault", "label": "DataCite", "count": 1, "rows": []},
        )

    def fast_hf(*_args, **_kwargs):
        return (
            [{"kind": "huggingface", "id": "hf1", "title": "fast"}],
            {"id": "huggingface", "label": "HF", "count": 1, "rows": []},
        )

    def empty_scrape(*_args, **_kwargs):
        return ([], None)

    monkeypatch.setattr(unified_search_mod, "_build_datacite_layer", slow_datacite)
    monkeypatch.setattr(unified_search_mod, "_build_hf_layer", fast_hf)
    monkeypatch.setattr(unified_search_mod, "_build_scrape_layer", empty_scrape)

    merged, _sections, timed_out, _errors = _run_remote_layers(
        repo_root=MagicMock(),
        q="test",
        limit=4,
        include_hf=True,
        include_datacite=True,
        resolve_datacite=False,
        max_file_bytes=50_000_000,
        budget_seconds=0.15,
    )
    kinds = {row.get("kind") for row in merged}
    assert "huggingface" in kinds
    assert timed_out


def test_unified_search_returns_budget_metadata(monkeypatch):
    gateway = MagicMock()
    gateway.repo_root = MagicMock()
    gateway.list_datasets.return_value = {"datasets": []}
    gateway.search_catalog.return_value = {"rows": []}

    monkeypatch.setattr(
        unified_search_mod,
        "_run_remote_layers",
        lambda **_kwargs: ([], [], [], []),
    )

    out = unified_search(gateway, "mops", limit=4, budget_seconds=8.0)
    assert out["search_budget_seconds"] == 8.0
    assert isinstance(out.get("search_elapsed_seconds"), float)
    assert out.get("timed_out_layers") == []
