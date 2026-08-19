from __future__ import annotations

from scripts.research_data_mcp.discover_plan_evaluation import evaluate_cases


def test_evaluation_keeps_raw_hits_distinct_from_visible_candidates():
    seen = []

    def fake_search(*, query, query_plan):
        seen.append((query, query_plan))
        return {
            "results": [
                {"title": "Patent data", "live_hit": True, "adapter_query": "patent citations"},
                {"title": "Held route", "live_hit": False},
            ],
            "agent_review_candidates": [
                {"title": "Other patent data", "live_hit": True, "adapter_query": "patent"},
            ],
            "remote_search": {
                "query_plan": {"mode": "agent_selected"},
                "adapters": [
                    {"adapter": "huggingface", "ok": True, "returned": 5, "queries_with_results": ["patent"]},
                    {"adapter": "datacite", "ok": True, "returned": 8, "queries_with_results": ["patent citations"]},
                ],
            },
        }

    cases = [{"id": "patents", "query": "US patent grants", "query_plan": {"providers": ["huggingface"], "queries": ["patent"]}}]
    report = evaluate_cases(cases, fake_search)

    assert seen == [("US patent grants", cases[0]["query_plan"])]
    assert report["raw_external_hits"] == 13
    assert report["researcher_visible_total"] == 2
    assert report["researcher_visible_live"] == 1
    assert report["agent_review_candidates"] == 1
    assert report["all_agent_review_rows_have_query_provenance"] is True
    assert report["all_visible_live_rows_have_query_provenance"] is True
