#!/usr/bin/env python3
"""Deterministic Discover relevance contract — capability evidence, not weak lexical hits."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DRIVE = REPO / "drive"

FINANCE_DIRECT_IDS = frozenset(
    {
        "sec_edgar",
        "yfinance_public",
        "capital_iq_compustat",
        "lseg_edp",
        "lseg_desktop_rescue",
        "wrds_crsp_compustat",
        "crsp_moveit",
    }
)

STABLECOIN_EVIDENCE_IDS = frozenset({"ethereum_onchain", "bigquery_public", "coingecko"})


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return DRIVE


def _ids(out: dict) -> set[str]:
    return {
        str(row.get("source_id") or row.get("connector_id") or "").strip().lower()
        for row in (out.get("results") or [])
        if str(row.get("source_id") or row.get("connector_id") or "").strip()
    }


@pytest.mark.parametrize("semantic", [True, False])
def test_us_polling_does_not_propose_finance_providers(repo_root: Path, semantic: bool) -> None:
    from scripts.research_data_mcp.discover_source_search import search_discover_sources

    out = search_discover_sources(
        repo_root,
        "US polling data",
        limit=12,
        semantic=semantic,
        prefer_embeddings=False,
        live=False,
    )
    ids = _ids(out)
    assert not (ids & FINANCE_DIRECT_IDS), ids
    assert out.get("relevance_miss") is True or out.get("no_supported_route") is True
    assert int(out.get("total") or 0) == len(out.get("results") or [])
    # Do not invent a polling provider route.
    assert not any(
        "poll" in str(g.get("concept_id") or "").lower() for g in (out.get("source_groups") or [])
    )


@pytest.mark.parametrize("semantic", [True, False])
def test_stablecoin_incidents_evidence_or_explicit_no_route(repo_root: Path, semantic: bool) -> None:
    from scripts.research_data_mcp.discover_source_search import search_discover_sources

    out = search_discover_sources(
        repo_root,
        "stablecoin incidents",
        limit=12,
        semantic=semantic,
        prefer_embeddings=False,
        live=False,
    )
    ids = _ids(out)
    groups = out.get("source_groups") or []
    group_ids = {str(g.get("concept_id") or "") for g in groups}
    member_ids = {
        sid
        for g in groups
        for sid in (g.get("source_ids") or [])
    }

    if out.get("no_supported_route"):
        # Honest miss must still surface relevant catalog alternatives — not silence.
        alts = out.get("alternatives") or []
        assert alts or groups, out
        alt_sources = {
            sid
            for item in (alts + groups)
            for sid in (item.get("source_ids") or [])
        }
        assert alt_sources & STABLECOIN_EVIDENCE_IDS or "gdelt" in alt_sources, out
        assert not (ids & FINANCE_DIRECT_IDS)
    else:
        assert ids & STABLECOIN_EVIDENCE_IDS, ids
        assert "stablecoin_onchain_transactions" in group_ids
        assert member_ids & STABLECOIN_EVIDENCE_IDS
        # NFT specialty must not ride onchain_crypto alone for stablecoin queries.
        assert "nft_opensea" not in ids
        # No invented incidents access claim on evidence rows.
        for row in out.get("results") or []:
            evidence = row.get("relevance_evidence") or []
            assert evidence, row
            notes = " ".join(
                str(g.get("notes") or "") for g in groups if g.get("concept_id") == "stablecoin_onchain_transactions"
            ).lower()
            assert "incident" in notes  # honest limitation called out


@pytest.mark.parametrize("semantic", [True, False])
def test_known_finance_query_surfaces_sec_edgar(repo_root: Path, semantic: bool) -> None:
    from scripts.research_data_mcp.discover_source_search import search_discover_sources

    out = search_discover_sources(
        repo_root,
        "sec edgar filings",
        limit=12,
        semantic=semantic,
        prefer_embeddings=False,
        live=False,
    )
    ids = _ids(out)
    assert "sec_edgar" in ids
    assert out.get("relevance_miss") is not True
    assert out.get("no_supported_route") is not True
    top = (out.get("results") or [{}])[0]
    assert float(top.get("query_relevance") or 0) >= 1.25
    assert top.get("relevance_evidence"), top


@pytest.mark.parametrize(
    "query,concept_id,expected_sources",
    [
        ("MOPS Taiwan governance", "mops_taiwan_governance", {"mops_taiwan", "twse_official"}),
        ("GDELT news", "gdelt_news", {"gdelt"}),
        (
            "historical stablecoin on-chain transactions",
            "stablecoin_onchain_transactions",
            STABLECOIN_EVIDENCE_IDS,
        ),
    ],
)
def test_known_concepts_emit_source_groups(
    repo_root: Path,
    query: str,
    concept_id: str,
    expected_sources: set[str],
) -> None:
    from scripts.research_data_mcp.discover_source_search import search_discover_sources

    out = search_discover_sources(
        repo_root,
        query,
        limit=12,
        semantic=True,
        prefer_embeddings=False,
        live=False,
    )
    groups = out.get("source_groups") or []
    match = next((g for g in groups if g.get("concept_id") == concept_id), None)
    assert match is not None, groups
    assert set(match.get("source_ids") or []) & expected_sources
    assert match.get("supported") is True
    # Groups document catalog evidence only — no fabricated access flags.
    assert "access_granted" not in match
    assert "collection_ready" not in match


def test_candidate_key_identity_stable_across_relevance_gate(repo_root: Path) -> None:
    from scripts.research_data_mcp.discover_source_search import (
        _catalog_corpus,
        search_discover_sources,
    )

    corpus = {
        str(r.get("source_id") or ""): str(r.get("candidate_key") or "")
        for r in _catalog_corpus(repo_root, include_providers=True)
        if r.get("source_id") and r.get("candidate_key")
    }
    assert corpus.get("sec_edgar", "").startswith("source:")
    assert corpus.get("gdelt", "").startswith("source:")
    assert corpus.get("mops_taiwan", "").startswith("source:")
    assert corpus.get("ethereum_onchain", "").startswith("source:")

    out = search_discover_sources(
        repo_root,
        "sec edgar filings",
        limit=8,
        semantic=True,
        prefer_embeddings=False,
        live=False,
    )
    for row in out.get("results") or []:
        sid = str(row.get("source_id") or "")
        if sid in corpus:
            assert row.get("candidate_key") == corpus[sid], (sid, row.get("candidate_key"), corpus[sid])


def test_web_federation_reranks_polling_and_drops_finance_noise() -> None:
    from scripts.research_data_mcp.web_search import (
        min_web_relevance,
        rank_web_results_by_relevance,
        web_query_aspects,
    )

    query = "US polling data"
    aspects = web_query_aspects(query)
    assert aspects.get("geography")
    assert any("poll" in t for t in (aspects.get("topic") or []))
    raw = [
        {
            "title": "SEC EDGAR company filings bulk",
            "url": "https://doi.org/10.1/edgar",
            "source": "datacite",
            "snippet": "US securities filings dataset",
        },
        {
            "title": "American National Election Studies polling data",
            "url": "https://doi.org/10.2/anes-poll",
            "source": "datacite",
            "snippet": "US public opinion polling survey waves",
        },
        {
            "title": "Yahoo Finance daily bars",
            "url": "https://doi.org/10.3/yfinance",
            "source": "datacite",
            "snippet": "equity price panel",
        },
    ]
    ranked = rank_web_results_by_relevance(
        raw, query, min_relevance=min_web_relevance(query)
    )
    assert ranked
    assert "poll" in ((ranked[0].get("title") or "") + (ranked[0].get("snippet") or "")).lower()
    titles = " ".join(str(r.get("title") or "") for r in ranked).lower()
    assert "edgar" not in titles
    assert "yahoo" not in titles
    assert float(ranked[0]["query_relevance"]) >= 2.0


def test_live_candidates_marked_inspect_only(repo_root: Path) -> None:
    from scripts.research_data_mcp.discover_source_search import apply_source_relevance_gate

    rows = [
        {
            "kind": "live_candidate",
            "live_hit": True,
            "title": "American National Election Studies polling data",
            "label": "American National Election Studies polling data",
            "provider": "DataCite",
            "capabilities": ["doi_metadata"],
            "candidate_key": "doi:10.2/anes-poll",
            "access_mode": "live_connector",
            "subscription_status": "public",
        },
        {
            "kind": "live_candidate",
            "live_hit": True,
            "title": "Crystal structure CIF dump",
            "label": "Crystal structure CIF dump",
            "provider": "DataCite",
            "capabilities": ["doi_metadata"],
            "candidate_key": "doi:10.9/crystal",
        },
    ]
    kept, meta = apply_source_relevance_gate(rows, "US polling data", limit=8, corpus=[])
    assert kept, meta
    assert all(r.get("inspect_only") is True for r in kept)
    assert all(r.get("trust_tier") == "inspect_only" for r in kept)
    assert all("access_mode" not in r for r in kept)
    assert all("crystal" not in str(r.get("title") or "").lower() for r in kept)
