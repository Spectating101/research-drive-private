#!/usr/bin/env python3
"""Shared procurement MCP constants — single source for collect paths and tool tiers."""

from __future__ import annotations

# Collect paths the desk/MCP may launch (union of all prior per-module frozensets).
DOWNLOADABLE_VIA = frozenset(
    {
        "datacite",
        "http_manifest",
        "local_open",
        "queue",
        "spectator",
        "web_scrape",
        "huggingface",
        "pipeline",
        "magic",
        "job",
    }
)

# Cursor/protocol adapter tools grouped by how Composer should use them.
# The full procurement MCP (toolbox) is larger — see docs/MCP_PROCUREMENT_STACK.md.
MCP_TOOL_CORE: tuple[str, ...] = (
    "research_mcp_stack_status",
    "research_platform_consolidated",
    "research_library_overview",
    "research_faculty_profile",
    "collection_status",
    "research_discover_search",
    "research_discover_source_search",
    "research_discover_source_preview",
    "research_web_discover",
    "research_list_datasets",
    "research_describe_dataset",
    "research_query_dataset",
    "research_analyze_dataset",
    "research_collection_hydrate",
    "research_synthesis_list_profiles",
    "research_synthesis_run",
    "research_synthesis_pair",
    "research_synthesis_propose_state",
    "research_synthesis_preflight_spec",
    "research_synthesis_discover_handoff",
    "research_synthesis_collect_missing",
    "research_synthesis_materialisation",
    "research_synthesis_submit_execution",
    "research_discover_create_intent",
    "research_discover_get_intent",
    "research_discover_propose_intent",
    "research_discover_history",
    "research_discover_create_refresh_subscription",
    "research_discover_pause_refresh_subscription",
    "research_discover_resume_refresh_subscription",
    "research_discover_stop_refresh_subscription",
    "research_discover_tick_refresh_subscriptions",
    "research_quant_brief",
    "procurement_probe_public_source",
)

MCP_TOOL_ACQUIRE: tuple[str, ...] = (
    "research_procure_resume_campaign",
    "research_procure_campaign_artifacts",
    "research_procure_approve_collect",
    "datacite_collect_doi",
    "datacite_search_and_resolve",
    "huggingface_collect_dataset",
    "procurement_submit_collection_job",
    "procurement_approve_job",
    "yzu_submit_job",
    "yzu_approve_job",
    "bigquery_dry_run",
    "bigquery_read_query",
)

MCP_TOOL_OPS: tuple[str, ...] = (
    "datacite_search",
    "datacite_get",
    "datacite_resolve_repository",
    "datacite_scope",
    "datacite_backfill_spec",
    "datacite_local_harvest_status",
    "bigquery_status",
    "bigquery_list_datasets",
    "bigquery_list_tables",
    "bigquery_table_schema",
    "research_unified_search",
    "research_search_catalog",
    "research_ops_status",
    "collection_queue_status",
    "research_procurement_catalog",
    "research_advise_datasets",
    "research_plan_sources",
    "huggingface_search",
    "procurement_list_connectors",
    "procurement_approve_connector",
    "procurement_prepare_collection",
    "procurement_list_jobs",
    "procurement_get_job",
    "procurement_cancel_job",
    "research_dataset_card",
    "research_open_dataset",
    "research_list_pins",
    "research_pin_dataset",
    "research_procure_chat",
    "research_procure_chat_session",
    "yzu_cluster_status",
    "yzu_list_acquisitions",
    "yzu_cluster_components",
    "yzu_list_queue_tasks",
    "yzu_cancel_job",
    "yzu_get_job",
    "yzu_list_jobs",
    "yzu_archive_to_gdrive",
)

# Ordered acquisition ladder (vault → registry → open web → fetch/scrape → jobs).
ACQUISITION_LADDER: tuple[str, ...] = (
    "vault_dictionary",       # collection_dictionary + collection_index FTS
    "registry_catalog",       # research_query_registry + curated catalog + on-disk check
    "datacite_local_prefetch",  # harvested index_v3 snippets
    "discover_search",        # Explore catalog (source_id) + optional lab supplement
    "web_discover",           # Tavily / DuckDuckGo / Zenodo / OpenAlex (index_miss)
    "probe_url",              # connector classification
    "shell_direct_http",      # curl — webfetch-equivalent
    "spectator_playwright",   # generic_url_scrape + extraction flywheel
    "cluster_jobs",           # queue / harvest / BQ / archive
)

# Composer-native tools (Playwright MCP, webfetch, Cursor web search) sit at the same
# ladder positions as shell_direct_http / spectator_playwright but do not auto-promote
# into registry — route through probe → plan_collect when acquiring for the lab.
COMPOSER_EXTERNAL_TOOLS_NOTE = (
    "Composer Playwright / webfetch / web search are valid for probe and debug. "
    "For vault-backed procurement, prefer research_web_discover then procurement_probe "
    "then yzu_submit_job so flywheel + registry promotion run."
)

MCP_TOOL_LEGACY_NOTE = (
    "Use atomic tools like yzu_submit_job, procurement_probe_public_source, and research_list_datasets. "
    "Desk chat: POST /library/chat (Cursor Composer + MCP). "
    "/agent/* and /yzu/* HTTP routes are legacy aliases."
)
