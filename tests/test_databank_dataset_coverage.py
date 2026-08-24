"""Dataset-level coverage map with proxy paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def audit():
    from scripts.research_data_mcp.dataset_coverage import build_dataset_coverage_audit

    return build_dataset_coverage_audit(REPO)


def test_proxies_config_loads():
    path = REPO / "config/databank_coverage_proxies.json"
    assert path.is_file()
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert len(doc.get("capability_proxies") or []) >= 5
    assert "news.gdelt-asia" in (doc.get("collection_bulk_profiles") or {})


def test_refinitiv_pit_has_disk_coverage(audit):
    pit = next(d for d in audit["dataset_profiles"] if d["dataset_id"] == "refinitiv_index_membership_pit")
    assert pit.get("materialized") is True
    probe = pit.get("disk_probe") or {}
    assert probe.get("row_count", 0) > 0
    assert "index_pit_survivorship" in pit.get("research_capabilities", [])


def test_gdelt_collection_bulk_profile(audit):
    gdelt = next(c for c in audit["collection_profiles"] if c["partition_id"] == "news.gdelt-asia")
    bp = gdelt.get("bulk_profile") or {}
    assert "country_news_shocks" in bp.get("latent_capabilities", [])
    assert gdelt.get("instant_card_count", 0) <= 3


def test_proxy_us_prices_has_crsp_and_yfinance(audit):
    block = next(p for p in audit["proxy_coverage"] if p["id"] == "us_daily_prices")
    kinds = {p.get("source_id") or p.get("artifact") or p.get("dataset_id") for p in block["paths"]}
    assert "crsp_moveit" in kinds
    assert any("daily_alpha_panel" in str(k) for k in kinds)


def test_synthesis_profiles_linked(audit):
    assert len(audit.get("synthesis_profiles") or []) >= 2
    crypto = next(p for p in audit["proxy_coverage"] if p["id"] == "crypto_onchain")
    assert any(p.get("recipe_id") == "stablecoin_trust_engagement" for p in crypto["paths"])
