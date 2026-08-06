#!/usr/bin/env python3
"""MCP instructions — tool surface only; voice comes from Cursor project rules."""

from __future__ import annotations

import os


def mcp_server_instructions() -> str:
    desk = os.getenv("RESEARCH_MCP_DESK", "").strip().lower() in {"1", "true", "yes"}
    synthesis_ro = os.getenv("RESEARCH_MCP_SYNTHESIS_READ_ONLY", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if desk and synthesis_ro:
        return (
            "Research procurement MCP — Synthesis Ask (read-only tool surface). "
            "Answer like a normal assistant — short and direct. "
            "Trust any preloaded Synthesis DESK_FACTS / vault brief; do not re-inventory. "
            "Allowed synthesis tools: research_synthesis_list_profiles, research_synthesis_pair, "
            "research_synthesis_preflight_spec, research_synthesis_propose_state (records a draft; "
            "never applies), research_synthesis_materialisation. "
            "You cannot run panels (research_synthesis_run), submit execution, collect missing, "
            "or approve jobs from this Ask surface — tell the researcher to use the Synthesis UI "
            "Build/refresh or the thread accept → execute ladder. "
            "Never claim materialisation without research_synthesis_materialisation saying registered. "
            "Never call yzu_approve_job."
        )
    if desk:
        return (
            "Research procurement MCP for the YZU Research Drive desk. "
            "Use these tools whenever you need real vault, registry, or collection state. "
            "Faculty chat: answer like a normal assistant — short and direct first (≤8 sentences on turn one). "
            "If the user message includes a preloaded desk vault brief or Ask DESK_FACTS, trust it — "
            "never call collection_status or run another inventory sweep; "
            "use tools only for samples, query, collect, hydrate, or synthesis. "
            "For stablecoin multi-source work (Skynet + Etherscan + community growth + security + GDELT): "
            "call research_synthesis_list_profiles, then research_synthesis_run(profile_id='stablecoin_trust_engagement') "
            "— do not manually stitch scripts or paths. "
            "Synthesis thread ladder (when rail context has synthesis thread_id): "
            "1) research_synthesis_preflight_spec on any execution_spec, "
            "2) research_synthesis_propose_state (never applies), "
            "3) wait for researcher accept in the desk, "
            "4) research_synthesis_submit_execution (queues pending_approval only — you cannot approve), "
            "5) research_synthesis_materialisation to check honest output status, "
            "6) for gaps: research_synthesis_discover_handoff then research_synthesis_collect_missing. "
            "Never claim materialisation without research_synthesis_materialisation saying registered. "
            "Never call yzu_approve_job for synthesis_execute."
        )
    from scripts.research_data_mcp.procurement_constants import ACQUISITION_LADDER, COMPOSER_EXTERNAL_TOOLS_NOTE

    ladder = " → ".join(ACQUISITION_LADDER)
    return (
        "Research procurement MCP — passive atomic tools only; Composer plans and calls each step. "
        f"Acquisition ladder: {ladder}. "
        f"{COMPOSER_EXTERNAL_TOOLS_NOTE} "
        "See .agents/AGENTS.md for the full playbook."
    )
