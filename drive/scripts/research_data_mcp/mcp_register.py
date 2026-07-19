#!/usr/bin/env python3
"""Register MCP tools from shared ResearchToolHandlers."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from scripts.research_data_mcp.tool_handlers import MCP_TOOL_NAMES, ResearchToolHandlers


def register_mcp_tools(mcp: FastMCP, tools: ResearchToolHandlers) -> None:
    for name in MCP_TOOL_NAMES:
        fn = getattr(tools, name)
        mcp.tool(name=name)(fn)


def build_mcp_server(
    mcp: FastMCP,
    tools: ResearchToolHandlers,
    *,
    registry_text: str,
) -> FastMCP:
    register_mcp_tools(mcp, tools)

    @mcp.resource("research://dataset-registry")
    def dataset_registry() -> str:
        """Current logical dataset registry used by the research platform."""
        return registry_text

    return mcp
