#!/usr/bin/env python3
"""Register MCP tools from shared ResearchToolHandlers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from scripts.research_data_mcp.tool_handlers import MCP_TOOL_NAMES, ResearchToolHandlers

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Synthesis Ask construction surface (env RESEARCH_MCP_SYNTHESIS_READ_ONLY=1).
# Propose never applies; submit_execution queues pending_approval only.
# Still excludes approve/run-panel/blanket procure mutate tools.
SYNTHESIS_READ_ONLY_TOOL_NAMES = frozenset(
    {
        "research_mcp_stack_status",
        "research_platform_consolidated",
        "research_library_overview",
        "research_faculty_profile",
        "collection_status",
        "research_discover_search",
        "research_discover_desk",
        "research_discover_source_search",
        "research_discover_source_preview",
        "research_web_discover",
        "research_list_datasets",
        "research_describe_dataset",
        "research_query_dataset",
        "research_analyze_dataset",
        "research_synthesis_list_profiles",
        "research_synthesis_pair",
        "research_synthesis_preflight_spec",
        "research_synthesis_materialisation",
        # Propose never applies — Composer can record a reviewable draft for the researcher.
        "research_synthesis_propose_state",
        # Construction ladder (human Accept still required before durable apply).
        "research_synthesis_submit_execution",
        "research_synthesis_discover_handoff",
        "research_synthesis_collect_missing",
        "research_synthesis_terminal_list",
        "research_synthesis_terminal_run",
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
        "research_ops_status",
        "collection_queue_status",
        "research_procurement_catalog",
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


# Discover answers one question about held evidence. 87 tools is well past the
# point where selection stays reliable — observed live, Composer authenticated to
# MCP and then never reached research_query_dataset. This is the task surface.
#
# research_propose_pending_collect is the one exception to "read-only": it never
# collects anything itself (submit_yzu_job runs with auto_approve=False and the
# job sits in pending_approval for a researcher to act on) and it "refuses
# inventing targets" — it errors rather than fabricate a URL when none is given.
# Added deliberately narrow after finding the underlying job-first/craft_collect
# machinery already existed, safety-gated, and simply wasn't reachable from a
# Discover conversation — Discover could describe a gap but never act on it.
DISCOVER_TOOL_NAMES = frozenset(
    {
        "research_discover_desk",
        "research_query_dataset",
        "research_analyze_dataset",
        "research_describe_dataset",
        "research_list_datasets",
        "research_web_discover",
        "procurement_probe_public_source",
        "research_propose_pending_collect",
    }
)


def registered_tool_names() -> list[str]:
    if os.getenv("RESEARCH_MCP_DISCOVER", "").strip().lower() in {"1", "true", "yes"}:
        return [name for name in MCP_TOOL_NAMES if name in DISCOVER_TOOL_NAMES]
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
