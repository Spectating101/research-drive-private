#!/usr/bin/env python3
"""A sentence is not a query, and an empty result must be attributable."""

from __future__ import annotations

from scripts.research_data_mcp.query_translation import (
    catalogue_query_variants,
    content_terms,
    llm_search_terms,
    search_terms,
    search_with_backoff,
)


def test_question_scaffolding_is_stripped():
    terms = content_terms("Can you find me any datasets with US patent grants and citations?")
    assert "patent" in terms
    for noise in ("can", "you", "find", "datasets", "with", "any"):
        assert noise not in terms


def test_catalogue_plan_preserves_question_and_adds_precise_then_broad_terms():
    variants = catalogue_query_variants("US patent grants and citations", provider="huggingface")
    assert variants == [
        "US patent grants and citations",
        "us patent grants citations",
        "patent citations",
        "patent",
    ]


def test_uppercase_us_is_retained_as_geography_not_question_scaffolding():
    assert "us" in content_terms("US company fundamentals")


def test_datacite_supplements_use_the_same_transparent_plan():
    from scripts.research_data_mcp.procurement_search import datacite_supplement_queries

    assert datacite_supplement_queries("US patent grants and citations") == catalogue_query_variants(
        "US patent grants and citations", provider="datacite"
    )


def test_the_ladder_gets_broader_not_narrower():
    ladder = search_terms("US patent grants and citations")
    assert ladder[0].split() >= ladder[1].split() or len(ladder[0]) >= len(ladder[1])
    assert ladder[-2] == "patent" or "patent" in ladder
    assert any(len(v.split()) == 1 for v in ladder), ladder


def test_weak_nouns_sink_rather_than_dominate():
    terms = content_terms("panel study of household income")
    assert terms.index("household") < terms.index("panel")


def test_an_empty_question_yields_nothing():
    assert search_terms("   ") == []


def test_backoff_stops_at_the_first_query_that_answers():
    calls: list[str] = []

    def fetch(q):
        calls.append(q)
        return {"rows": [{"id": "hit"}]} if q == "patent" else {"rows": []}

    out = search_with_backoff("US patent grants and citations", fetch)
    assert out["query_used"] == "patent"
    assert len(out["rows"]) == 1
    assert calls[-1] == "patent"
    assert len(out["attempts"]) == len(calls)


def test_backoff_reports_what_it_tried_when_nothing_answers():
    """Zero results must be attributable: nothing there, versus asked badly."""
    out = search_with_backoff("obscure nonexistent topic", lambda q: {"rows": []})
    assert out["rows"] == []
    assert len(out["attempts"]) >= 2
    assert all(a["rows"] == 0 for a in out["attempts"])


def test_a_failing_fetch_is_recorded_and_does_not_abort_the_ladder():
    def fetch(q):
        if q != "patent":
            raise RuntimeError("upstream 503")
        return {"rows": [{"id": "hit"}]}

    out = search_with_backoff("US patent grants and citations", fetch)
    assert out["query_used"] == "patent"
    assert any("upstream 503" in (a.get("error") or "") for a in out["attempts"])


def test_a_reasoner_can_propose_terms_instead():
    out = llm_search_terms("US patent grants and citations",
                           propose=lambda q: ["uspto citations", "patent"])
    assert out[0] == "uspto citations"


def test_a_dead_reasoner_falls_back_to_the_deterministic_ladder():
    def broken(_q):
        raise RuntimeError("subscription expired")

    assert llm_search_terms("US patent grants and citations", propose=broken) == search_terms(
        "US patent grants and citations"
    )
