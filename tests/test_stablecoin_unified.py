"""Tests for Skynet + Etherscan unified stablecoin dataset."""

from __future__ import annotations

import json
from pathlib import Path

from stablecoin_skynet.community_summary import load_community_summaries
from stablecoin_skynet.unified_dataset import (
    build_unified_dataset,
    extract_skynet_eth_addresses,
    extract_skynet_primary_eth,
    load_etherscan_index,
    parse_money,
    parse_skynet_project,
)


def test_extract_primary_ethereum_from_eth_prefix():
    data = {
        "endpoints": {
            "info": {
                "project": {
                    "primaryTokenContractAddress": "eth:0xdac17f958d2ee523a2206206994597c13d831ec7",
                    "allAddress": ["arbitrum-one:0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9"],
                }
            }
        }
    }
    assert extract_skynet_primary_eth(data) == "0xdac17f958d2ee523a2206206994597c13d831ec7"
    addrs = extract_skynet_eth_addresses(data)
    assert addrs[0] == "0xdac17f958d2ee523a2206206994597c13d831ec7"


def test_parse_money_and_unified_join(tmp_path: Path):
    skynet_dir = tmp_path / "skynet"
    skynet_dir.mkdir()
    (skynet_dir / "tether.json").write_text(
        json.dumps(
            {
                "slug": "tether",
                "harvested_at": "2026-01-01T00:00:00Z",
                "endpoints": {
                    "info": {
                        "project": {
                            "name": "Tether",
                            "primaryTokenContractAddress": "eth:0xdac17f958d2ee523a2206206994597c13d831ec7",
                            "skynetScore": {"score": 93.0},
                        }
                    },
                    "website_scan": {"website": "https://tether.to"},
                    "pulses": [{"id": 1}],
                },
            }
        ),
        encoding="utf-8",
    )

    scrape_root = tmp_path / "scrapes" / "job1"
    tokens = scrape_root / "tokens"
    tokens.mkdir(parents=True)
    (tokens / "0xdac17f958d2ee523a2206206994597c13d831ec7.json").write_text(
        json.dumps(
            {
                "address": "0xdac17f958d2ee523a2206206994597c13d831ec7",
                "listing": {
                    "symbol": "USDT",
                    "name": "Tether USD (USDT)",
                    "rank": "1",
                    "holders": "1000 1.2%",
                    "onchain_market_cap": "$100",
                },
                "detail": {"decimals": "6", "links": {"website": "https://tether.to"}},
            }
        ),
        encoding="utf-8",
    )

    rows, manifest = build_unified_dataset(skynet_harvest_dir=skynet_dir, scrapes_root=tmp_path / "scrapes")
    assert manifest["counts"]["both_sources"] == 1
    assert rows[0]["join_method"] == "ethereum_address"
    assert rows[0]["etherscan_symbol"] == "USDT"
    assert rows[0]["etherscan_holders"] == 1000
    assert parse_money("$1,234.56") == 1234.56


def test_parse_skynet_project_from_repo_fixture():
    path = Path("stablecoin_skynet/data/harvest_20260622T132438Z/projects/tether.json")
    if not path.exists():
        return
    row = parse_skynet_project(path)
    assert row["primary_ethereum_address"] == "0xdac17f958d2ee523a2206206994597c13d831ec7"


def test_community_summary_from_repo():
    root = Path("stablecoin_skynet/data/community")
    if not root.exists():
        return
    summaries = load_community_summaries(root)
    assert "tether" in summaries
    assert summaries["tether"].get("google_trends_peak") is not None


def test_load_etherscan_index_from_repo():
    root = Path("data_lake/spectator_engine/scrapes")
    if not root.exists():
        return
    idx = load_etherscan_index(root)
    assert "0xdac17f958d2ee523a2206206994597c13d831ec7" in idx
