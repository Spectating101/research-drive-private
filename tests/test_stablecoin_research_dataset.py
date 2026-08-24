"""Tests for curated stablecoin research dataset builder."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from stablecoin_skynet.code_security import build_code_security_panel
from stablecoin_skynet.gdelt_panel import scan_entity_evidence_daily
from stablecoin_skynet.research_dataset import (
    build_research_dataset,
    publish_research_dataset,
    rollup_engagement_daily,
    rollup_engagement_weekly,
)


def test_code_security_panel_covers_leaderboard():
    harvest = Path("stablecoin_skynet/data/harvest_20260622T132438Z/projects")
    if not harvest.is_dir():
        return
    rows = build_code_security_panel(harvest)
    assert len(rows) == 71
    scored = [r for r in rows if r.get("code_security_score") is not None]
    assert len(scored) >= 64
    tether = next(r for r in rows if r["entity_id"] == "tether")
    assert tether["governance_chains_scanned"] >= 1


def test_engagement_daily_weekly_from_repo():
    community = Path("stablecoin_skynet/data/community")
    if not community.is_dir():
        return
    daily = rollup_engagement_daily(community, leaderboard_slugs={"tether"})
    weekly = rollup_engagement_weekly(community, leaderboard_slugs={"tether"})
    assert len(daily) > 200
    assert len(weekly) > 40
    assert "community_growth_index" in daily[0]


def test_gdelt_entity_scan_on_sample(tmp_path: Path):
    overlay = tmp_path / "overlay" / "win1"
    overlay.mkdir(parents=True)
    evidence = overlay / "crypto_event_evidence.csv.gz"
    with gzip.open(evidence, "wt", encoding="utf-8", newline="") as handle:
        handle.write(
            "date,country_iso3,source_common_name,document_identifier,asset_topics,event_topics,shock_hints,tone_avg\n"
            "2024-01-01,USA,cointelegraph.com,https://example.com/tether-usdt-stablecoin-review,stablecoin,security_exploit,, -2.5\n"
        )
    aliases = tmp_path / "aliases.json"
    aliases.write_text(
        json.dumps(
            {
                "entries": [
                    {"entity_id": "tether", "patterns": ["tether", "usdt"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    rows = scan_entity_evidence_daily(overlay.parent, aliases_path=aliases, entity_ids={"tether"})
    assert len(rows) == 1
    assert rows[0]["gdelt_entity_mention_rows"] == 1
    assert rows[0]["gdelt_entity_security_exploit_rows"] == 1


def test_github_merge_weekly():
    from stablecoin_skynet.github_activity_panel import merge_github_weekly

    spine = [{"entity_id": "fraxfinance", "week": "2024-W01", "community_growth_index": 1.0}]
    github = [
        {
            "entity_id": "fraxfinance",
            "week": "2024-W01",
            "repo_full_name": "FraxFinance/frax-solidity",
            "github_commit_count": "5",
            "github_security_keyword_commit_count": "1",
            "github_activity_index": "3.0",
        }
    ]
    merged = merge_github_weekly(spine, github)
    assert merged[0]["github_commit_count"] == "5"
    assert merged[0]["github_repo_full_name"] == "FraxFinance/frax-solidity"


def test_build_research_dataset_v3_from_repo():
    skynet = Path("stablecoin_skynet/data/harvest_20260622T132438Z/projects")
    community = Path("stablecoin_skynet/data/community")
    if not (skynet.is_dir() and community.is_dir()):
        return
    manifest, tables = build_research_dataset(
        skynet_harvest_dir=skynet,
        scrapes_root=Path("data_lake/spectator_engine/scrapes"),
        community_dir=community,
        include_gdelt=False,
        include_external=False,
    )
    assert manifest["dataset_version"] == "v3"
    assert manifest["counts"]["leaderboard_entities"] == 71
    assert len(tables["research_weekly"]) >= 18000
    assert all(r["week"] >= "2021-W24" for r in tables["research_weekly"][:10])
    assert len(tables["code_security"]) == 71


def test_publish_writes_v3_package(tmp_path: Path):
    skynet = Path("stablecoin_skynet/data/harvest_20260622T132438Z/projects")
    community = Path("stablecoin_skynet/data/community")
    if not (skynet.is_dir() and community.is_dir()):
        return
    out = tmp_path / "dataset"
    manifest = publish_research_dataset(
        out,
        skynet_harvest_dir=skynet,
        scrapes_root=tmp_path / "empty_scrapes",
        community_dir=community,
        include_gdelt=False,
        include_external=False,
    )
    assert manifest["dataset_version"] == "v3"
    assert (out / "panel_weekly.csv").is_file()
    assert (out / "panels" / "research_panel_weekly.csv").is_file()
    assert (out / "factors" / "skynet_governance_chains.csv").is_file()
    assert (out / "validation" / "validation_event_studies.csv").is_file()
    assert (out / "validation" / "validation_missingness_handoff_top10.csv").is_file()
    assert (out / "validation" / "validation_missingness_full_width_top10.csv").is_file()
    for name in [
        "code_security_snapshot.csv",
        "engagement_panel_daily.csv",
        "research_panel_weekly.csv",
        "METHOD.md",
    ]:
        assert (out / "panels" / name).is_file() or (out / "factors" / name).is_file() or (out / "reference" / name).is_file(), name


def test_defillama_entity_map_from_repo():
    from stablecoin_skynet.defillama_panel import build_entity_defillama_map

    skynet = Path("stablecoin_skynet/data/harvest_20260622T132438Z/projects")
    community = Path("stablecoin_skynet/data/community")
    if not (skynet.is_dir() and community.is_dir()):
        return
    from stablecoin_skynet.research_dataset import build_entities
    from stablecoin_skynet.unified_dataset import build_unified_dataset

    unified_rows, _ = build_unified_dataset(
        skynet_harvest_dir=skynet,
        scrapes_root=Path("data_lake/spectator_engine/scrapes"),
        community_dir=community,
    )
    entities = [e for e in build_entities(unified_rows) if e.get("in_skynet_leaderboard")]
    mapping = build_entity_defillama_map(entities)
    assert len(mapping) >= 60
    assert "tether" in mapping
    assert mapping["tether"]["defillama_id"] in (1, "1")
