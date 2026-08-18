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
        "_live_search_datacite",
        lambda query, *, limit: ([], {"adapter": "datacite", "ok": True, "error": None, "returned": 0}),
    )
    hits, reports = mod._run_live_adapters("US patent grants and citations", per_adapter=5)

    assert "patent" in seen_hf
    assert len(hits) == 1
    assert hits[0]["adapter_query"] == "patent"
    hf = next(report for report in reports if report["adapter"] == "huggingface")
    assert "patent" in hf["queries_tried"]
    assert hf["queries_with_results"] == ["patent"]
