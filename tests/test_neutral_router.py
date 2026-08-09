"""The neutral desk router is cross-workspace, but mutation-bounded."""

from __future__ import annotations


def test_neutral_router_context_is_explicit_and_not_synthesis():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        is_neutral_router_context,
        is_synthesis_context,
    )

    state = {
        "rail_context": {
            "tab": "home",
            "mode": "ask",
            "workspace": {"surface": "neutral"},
        }
    }
    assert is_neutral_router_context(state)
    assert not is_synthesis_context(state)

    state["rail_context"] = {"tab": "synthesis", "mode": "define"}
    assert not is_neutral_router_context(state)
    assert is_synthesis_context(state)


def test_neutral_router_excludes_collection_and_execution(monkeypatch):
    from scripts.research_data_mcp.mcp_register import registered_tool_names

    monkeypatch.setenv("RESEARCH_MCP_DESK", "1")
    monkeypatch.setenv("RESEARCH_MCP_NEUTRAL_ROUTER", "1")
    monkeypatch.delenv("RESEARCH_MCP_DISCOVER", raising=False)
    monkeypatch.delenv("RESEARCH_MCP_SYNTHESIS_READ_ONLY", raising=False)

    names = set(registered_tool_names())
    assert {
        "research_discover_search",
        "research_describe_dataset",
        "research_synthesis_discover_handoff",
        "research_synthesis_materialisation",
        "research_synthesis_propose_state",
    } <= names
    assert {
        "research_synthesis_collect_missing",
        "research_synthesis_submit_execution",
        "research_propose_pending_collect",
        "datacite_collect_doi",
        "yzu_submit_job",
        "yzu_approve_job",
    }.isdisjoint(names)


def test_neutral_router_instructions_state_the_boundary(monkeypatch):
    from scripts.research_data_mcp.mcp_instructions import mcp_server_instructions

    monkeypatch.setenv("RESEARCH_MCP_DESK", "1")
    monkeypatch.setenv("RESEARCH_MCP_NEUTRAL_ROUTER", "1")
    text = mcp_server_instructions().lower()
    assert "library, discover, and synthesis" in text
    assert "review-only proposal" in text
    assert "no collection" in text
    assert "never claim materialisation" in text
