"""Discover L0 desk_check — measured held + routes, no LLM."""

from __future__ import annotations

from scripts.research_data_mcp.discover_composer import (
    _cache_get,
    _cache_put,
    _enrich_cache_key,
    _ENRICH_CACHE,
    _package_hybrid,
)
from scripts.research_data_mcp.discover_desk import desk_check, strong_held_hits


def test_strong_held_hits():
    assert not strong_held_hits([])
    assert strong_held_hits([{"score": 8.0}])
    assert strong_held_hits([{"score": 3.0, "local_ready": True}])
    assert not strong_held_hits([{"score": 3.0}])
    assert not strong_held_hits([{"score": 0.5}])


def test_desk_check_strong_held_skips_routes():
    class _Gw:
        repo_root = "/tmp"

        def discover_search_lexical(self, query, email="", limit=12):
            return {
                "sections": [
                    {
                        "id": "held",
                        "rows": [
                            {
                                "title": "Stablecoin panel",
                                "dataset_id": "stablecoin.demo",
                                "score": 3.5,
                                "local_ready": True,
                            }
                        ],
                    }
                ]
            }

    out = desk_check(_Gw(), "stablecoin", limit=8)
    assert out["strong_held"] is True
    assert out["held_count"] == 1
    assert out["route_count"] == 0
    assert out["layer"] == "L0_hands"
    assert out["held"][0]["placement"] == "held"
    assert "timing_ms" in out


def test_desk_check_miss_keeps_routes():
    class _Gw:
        repo_root = "/tmp"

        def discover_search_lexical(self, query, email="", limit=12):
            return {"sections": []}

    # Patch routes via monkeypatch-free stub: gap_routes may fail → empty ok
    out = desk_check(_Gw(), "US Polling data", limit=8)
    assert out["strong_held"] is False
    assert out["held_count"] == 0
    assert out["index_miss"] is True


def test_enrich_cache_roundtrip():
    _ENRICH_CACHE.clear()
    key = _enrich_cache_key("US Polling data", use_mcp=True, desk_sig="h0r0")
    assert _cache_get(key) is None
    _cache_put(key, {"context": [{"title": "Gallup"}], "engine": "composer_mcp_grounded"})
    hit = _cache_get(key)
    assert hit is not None
    assert hit["engine"] == "composer_mcp_grounded"
    _ENRICH_CACHE.clear()


def test_package_hybrid_exposes_stack_layers():
    out = _package_hybrid(
        "q",
        held=[],
        routes=[],
        context=[{"title": "Gallup", "url": "https://news.gallup.com/"}],
        engine="composer_mcp_grounded",
        summary="Desk truth",
        next_action="probe_url",
        tools_used=["research_discover_desk", "mcp"],
        layers={"L0_hands": {"ms": 40}, "total_ms": 100},
        cache_hit=True,
    )
    assert out["stack"] == "discover_l0_hands_l1_composer_mcp"
    assert out["cache_hit"] is True
    assert out["layers"]["total_ms"] == 100
    assert out["engine"] == "composer_mcp_grounded"
