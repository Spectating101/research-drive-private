#!/usr/bin/env python3
"""Unit tests for AI-crafted generic collect plans (no vendor product modules)."""

from __future__ import annotations

import pytest

from scripts.research_data_mcp.craft_collect import (
    build_crafted_proposal,
    craft_collect_plan,
    is_forbidden_product_id,
    validate_generic_plan,
)


def test_craft_skynet_target_is_generic_scrape_not_skynet_module():
    out = craft_collect_plan(
        research_need="Download CertiK Skynet stablecoin leaderboard for taxonomy research",
        url="https://skynet.certik.com/leaderboards/stablecoin",
    )
    plan = out["plan"]
    assert plan["job_type"] in {"scraper_run", "http_manifest", "source_probe"}
    assert plan["pipeline"] == "custom"
    assert plan["crafted"] is True
    assert plan["job_type"] != "skynet_stablecoin_harvest"
    assert "skynet_stablecoin" not in str(plan.get("script_key") or "")
    if plan["job_type"] == "scraper_run":
        assert plan.get("script_key") == "generic_url_scrape"


def test_craft_direct_json_uses_http_manifest():
    out = craft_collect_plan(
        research_need="SEC company tickers",
        url="https://www.sec.gov/files/company_tickers.json",
    )
    assert out["plan"]["job_type"] == "http_manifest"
    assert out["plan"]["pipeline"] == "custom"


def test_validate_rejects_named_vendor_pipeline():
    with pytest.raises(ValueError):
        validate_generic_plan(
            {
                "job_type": "scraper_run",
                "script_key": "skynet_stablecoin_harvest",
                "url": "https://example.com",
            }
        )


def test_enforce_submit_rejects_vendor_before_queue():
    from scripts.research_data_mcp.craft_collect import enforce_submit_doctrine

    with pytest.raises(ValueError, match="named vendor"):
        enforce_submit_doctrine(
            {
                "job_type": "scraper_run",
                "script_key": "skynet_stablecoin_harvest",
                "url": "https://example.com",
                "launchable": True,
            }
        )


def test_enforce_submit_allows_archive_upload():
    from scripts.research_data_mcp.craft_collect import enforce_submit_doctrine

    plan = enforce_submit_doctrine(
        {"job_type": "archive_upload", "local_path": "/tmp/x", "launchable": True}
    )
    assert plan["job_type"] == "archive_upload"
    assert plan.get("crafted") is not True


def test_forbidden_product_ids():
    assert is_forbidden_product_id("skynet_stablecoin_harvest")
    assert is_forbidden_product_id("opensea_nft_metadata_layer")
    assert is_forbidden_product_id("ethereum_usdt_rpc_pilot")
    assert not is_forbidden_product_id("http_manifest")
    assert not is_forbidden_product_id("generic_url_scrape")


def test_discover_proposal_embeds_collect_plan():
    proposal = build_crafted_proposal(
        research_need="Land public NFT marketplace metadata",
        url="https://example.com/nft-api/collections.json",
    )
    assert proposal["routes"]
    assert proposal["routes"][0]["collect_plan"]["pipeline"] == "custom"
    assert proposal["recommended_route_id"] == "craft_primary"


def test_craft_api_host_prefers_http_manifest():
    out = craft_collect_plan(
        research_need="OpenAlex works about stablecoins",
        url="https://api.openalex.org/works?search=stablecoin&per-page=5",
    )
    assert out["plan"]["job_type"] == "http_manifest"


def test_craft_coingecko_api_prefers_http_manifest():
    out = craft_collect_plan(
        research_need="CoinGecko ping",
        url="https://api.coingecko.com/api/v3/ping",
    )
    assert out["plan"]["job_type"] == "http_manifest"
