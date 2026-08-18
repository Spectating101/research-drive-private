#!/usr/bin/env python3
"""Register MCP tools from shared ResearchToolHandlers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from scripts.research_data_mcp.tool_handlers import MCP_TOOL_NAMES, ResearchToolHandlers

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

SYNTHESIS_READ_ONLY_TOOL_NAMES = frozenset(
    {
        "research_mcp_stack_status",
        "research_platform_consolidated",
        "research_library_overview",
        "research_faculty_profile",
        "collection_status",
        "research_discover_search",
        "research_discover_source_search",
        "research_discover_source_preview",
        "research_acquisition_status",
        "research_webfetch_handoff",
        "research_web_discover",
        "research_list_datasets",
        "research_describe_dataset",
        "research_query_dataset",
        "research_analyze_dataset",
        "research_synthesis_list_profiles",
        "research_synthesis_pair",
        "research_synthesis_preflight_spec",
        "research_synthesis_materialisation",
        "research_discover_get_intent",
        "research_discover_history",
        "research_quant_brief",
        "procurement_probe_public_source",
        "datacite_search",
        "datacite_get",
        "datacite_resolve_repository",
        "datacite_scope",
        "datacite_local_harvest_status",
        "bigquery_status",
        "bigquery_list_datasets",
        "bigquery_list_tables",
        "bigquery_table_schema",
        "bigquery_dry_run",
        "research_unified_search",
        "research_search_catalog",
        "research_ops_status",
        "collection_queue_status",
        "research_procurement_catalog",
        "research_advise_datasets",
        "procurement_list_connectors",
        "procurement_list_jobs",
        "procurement_get_job",
        "research_dataset_card",
        "research_open_dataset",
        "research_list_pins",
        "yzu_cluster_status",
        "yzu_list_acquisitions",
        "yzu_cluster_components",
        "yzu_list_queue_tasks",
        "yzu_get_job",
        "yzu_list_jobs",
    }
)


def registered_tool_names() -> list[str]:
    read_only = os.getenv("RESEARCH_MCP_SYNTHESIS_READ_ONLY", "").strip().lower()
    if read_only in {"1", "true", "yes"}:
        return [
            name for name in MCP_TOOL_NAMES if name in SYNTHESIS_READ_ONLY_TOOL_NAMES
        ]
    return list(MCP_TOOL_NAMES)


def register_mcp_tools(mcp: FastMCP, tools: ResearchToolHandlers) -> None:
    for name in registered_tool_names():
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
