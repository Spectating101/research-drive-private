"""Live discovery must not mistake a raw sentence for a catalogue query."""

from __future__ import annotations

from scripts.research_data_mcp.query_translation import catalogue_query_variants


def test_long_patent_request_keeps_the_original_and_exposes_catalogue_terms():
    variants = catalogue_query_variants("US patent grants and citations", provider="huggingface")
    assert variants[0] == "US patent grants and citations"
    assert "patent citations" in variants
    assert "patent" in variants
    assert len(variants) <= 4


def test_short_query_is_not_needlessly_rewritten():
    assert catalogue_query_variants("taiwan stock", provider="huggingface") == ["taiwan stock"]


def test_live_adapter_reports_exact_variants_and_returns_a_variant_hit(monkeypatch):
    from scripts.research_data_mcp import discover_source_search as mod

    seen_hf: list[str] = []

    def fake_hf(query, *, limit):
        seen_hf.append(query)
        if query != "patent":
            return [], {"adapter": "huggingface", "ok": True, "error": None, "returned": 0}
        row = mod._normalize_live_candidate(
            provider="Hugging Face", title="Patent corpus", external_id="org/patents"
        )
        return [row], {"adapter": "huggingface", "ok": True, "error": None, "returned": 1}

    monkeypatch.setattr(mod, "_live_search_huggingface", fake_hf)
    monkeypatch.setattr(
        mod,
        "_live_search_kaggle",
        lambda query, *, limit: ([], {"adapter": "kaggle", "ok": True, "error": None, "returned": 0}),
    )
    monkeypatch.setattr(
        mod,
        "_live_search_datacite",
        lambda query, *, limit: ([], {"adapter": "datacite", "ok": True, "error": None, "returned": 0}),
    )
    for adapter in ("zenodo", "openalex"):
        monkeypatch.setattr(
            mod,
            f"_live_search_{adapter}",
            lambda query, *, limit, adapter=adapter: (
                [], {"adapter": adapter, "ok": True, "error": None, "returned": 0}
            ),
        )
    hits, reports = mod._run_live_adapters("US patent grants and citations", per_adapter=5)

    assert "patent" in seen_hf
    assert len(hits) == 1
    assert hits[0]["adapter_query"] == "patent"
    assert hits[0]["connector_id"] == "huggingface"
    hf = next(report for report in reports if report["adapter"] == "huggingface")
    assert "patent" in hf["queries_tried"]
    assert hf["queries_with_results"] == ["patent"]
    assert {report["adapter"] for report in reports} == {
        "huggingface", "kaggle", "datacite", "zenodo", "openalex"
    }


def test_zenodo_and_openalex_rows_use_the_common_live_candidate_contract(monkeypatch):
    from scripts.research_data_mcp import academic_discovery as academic
    from scripts.research_data_mcp import discover_source_search as mod

    monkeypatch.setattr(
        academic,
        "search_zenodo",
        lambda *args, **kwargs: [{"title": "Patent files", "url": "https://zenodo.org/records/1", "doi": "10.1/z"}],
    )
    monkeypatch.setattr(
        academic,
        "search_openalex_datasets",
        lambda *args, **kwargs: [{"title": "Patent works", "url": "https://example.org/openalex", "doi": "10.1/o"}],
    )
    zenodo_rows, zenodo_meta = mod._live_search_zenodo("patent", limit=5)
    openalex_rows, openalex_meta = mod._live_search_openalex("patent", limit=5)

    assert zenodo_meta["ok"] is True
    assert openalex_meta["ok"] is True
    assert zenodo_rows[0]["provider"] == "Zenodo"
    assert openalex_rows[0]["provider"] == "OpenAlex"
    assert zenodo_rows[0]["live_hit"] is True
    assert openalex_rows[0]["candidate_key"]


def test_relevance_is_prioritized_within_a_provider_before_diversification():
    from scripts.research_data_mcp import discover_source_search as mod

    weak = mod._normalize_live_candidate(
        provider="Zenodo", title="Unrelated record", url="https://zenodo.org/records/weak"
    )
    strong = mod._normalize_live_candidate(
        provider="Zenodo",
        title="Taiwan stock returns dataset",
        url="https://zenodo.org/records/strong",
    )
    ranked = mod._prioritize_live_hits_for_query(
        [weak, strong], "daily returns for Taiwan listed companies"
    )
    assert ranked[0]["title"] == "Taiwan stock returns dataset"
