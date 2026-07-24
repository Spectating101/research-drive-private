#!/usr/bin/env python3
"""Bounded procurement-intelligence relevance + structured discover replies."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parents[1]
DRIVE = REPO / "drive"

IRRELEVANT_LOCAL_IDS = frozenset(
    {
        "sec_edgar",
        "yfinance_public",
        "capital_iq_compustat",
        "lseg_edp",
        "wrds_crsp_compustat",
    }
)


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return DRIVE


def test_irrelevant_local_sources_suppressed_for_polling_query(repo_root: Path) -> None:
    from scripts.research_data_mcp.discover_source_search import search_discover_sources

    out = search_discover_sources(
        repo_root,
        "US polling data",
        limit=12,
        semantic=True,
        prefer_embeddings=False,
    )
    ids = {
        str(row.get("source_id") or row.get("connector_id") or "").strip().lower()
        for row in (out.get("results") or [])
    }
    assert not (ids & IRRELEVANT_LOCAL_IDS), ids
    assert out.get("relevance_miss") is True or out.get("index_miss") is True or not ids
    assert int(out.get("total") or 0) == len(out.get("results") or [])


def test_credible_local_source_still_surfaces(repo_root: Path) -> None:
    from scripts.research_data_mcp.discover_source_search import search_discover_sources

    out = search_discover_sources(
        repo_root,
        "sec edgar filings",
        limit=12,
        semantic=True,
        prefer_embeddings=False,
    )
    ids = {
        str(row.get("source_id") or "").strip().lower()
        for row in (out.get("results") or [])
    }
    assert "sec_edgar" in ids
    assert out.get("relevance_miss") is not True
    top = (out.get("results") or [{}])[0]
    assert float(top.get("query_relevance") or 0) >= 1.0


def test_external_catalogue_reranked_by_query_relevance() -> None:
    from scripts.research_data_mcp.web_search import (
        min_web_relevance,
        rank_web_results_by_relevance,
        web_query_aspects,
    )

    query = "US polling data"
    aspects = web_query_aspects(query)
    assert "us" in aspects.get("geography") or "usa" in aspects.get("geography")
    assert any("poll" in t for t in aspects.get("topic") or [])
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
        {
            "title": "Unrelated crystal structure deposit",
            "url": "https://doi.org/10.4/crystal",
            "source": "datacite",
            "snippet": "materials science CIF archive",
        },
    ]
    ranked = rank_web_results_by_relevance(
        raw, query, min_relevance=min_web_relevance(query)
    )
    assert ranked, "relevant polling hit should survive"
    assert "poll" in (ranked[0].get("title") or "").lower() or "poll" in (
        ranked[0].get("snippet") or ""
    ).lower()
    titles = " ".join(str(r.get("title") or "") for r in ranked).lower()
    assert "crystal structure" not in titles
    assert "edgar" not in titles
    assert all("query_relevance" in row for row in ranked)
    rels = [float(r["query_relevance"]) for r in ranked]
    assert rels == sorted(rels, reverse=True)
    assert float(ranked[0]["query_relevance"]) >= 2.0


def test_us_polling_rejects_irish_only_keeps_us_hit() -> None:
    """Geography is a required aspect: Irish-only polling must not pass 'US polling'."""
    from scripts.research_data_mcp.web_search import (
        min_web_relevance,
        rank_web_results_by_relevance,
        web_hit_relevance,
        web_query_aspects,
    )

    query = "US polling data"
    aspects = web_query_aspects(query)
    assert aspects.get("geography"), "US must remain a query geography term"
    assert aspects.get("topic"), "polling must remain a topic term"
    assert min_web_relevance(query) >= 2.0

    irish = {
        "title": "Irish National Election Study polling data",
        "url": "https://doi.org/10.1/ines-poll",
        "source": "datacite",
        "snippet": "Republic of Ireland public opinion polling survey waves",
    }
    us_hit = {
        "title": "American National Election Studies polling data",
        "url": "https://doi.org/10.2/anes-poll",
        "source": "zenodo_api",
        "snippet": "US public opinion polling survey microdata",
    }
    assert web_hit_relevance(irish, query) < min_web_relevance(query)
    assert web_hit_relevance(us_hit, query) >= min_web_relevance(query)

    ranked = rank_web_results_by_relevance(
        [irish, us_hit], query, min_relevance=min_web_relevance(query)
    )
    assert len(ranked) == 1
    assert "american" in (ranked[0].get("title") or "").lower()
    assert "irish" not in (ranked[0].get("title") or "").lower()
    assert "available" not in ranked[0]
    assert "access_mode" not in ranked[0]


def test_discover_sources_collects_across_providers_before_rerank(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Do not stop after the first provider fills max_results; pool then rerank."""
    from scripts.research_data_mcp import web_search

    calls: list[str] = []

    def _dc(q: str, n: int) -> list[dict[str, Any]]:
        calls.append("datacite")
        return [
            {
                "title": "Irish National Election Study polling data",
                "url": "https://doi.org/10.1/ines",
                "source": "datacite",
                "snippet": "Ireland public opinion polling",
            }
        ]

    def _zen(q: str, n: int) -> list[dict[str, Any]]:
        calls.append("zenodo_api")
        return [
            {
                "title": "American National Election Studies polling data",
                "url": "https://doi.org/10.2/anes",
                "source": "zenodo_api",
                "snippet": "US public opinion polling survey waves",
            }
        ]

    def _oa(q: str, n: int) -> list[dict[str, Any]]:
        calls.append("openalex")
        return []

    def _tav(repo: Path, q: str, n: int, *, live: bool = False) -> list[dict[str, Any]]:
        calls.append("tavily")
        return []

    def _ddg(q: str, n: int) -> list[dict[str, Any]]:
        calls.append("duckduckgo_html")
        return []

    def _ddgi(q: str, n: int) -> list[dict[str, Any]]:
        calls.append("duckduckgo_instant")
        return []

    monkeypatch.setattr(web_search, "_search_datacite", _dc)
    monkeypatch.setattr(web_search, "_search_zenodo_api", _zen)
    monkeypatch.setattr(web_search, "_search_openalex_api", _oa)
    monkeypatch.setattr(web_search, "_search_tavily", _tav)
    monkeypatch.setattr(web_search, "_search_duckduckgo_html", _ddg)
    monkeypatch.setattr(web_search, "_search_duckduckgo_instant", _ddgi)

    out = web_search.discover_sources(tmp_path, "US polling data", max_results=1, tavily_live=False)
    assert "datacite" in calls
    assert "zenodo_api" in calls, calls
    assert "openalex" in calls
    tried = out.get("sources_tried") or []
    assert "datacite" in tried and "zenodo_api" in tried
    rows = out.get("results") or []
    assert rows, out
    assert "american" in (rows[0].get("title") or "").lower()
    assert all("irish" not in (r.get("title") or "").lower() for r in rows)
    assert float(rows[0].get("query_relevance") or 0) >= 2.0
    assert int((out.get("relevance") or {}).get("candidates_before_gate") or 0) >= 2


