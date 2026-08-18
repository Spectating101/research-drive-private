#!/usr/bin/env python3
"""A retrieval path nothing can call is not a capability.

`gateway.semantic_discover` answered natural-language research questions correctly
while `/library/discover` returned nothing for 7 of 8 — and it was exposed to nobody:
absent from the 86 MCP tools and never called by the UI. A local 7B model given the
keyword tool concluded "no datasets cover Taiwan listed company market data"; the same
model with the semantic tool returned twse_openapi_taiwan_market_layer. The capability
was never the problem, the wiring was.
"""

from __future__ import annotations

from scripts.research_data_mcp.gateway import ResearchDataGateway
from scripts.research_data_mcp.mcp_register import registered_tool_names
from scripts.research_data_mcp.tool_handlers import MCP_TOOL_NAMES, ResearchToolHandlers

# Gateway retrieval methods a reasoner must be able to reach. Widening the gateway
# without exposing the path is the failure this pins.
REQUIRED_RETRIEVAL_TOOLS = (
    "research_semantic_discover",
    "research_discover_search",
    "research_list_datasets",
    "research_describe_dataset",
    "research_query_dataset",
)


def test_every_required_retrieval_path_is_a_registered_tool() -> None:
    registered = set(registered_tool_names())
    missing = [name for name in REQUIRED_RETRIEVAL_TOOLS if name not in registered]
    assert not missing, f"retrieval paths unreachable by any agent: {missing}"


def test_each_declared_tool_name_has_a_handler_method() -> None:
    """A name in the roster with no method registers nothing and fails at call time."""
    absent = [name for name in MCP_TOOL_NAMES if not hasattr(ResearchToolHandlers, name)]
    assert not absent, f"declared tool names with no handler method: {absent}"


def test_semantic_discover_reaches_the_gateway() -> None:
    assert hasattr(ResearchToolHandlers, "research_semantic_discover")
    assert hasattr(ResearchDataGateway, "semantic_discover")
