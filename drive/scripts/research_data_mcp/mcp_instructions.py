#!/usr/bin/env python3
"""MCP instructions — tool surface only; voice comes from Cursor project rules."""

from __future__ import annotations

import os


def mcp_server_instructions() -> str:
    if os.getenv("RESEARCH_MCP_DESK", "").strip() in {"1", "true", "yes"}:
        return (
            "Research procurement MCP for the YZU Research Drive desk. "
            "Use these tools whenever you need real vault, registry, or collection state. "
            "Faculty chat: answer like a normal assistant — short and direct first (≤8 sentences on turn one). "
            "If the user message includes a preloaded desk vault brief, trust it — "
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
            "Never call yzu_approve_job for synthesis_execute. "
            "What a dataset says about itself — research_list_datasets and "
            "research_describe_dataset return these on every row: one_line and "
            "description (what it is), meaning_about (a plain-English account of "
            "what the data is about, present on 120 of 168), keywords, limitations "
            "(what the source cannot support, on 31), grain (what one row "
            "represents, on all 168), and join_keys (on 44 — a hint where present, "
            "not a boundary; the columns themselves are in the data). "
            "What a preflight result contains — these are measurements of the real "
            "bytes, reported so they can be shown to the researcher. "
            "join_probes[] per join: shared_distinct (key values present on both "
            "sides), coverage_left_pct / coverage_right_pct, right_cardinality "
            "(1:1 or 1:N). "
            "issues[] block execution: empty_join (the key shares no values); "
            "collapse_rule_required (the right side has several rows per key, so a "
            "merge multiplies rows; collapse.strategy first/last/error is a spec "
            "field the engine will not fill in); join_discards_most_rows (both sides "
            "retain under the configured floor; accept_row_loss overrides); "
            "missing_column (absent from that schema). "
            "warnings[] do not block and describe what a number is computed over: a "
            "left join leaves count() and mean() over different row counts; a name "
            "on both sides keeps the input's values and suffixes the other _right; "
            "non-finite source values propagate into aggregates. "
            "join_asof matches on an ordered column with optional `by` entities: "
            "direction backward/forward/nearest (forward and nearest read values "
            "dated after the row), tolerance bounds how stale a match may be. "
            "Metrics a spec may ask for — count (rows, including rows whose group "
            "key is null), sum, mean, min, max, std, median, nunique, and quantile "
            "(which takes q, a fraction between 0 and 1). Nothing requires "
            "dispersion; an effect size without one cannot be told from noise, and "
            "that is the caller's call to make. "
            "What a run measures about itself — research_synthesis_materialisation "
            "returns `measured` on a recorded execution: source_rows and "
            "rows_aggregated (an aggregate over 50 of 1000 rows reads the same as "
            "one over all of them unless you look), row_ledger (rows in and out per "
            "transform step), asof_coverage (per as-of step: matched_rows, "
            "unmatched_rows, match_rate_pct, undated_left_rows_dropped — an "
            "unmatched row is NaN and sums to 0.0), and undefined_derived_values "
            "(how many values a derive masked, a division by zero among them)."
        )
    from scripts.research_data_mcp.procurement_constants import ACQUISITION_LADDER, COMPOSER_EXTERNAL_TOOLS_NOTE

    ladder = " → ".join(ACQUISITION_LADDER)
    return (
        "Research procurement MCP — passive atomic tools only; Composer plans and calls each step. "
        f"Acquisition ladder: {ladder}. "
        f"{COMPOSER_EXTERNAL_TOOLS_NOTE} "
        "See .agents/AGENTS.md for the full playbook."
    )