def test_discover_chat_exposes_structured_candidates_and_routes(repo_root: Path) -> None:
    from scripts.research_data_mcp.desk_direct_turns import try_direct_discover_search_turn

    gateway = MagicMock()
    gateway.discover_source_search.return_value = {
        "query": "gdelt",
        "search_mode": "catalog",
        "results": [
            {
                "kind": "source",
                "source_id": "gdelt",
                "label": "GDELT",
                "title": "GDELT",
                "access_mode": "materialized_bulk",
                "candidate_key": "source:gdelt:gdelt",
                "query_relevance": 2.0,
            }
        ],
        "total": 1,
        "index_miss": False,
        "relevance_miss": False,
    }
    turn = try_direct_discover_search_turn(
        gateway,
        "discover source search for gdelt",
        {"rail_context": {}},
    )
    assert turn is not None
    ar = turn.action_result
    assert ar.get("action") == "discover_search"
    candidates = ar.get("candidates") or (ar.get("state_patch") or {}).get("candidates") or []
    assert candidates, "structured candidates required"
    assert candidates[0].get("source_id") == "gdelt"
    assert candidates[0].get("index") == 1
    routes = ar.get("valid_routes") or []
    assert routes, "valid_routes required"
    paths = {str(r.get("path") or "") for r in routes}
    assert "/library/discover/sources" in paths
    assert "/library/discover/web" in paths
    next_actions = ar.get("next_actions") or []
    assert next_actions, "next_actions required"
    assert all(isinstance(step, dict) and step.get("label") for step in next_actions)


