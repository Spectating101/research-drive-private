"""Tests for stablecoin dataset handoff fixes (research window, validation, naming)."""

from __future__ import annotations

from pathlib import Path

from stablecoin_skynet.defillama_panel import _unix_to_date
from stablecoin_skynet.handoff_validation import build_coverage_by_source
from stablecoin_skynet.research_window import RESEARCH_WEEK_MAX, RESEARCH_WEEK_MIN, filter_research_weeks, in_research_window
from stablecoin_skynet.unified_dataset import _is_noisy_etherscan_name, _pick_canonical_name


def test_unix_to_date_rejects_epoch():
    assert _unix_to_date(0) is None
    assert _unix_to_date(1609459200) == "2021-01-01"


def test_research_window_filter():
    rows = [
        {"entity_id": "tether", "week": "1970-W01"},
        {"entity_id": "tether", "week": "2021-W23"},
        {"entity_id": "tether", "week": RESEARCH_WEEK_MIN},
        {"entity_id": "tether", "week": RESEARCH_WEEK_MAX},
        {"entity_id": "tether", "week": "2026-W27"},
    ]
    filtered = filter_research_weeks(rows)
    assert len(filtered) == 2
    assert in_research_window("2021-W24")
    assert not in_research_window("1970-W01")
    assert not in_research_window("2026-W27")


def test_noisy_etherscan_name_detection():
    assert _is_noisy_etherscan_name("NFT | ERC-1155 | Address: 0xabc")
    assert not _is_noisy_etherscan_name("Binance USD")


def test_canonical_name_prefers_skynet():
    name, suspect = _pick_canonical_name(
        {
            "skynet_name": "Binance USD",
            "etherscan_name": "NFT | ERC-1155 | Address: 0xabc",
        }
    )
    assert name == "Binance USD"
    assert suspect is True


def test_coverage_by_source_has_incidents(tmp_path: Path):
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "entities.csv").write_text(
        "entity_id,canonical_name,in_skynet_leaderboard\nterrausd,TerraUSD,true\n",
        encoding="utf-8",
    )
    (root / "incidents.csv").write_text(
        "entity_id,event_date\nterrausd,2022-05-09\n",
        encoding="utf-8",
    )
    (root / "panels").mkdir()
    (root / "panels" / "research_panel_weekly.csv").write_text(
        "entity_id,week\nterrausd,2022-W19\n",
        encoding="utf-8",
    )
    (root / "reference").mkdir()
    (root / "reference" / "security_snapshot.csv").write_text(
        "entity_id,code_security_score,skynet_score\nterrausd,80,70\n",
        encoding="utf-8",
    )
    coverage = build_coverage_by_source(root)
    terrausd = next(r for r in coverage if r["entity_id"] == "terrausd")
    assert terrausd["has_incidents"] == 1
