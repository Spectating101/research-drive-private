"""Registry access tiers with local bytes."""

from __future__ import annotations

from scripts.research_data_mcp.registry_access import QUERY_INSTANT, access_tier


def test_metadata_search_becomes_instant_when_local(tmp_path) -> None:
    root = tmp_path
    p = root / "stablecoin_skynet/data/harvest/projects"
    p.mkdir(parents=True)
    (p / "usdt.json").write_text("{}", encoding="utf-8")
    row = {
        "analysis_readiness": "sample_now_full_later",
        "backend": "local_json_glob",
        "local_path": "stablecoin_skynet/data/harvest/projects/*.json",
    }
    assert access_tier(row, repo_root=root) == QUERY_INSTANT
