#!/usr/bin/env python3
"""What this desk can actually do — capability families over registered MCP tools.

Discover named 4 tools of 55. The rest of the stack (query held data, BigQuery,
synthesis, cluster) was invisible to Composer, so it could only point at
datasets it could have answered from.

Dumping 55 names degrades tool selection. This maps tools to capability
families, verifies each against the live registry so a family can never claim a
tool that is not registered, and emits a compact block scoped to the turn.
"""

from __future__ import annotations

from typing import Any, Iterable

FAMILIES: dict[str, dict[str, Any]] = {
    "answer_from_held": {
        "label": "Answer from held data",
        "tools": ["research_query_dataset", "research_analyze_dataset", "research_dataset_card"],
        "hint": (
            "held evidence can be queried directly — answer the question from the data"
            " instead of only naming the dataset"
        ),
    },
    "inspect": {
        "label": "Inspect before committing",
        "tools": ["research_describe_dataset", "research_open_dataset", "research_discover_source_preview"],
        "hint": "read schema, columns and a bounded sample before recommending a collect",
    },
    "warehouse": {
        "label": "BigQuery warehouse",
        "tools": ["bigquery_dry_run", "bigquery_list_datasets", "bigquery_list_tables", "bigquery_table_schema"],
        "hint": "public warehouse tables are reachable; dry-run first to price the scan",
    },
    "collect": {
        "label": "Collect and probe",
        # capability_block() only shows the first 3 tool names in its rendered
        # tuple — research_propose_pending_collect leads so it's actually
        # visible there, not just named inside the hint sentence.
        "tools": [
            "research_propose_pending_collect",
            "procurement_probe_public_source",
            "procurement_list_connectors",
            "research_procurement_catalog",
        ],
        "hint": (
            "when nothing is held or routed, research_propose_pending_collect "
            "drafts a real pending_approval job from a URL you name — call it, "
            "don't just describe that a collect would be possible; probe a "
            "public URL first to classify it if unsure"
        ),
    },
    "synthesis": {
        "label": "Build derived datasets",
        "tools": [
            "research_synthesis_pair",
            "research_synthesis_preflight_spec",
            "research_synthesis_collect_missing",
            "research_synthesis_discover_handoff",
        ],
        "hint": "held datasets can be joined or transformed into a new registered dataset",
    },
    "fleet": {
        "label": "Worker fleet",
        "tools": ["yzu_cluster_status", "yzu_cluster_components", "yzu_list_jobs"],
        "hint": "collection can be split across online workers rather than run serially",
    },
    "catalog": {
        "label": "External catalogues",
        "tools": ["datacite_search", "datacite_resolve_repository", "research_web_discover"],
        "hint": "DOI and web discovery for sources the desk does not hold",
    },
}


def registered_tool_names(gateway: Any) -> set[str] | None:
    """Tool names the runtime exposes. None means unknown; empty set means none."""
    for attr in ("mcp_tool_names", "tool_names", "registered_tools"):
        value = getattr(gateway, attr, None)
        if callable(value):
            try:
                value = value()
            except Exception:  # noqa: BLE001
                value = None
        if isinstance(value, (list, tuple, set)):
            return {str(v) for v in value if v}
        if isinstance(value, dict):
            return {str(k) for k in value}
    try:
        from scripts.research_data_mcp.tool_handlers import MCP_TOOL_NAMES

        return {str(n) for n in MCP_TOOL_NAMES if n}
    except Exception:  # noqa: BLE001
        return None


def available_families(
    gateway: Any = None,
    *,
    only: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Families whose tools are registered. Never claims an unregistered tool."""
    registered = registered_tool_names(gateway)
    wanted = set(only) if only else None
    out: list[dict[str, Any]] = []
    for key, spec in FAMILIES.items():
        if wanted is not None and key not in wanted:
            continue
        tools = [t for t in spec["tools"] if registered is None or t in registered]
        if not tools:
            continue
        out.append({"key": key, "label": spec["label"], "tools": tools, "hint": spec["hint"]})
    return out


def families_for_turn(*, has_held: bool, has_routes: bool, is_question: bool) -> list[str]:
    """Scope the block to what this turn could plausibly use."""
    keys: list[str] = []
    if has_held:
        keys.append("answer_from_held")
        keys.append("inspect")
        if is_question:
            keys.append("synthesis")
    if has_routes:
        keys.append("collect")
        keys.append("fleet")
    if not has_held:
        keys.append("catalog")
        keys.append("warehouse")
        # "collect" was previously gated on has_routes only — exactly backwards
        # for the case that most needs it: nothing held AND nothing routed is
        # when research_propose_pending_collect actually matters, and it was
        # never surfaced in the capability block for that turn.
        keys.append("collect")
    seen: set[str] = set()
    return [k for k in keys if not (k in seen or seen.add(k))]


def capability_block(
    gateway: Any = None,
    *,
    has_held: bool = False,
    has_routes: bool = False,
    is_question: bool = False,
) -> str:
    families = available_families(
        gateway,
        only=families_for_turn(has_held=has_held, has_routes=has_routes, is_question=is_question),
    )
    if not families:
        return ""
    lines = ["This desk can also do the following on this turn — use them when they change the answer:"]
    for fam in families:
        lines.append(f"- {fam['label']}: {fam['hint']} ({', '.join(fam['tools'][:3])})")
    return "\n".join(lines)
