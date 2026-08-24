from __future__ import annotations

from scripts.research_data_mcp.desk_direct_turns import (
    discover_query_from_message,
    parse_intent_request,
    search_query_from_message,
)
from scripts.research_data_mcp.tool_handlers import ResearchToolHandlers
from scripts.research_data_mcp.bootstrap import create_stack


def test_discover_query_not_stolen_as_vault():
    msg = "Use research_discover_search for query TWSE. List source_id values."
    assert search_query_from_message(msg) is None
    assert discover_query_from_message(msg) == "TWSE"


def test_vault_search_still_works():
    assert search_query_from_message("search vault for stablecoin") == "stablecoin"


def test_multi_step_intent_not_stolen():
    msg = (
        "Faculty need daily Taiwan equity prices. Search Discover for suitable sources, "
        "pick the best public TWSE-related source, then create a Discover research intent."
    )
    assert parse_intent_request(msg) is None


def test_simple_intent_still_direct():
    rail = {"selected": {"source_id": "twse_official", "connector_id": "twse", "title": "TWSE"}}
    req = parse_intent_request(
        "Create a Discover research intent for: TWSE daily prices for board-election event studies. Do not collect.",
        rail,
    )
    assert req is not None
    assert "board-election" in req["research_need"]
    assert "Return the" not in req["research_need"]


def test_research_discover_search_returns_catalog_sources():
    stack = create_stack()
    handlers = ResearchToolHandlers(stack)
    out = handlers.research_discover_search("TWSE", limit=5, include_lab=True)
    assert out["result_kind"] == "discover_sources"
    assert out["catalog_total"] >= 1
    assert any(r.get("source_id") == "twse_official" for r in out.get("results") or [])
    assert any(r.get("access_mode") for r in out.get("results") or [])


def test_multi_step_not_stolen_as_discover_query():
    msg = (
        "Faculty need daily Taiwan equity prices. Search Discover for suitable sources, "
        "pick the best public TWSE-related source, then create a Discover research intent."
    )
    assert discover_query_from_message(msg) is None
