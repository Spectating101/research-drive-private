"""All outward web-discovery callers use the same transparent catalogue plan."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path


def _hit(title: str, source: str = "datacite") -> dict[str, str]:
    return {
        "title": title,
        "url": f"https://example.org/{source}/{title.replace(' ', '-')}",
        "source": source,
        "snippet": title,
    }


def test_catalogue_sources_back_off_to_translated_phrase_and_report_it(tmp_path, monkeypatch):
    from scripts.research_data_mcp import web_search as mod

    seen_datacite: list[str] = []

    def datacite(query: str, _limit: int):
        seen_datacite.append(query)
        if query == "patent citations":
            return [_hit("US patent grants and citations dataset")]
        return []

    monkeypatch.setattr(mod, "_search_datacite", datacite)
    monkeypatch.setattr(mod, "_search_zenodo_api", lambda *_args: [])
    monkeypatch.setattr(mod, "_search_openalex_api", lambda *_args: [])
    monkeypatch.setattr(mod, "_search_tavily", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(mod, "_search_duckduckgo_html", lambda *_args: [])
    monkeypatch.setattr(mod, "_search_duckduckgo_instant", lambda *_args: [])

    out = mod.discover_sources(tmp_path, "US patent grants and citations", tavily_live=False)

    assert "patent citations" in seen_datacite
    assert out["results"]
    attempt = next(item for item in out["provider_attempts"] if item["source"] == "datacite")
    assert attempt["query_used"] == "patent citations"
    assert attempt["catalogue_style"] is True
    assert "patent citations" in out["queries_tried"]


def test_general_web_engines_keep_the_researcher_wording(tmp_path, monkeypatch):
    from scripts.research_data_mcp import web_search as mod

    seen_tavily: list[str] = []
    monkeypatch.setattr(mod, "_search_datacite", lambda *_args: [])
    monkeypatch.setattr(mod, "_search_zenodo_api", lambda *_args: [])
    monkeypatch.setattr(mod, "_search_openalex_api", lambda *_args: [])
    monkeypatch.setattr(
        mod,
        "_search_tavily",
        lambda _root, query, _limit, **_kwargs: seen_tavily.append(query) or [],
    )
    monkeypatch.setattr(mod, "_search_duckduckgo_html", lambda *_args: [])
    monkeypatch.setattr(mod, "_search_duckduckgo_instant", lambda *_args: [])

    question = "US patent grants and citations"
    out = mod.discover_sources(tmp_path, question, tavily_live=False)

    assert seen_tavily == [question]
    tavily_attempt = next(item for item in out["provider_attempts"] if item["source"] == "tavily")
    assert tavily_attempt["queries_tried"] == [question]


def test_tavily_adapter_is_callable_from_an_active_mcp_event_loop(monkeypatch):
    from scripts.research_data_mcp import web_search as mod

    class FakeBalancer:
        async def search(self, query: str, search_depth: str, max_results: int):
            return [{"title": query, "url": "https://example.org/result", "content": "ok"}]

    fake_module = types.ModuleType("src.utils.tavily_balancer")
    fake_module.TavilyBalancer = FakeBalancer
    monkeypatch.setitem(sys.modules, "src.utils.tavily_balancer", fake_module)
    monkeypatch.setattr(mod, "_optiplex_root", lambda _root: Path("/tmp/optiplex"))

    async def invoke():
        return mod._search_tavily(Path("/tmp/research-drive"), "patent", 2, live=False)

    rows = asyncio.run(invoke())
    assert rows[0]["title"] == "patent"
