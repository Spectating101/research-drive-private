"""Lane B faculty profiling — procurement recommendations and query expansion."""

from __future__ import annotations

from scripts.research_data_mcp.faculty_profile import (
    agent_research_context,
    default_search_query,
    expand_datacite_queries,
    procurement_recommendations,
    profile_score_adjustment,
    profile_summary,
    resolve_profile,
)


def _kong() -> dict:
    row = resolve_profile(email="drkong@saturn.yzu.edu.tw")
    assert row is not None
    return row


def test_procurement_recommendations_skip_vault_inventory() -> None:
    kong = _kong()
    recs = procurement_recommendations(kong)
    assert recs
    assert not any(r.get("family") == "lab_vault" for r in recs)
    assert all("drive_path" not in r for r in recs)
    assert any(r.get("family") == "lab_fintech_stack" for r in recs)
    assert any("OpenSea" in (r.get("dataset") or "") for r in recs)


def test_lab_fintech_stack_routes() -> None:
    kong = _kong()
    stack = [r for r in procurement_recommendations(kong) if r.get("family") == "lab_fintech_stack"]
    routes = {r.get("source_route") for r in stack}
    assert "vault" in routes
    assert "bigquery" in routes


def test_datacite_scope_queries_short_seeds() -> None:
    from scripts.research_data_mcp.faculty_profile import datacite_scope_queries

    seeds = datacite_scope_queries(_kong())
    assert any("momentum taiwan" in s for s in seeds)
    assert all(len(s.split()) <= 6 for s in seeds)


def test_profile_summary_intel_v2() -> None:
    summary = profile_summary(_kong())
    assert summary.get("profile_schema") == "v2_intel"
    assert summary.get("lab_fintech_stack")
    assert summary.get("datacite_scopes")
    assert summary.get("intel_sources", {}).get("google_scholar")
    clusters = summary.get("recommendation_clusters") or {}
    assert "vault" in clusters
    assert len(clusters.get("vault") or []) >= 4


def test_profile_summary_includes_lane_b_fields() -> None:
    summary = profile_summary(_kong())
    assert summary.get("default_search_query")
    assert "momentum" in summary["default_search_query"].lower() or "taiwan" in summary["default_search_query"].lower()
    assert summary.get("procurement_recommendations")
    assert summary.get("research_keywords")


def test_profile_summary_sanitizes_legacy_procurement_source() -> None:
    profile = dict(_kong())
    profile["preferred_sources"] = ["datacite", "magic_procure", "datacite"]
    summary = profile_summary(profile)
    assert summary["preferred_sources"] == ["datacite", "yzu_submit_job"]


def test_expand_datacite_queries_uses_profile() -> None:
    kong = _kong()
    bare = expand_datacite_queries("dataset", kong)
    assert any("momentum taiwan" in q for q in bare)
    assert any("nft" in q.lower() or "non-fungible" in q.lower() for q in bare)


def test_profile_score_boosts_taiwan_momentum_row() -> None:
    kong = _kong()
    row = {
        "kind": "datacite",
        "title": "Taiwan stock market momentum machine learning panel",
        "source": "datacite",
        "collect_via": "datacite",
    }
    noise = {
        "kind": "datacite",
        "title": "Arctic sea ice thickness measurements",
        "source": "datacite",
        "collect_via": "datacite",
    }
    q = "momentum replication"
    assert profile_score_adjustment(row, q, kong) > profile_score_adjustment(noise, q, kong)


def test_agent_research_context_mentions_keywords() -> None:
    ctx = agent_research_context(_kong())
    assert "Prof." in ctx or "Kong" in ctx
    assert "momentum" in ctx.lower() or "taiwan" in ctx.lower()
    assert "vault" in ctx.lower()
