"""Tests for multi-source synthesis backend."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_data_mcp.synthesis.engine import (
    list_synthesis_profiles,
    run_synthesis,
    run_synthesis_pair,
)
from scripts.research_data_mcp.synthesis.registry_pair import metadata_overlap


def test_list_profiles_includes_skynet_etherscan() -> None:
    repo = Path(__file__).resolve().parents[1]
    payload = list_synthesis_profiles(repo)
    ids = {p["id"] for p in payload.get("profiles") or []}
    assert "skynet_etherscan_stablecoin" in ids


def test_metadata_overlap_grain_and_keys() -> None:
    left = {
        "dataset_id": "panel_a",
        "name": "Panel A",
        "grain": "country-day",
        "join_keys": ["country", "date"],
        "entity_fields": ["country"],
    }
    right = {
        "dataset_id": "panel_b",
        "name": "Panel B",
        "grain": "country-day",
        "join_keys": ["country", "as_of"],
        "entity_fields": ["country"],
    }
    out = metadata_overlap(left, right)
    assert out["grain_match"] is True
    assert "country" in out["shared_join_keys"]
    assert out["synthesis_viable"] is True
    assert out["overlap_pct"] >= 35


def test_registry_pair_describe_fn() -> None:
    repo = Path(__file__).resolve().parents[1]

    def describe(dataset_id: str) -> dict:
        return {
            "dataset_id": dataset_id,
            "name": dataset_id.replace("_", " ").title(),
            "grain": "entity-week" if "gdelt" in dataset_id else "entity",
            "join_keys": ["entity_id"],
            "entity_fields": ["entity_id"],
        }

    out = run_synthesis_pair(repo, "skynet_stablecoin_harvest", "gdelt_asia_daily_country_panel", describe_fn=describe)
    assert out["type"] == "registry_pair"
    assert out["summary"]["left_dataset_id"] == "skynet_stablecoin_harvest"


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "stablecoin_skynet/data/harvest_20260622T132438Z/projects").is_dir(),
    reason="Skynet harvest fixture not present",
)
def test_skynet_etherscan_synthesis_run() -> None:
    repo = Path(__file__).resolve().parents[1]
    result = run_synthesis(repo, "skynet_etherscan_stablecoin", preview_limit=5, gap_limit=5)
    assert result["type"] == "skynet_etherscan"
    assert result["summary"]["both_count"] >= 0
    panel = repo / result["artifacts"]["panel_csv"]
    assert panel.is_file()
    pointer = repo / result["artifacts"]["latest_pointer"]
    assert pointer.is_file()
    pointer_data = json.loads(pointer.read_text(encoding="utf-8"))
    assert pointer_data["profile_id"] == "skynet_etherscan_stablecoin"
