"""MCP callers, rather than backend heuristics, select public Discover lanes."""

from __future__ import annotations

from types import SimpleNamespace

from scripts.research_data_mcp.tool_handlers import ResearchToolHandlers


class _Gateway:
    def __init__(self):
        self.calls = []

    def discover_source_search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return {
            "results": [],
            "search_mode": "live",
            "remote_search": {"query_plan": {"mode": "agent_selected"}},
            "agent_review_candidates": [{"title": "Patent corpus", "adapter_query": "patent citations"}],
            "agent_review_candidate_total": 1,
        }


def test_combined_mcp_discover_enables_the_live_path_and_passes_the_agent_plan():
    gateway = _Gateway()
    handlers = ResearchToolHandlers(SimpleNamespace(gateway=gateway))
    plan = {"providers": ["zenodo"], "queries": ["patent citations"]}

    out = handlers.research_discover_search(
        "US patent grants and citations",
        live=True,
        include_lab=False,
        query_plan=plan,
    )

    assert out["search_mode"] == "live"
    assert gateway.calls == [
        (
            "US patent grants and citations",
            {"limit": 12, "live": True, "query_plan": plan},
        )
    ]
    assert out["remote_search"]["query_plan"]["mode"] == "agent_selected"
    assert out["agent_review_candidate_total"] == 1
    assert out["agent_review_candidates"][0]["adapter_query"] == "patent citations"
