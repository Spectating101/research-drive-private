"""Ranked procurement search — vault/dictionary first."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.research_data_mcp.procurement_search import (
    datacite_supplement_queries,
    looks_like_index_miss,
    score_row,
    smart_search,
)


def test_datacite_supplement_is_query_only() -> None:
    assert datacite_supplement_queries("climate calibration ridge regression") == [
        "climate calibration ridge regression"
    ]


def test_looks_like_index_miss_local_ready() -> None:
    candidates = [
        {
            "title": "Example panel",
            "dataset_id": "example_panel",
            "score": 8.0,
            "local_ready": True,
        },
    ]
    assert not looks_like_index_miss("example panel query", candidates, top_dl=8.0)


def test_looks_like_index_miss_empty() -> None:
    assert looks_like_index_miss("query", [], top_dl=0.0)


def test_score_prefers_local_ready_registry() -> None:
    local = {
        "kind": "registry_dataset",
        "dataset_id": "example_panel",
        "title": "Example panel",
        "local_ready": True,
        "procureability": {"can_collect": True},
    }
    remote = {
        "kind": "registry_dataset",
        "dataset_id": "other_panel",
        "title": "Other",
        "local_ready": False,
        "procureability": {"can_collect": True},
    }
    assert score_row(local, "example panel query") > score_row(remote, "example panel query")


def test_smart_search_strong_local_uses_registry_only() -> None:
    gw = MagicMock()
    gw.repo_root = Path(__file__).resolve().parents[1]
    local_cands = [
        {
            "index": 1,
            "kind": "registry_dataset",
            "dataset_id": "procured_src_c8c0f733ac8d",
            "title": "BTS DB1B Market 2024 Q1",
            "collect_via": "local_open",
            "local_ready": True,
            "score": 8.5,
            "procureability_label": "On disk",
        }
    ]
    with patch(
        "scripts.research_data_mcp.procurement_fast.local_search",
        return_value={
            "candidates": local_cands,
            "sources": ["registry", "local"],
            "index_miss": False,
            "strong_local_hit": True,
            "weak_match": False,
            "top_score": 8.5,
        },
    ):
        out = smart_search(gw, "historical US domestic flight ticket price", limit=6)
    assert out.get("strong_local_hit") is True
    assert out["candidates"][0]["dataset_id"] == "procured_src_c8c0f733ac8d"
    assert out["judgment"]["engine"] == "local_catalog"


def test_smart_search_index_miss_no_magic_auto() -> None:
    gw = MagicMock()
    gw.repo_root = Path(__file__).resolve().parents[1]
    with patch(
        "scripts.research_data_mcp.procurement_fast.local_search",
        return_value={
            "candidates": [],
            "sources": ["local"],
            "index_miss": True,
            "strong_local_hit": False,
            "top_score": 0.0,
        },
    ):
        out = smart_search(gw, "infant diaper consumer brand panel", limit=4)

    assert out.get("index_miss") is True
    assert not out["candidates"] or out["candidates"][0].get("collect_via") != "magic"
    assert out["judgment"]["engine"] == "local_catalog"