def test_search_only_discover_does_not_create_collection_job(repo_root: Path) -> None:
    from scripts.research_data_mcp.desk_direct_turns import try_direct_discover_search_turn

    gateway = MagicMock()
    gateway.discover_source_search.return_value = {
        "query": "gdelt",
        "search_mode": "catalog",
        "results": [
            {
                "kind": "source",
                "source_id": "gdelt",
                "label": "GDELT",
                "title": "GDELT",
                "access_mode": "materialized_bulk",
                "candidate_key": "source:gdelt:gdelt",
            }
        ],
        "total": 1,
    }
    gateway.submit_collection_job = MagicMock()
    gateway.jobs = MagicMock()
    gateway.collect_datacite_doi = MagicMock()

    turn = try_direct_discover_search_turn(
        gateway,
        "discover source search for gdelt",
        {},
    )
    assert turn is not None
    ar = turn.action_result
    assert not ar.get("job")
    assert not ar.get("job_id")
    assert not ar.get("pending_job_id")
    assert "collect" not in str(ar.get("action") or "").lower()
    gateway.submit_collection_job.assert_not_called()
    gateway.collect_datacite_doi.assert_not_called()
    gateway.jobs.submit.assert_not_called()


def test_discover_search_accepts_list_valued_collect_via(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Source-map rows may supply collect_via as a list; must not 500 the chat turn."""
    from scripts.research_data_mcp.bootstrap import create_stack
    from scripts.research_data_mcp.desk_direct_turns import (
        discover_search_candidates,
        try_direct_discover_search_turn,
    )

    rows = [
        {
            "kind": "source",
            "source_id": "gdelt",
            "label": "GDELT",
            "title": "GDELT",
            "collect_via": ["http_manifest", "local_open"],
            "candidate_key": "source:gdelt:gdelt",
        },
        {
            "kind": "source",
            "source_id": "empty_via",
            "label": "Empty via",
            "collect_via": [],
        },
        {
            "kind": "source",
            "source_id": "missing_via",
            "label": "Missing via",
        },
    ]
    cleaned = discover_search_candidates(rows)
    assert len(cleaned) == 3
    assert cleaned[0]["collect_via"] == ["http_manifest", "local_open"]
    assert cleaned[0]["trust_tier"] == "acquisition_route"
    assert cleaned[1]["collect_via"] == []
    assert cleaned[1]["trust_tier"] == "metadata_only"
    assert cleaned[2]["collect_via"] == "none"
    assert cleaned[2]["trust_tier"] == "metadata_only"

    gateway = MagicMock()
    gateway.discover_source_search.return_value = {
        "query": "gdelt",
        "search_mode": "catalog",
        "results": rows[:1],
        "total": 1,
    }
    turn = try_direct_discover_search_turn(
        gateway,
        "discover source search for gdelt",
        {},
    )
    assert turn is not None
    cands = turn.action_result.get("candidates") or []
    assert cands and cands[0]["collect_via"] == ["http_manifest", "local_open"]
    assert cands[0]["trust_tier"] == "acquisition_route"

    # Full procurement_chat path previously 500'd on list-valued collect_via.
    stack = create_stack(repo_root=repo_root)

    def _fake_discover_source_search(query: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "query": query,
            "search_mode": "catalog",
            "results": rows[:1],
            "total": 1,
            "index_miss": False,
            "relevance_miss": False,
        }

    monkeypatch.setattr(stack.gateway, "discover_source_search", _fake_discover_source_search)
    chat = stack.gateway.procurement_chat("discover source search for gdelt")
    assert chat.get("action") == "discover_search"
    chat_cands = chat.get("candidates") or []
    assert chat_cands and chat_cands[0]["collect_via"] == ["http_manifest", "local_open"]
    assert chat_cands[0]["trust_tier"] == "acquisition_route"


def test_library_discover_web_applies_relevance_filter(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.research_data_mcp import http_router
    from scripts.research_data_mcp.bootstrap import create_stack

    stack = create_stack(repo_root=repo_root)

    def _fake_discover_sources(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "query": "US polling data",
            "results": [
                {
                    "title": "Crystal CIF dump",
                    "url": "https://doi.org/10.9/crystal",
                    "source": "datacite",
                    "snippet": "materials archive",
                },
                {
                    "title": "US election polling crosstabs",
                    "url": "https://doi.org/10.9/polls",
                    "source": "openalex",
                    "snippet": "polling survey microdata",
                },
            ],
            "sources_tried": ["datacite", "openalex"],
        }

    monkeypatch.setattr(
        "scripts.research_data_mcp.web_search.discover_sources",
        _fake_discover_sources,
    )
    out = http_router.handle_get(
        "/library/discover/web",
        {"q": "US polling data", "limit": "8", "tavily": "0"},
        stack,
    )
    assert out["status"] == 200
    body = out["body"]
    rows: list[dict[str, Any]] = []
    for sec in body.get("sections") or []:
        rows.extend(sec.get("rows") or [])
    assert rows, body
    assert "poll" in (rows[0].get("title") or "").lower()
    assert all("crystal" not in str(r.get("title") or "").lower() for r in rows)
    assert float(rows[0].get("query_relevance") or 0) >= 1.0
