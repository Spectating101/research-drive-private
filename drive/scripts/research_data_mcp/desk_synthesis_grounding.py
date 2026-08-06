#!/usr/bin/env python3
"""First-turn Synthesis Ask grounding — measured desk facts only.

No token-ranked catalog wallpaper (the Discover script-brain failure mode).
Composer judges fit; this module only reports what
``research_discover_desk`` / desk_check measured plus declared synthesis profiles.
"""

from __future__ import annotations

from typing import Any


def build_synthesis_grounding_brief(
    gateway: Any,
    message: str,
    *,
    candidate_limit: int = 8,
    profile_limit: int = 8,
    rail_context: dict[str, Any] | None = None,
) -> str:
    """Build a bounded DESK_FACTS block — held/routes measured, profiles listed.

    Does not claim fit, coverage, readiness, or a completed construct.
    Prefer the open Synthesis objective when Ask is assisting that thread.
    """
    from scripts.research_data_mcp.desk_ask_grounding import resolve_ask_measure_query
    from scripts.research_data_mcp.discover_desk import desk_check

    q = resolve_ask_measure_query(message, rail_context)
    desk: dict[str, Any] = {}
    try:
        desk = desk_check(gateway, q, limit=candidate_limit)
    except Exception:  # noqa: BLE001
        desk = {
            "held": [],
            "routes": [],
            "strong_held": False,
            "held_count": 0,
            "route_count": 0,
        }

    held = [dict(r) for r in (desk.get("held") or [])[:candidate_limit] if isinstance(r, dict)]
    routes = [dict(r) for r in (desk.get("routes") or [])[:3] if isinstance(r, dict)]
    strong = bool(desk.get("strong_held"))

    profiles: list[dict[str, Any]] = []
    try:
        payload = gateway.synthesis_list_profiles()
        profiles = [
            dict(row)
            for row in (payload.get("profiles") or [])
            if isinstance(row, dict)
        ][:profile_limit]
    except Exception:  # noqa: BLE001
        profiles = []

    held_ids = {
        str(r.get("dataset_id") or "").strip()
        for r in held
        if str(r.get("dataset_id") or "").strip()
    }
    # Prefer profiles that cite measured held sources; otherwise list declared ids only.
    linked: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for row in profiles:
        sources = row.get("sources") or []
        source_ids = {
            str(s.get("dataset_id") or s.get("id") or s).strip()
            if isinstance(s, dict)
            else str(s).strip()
            for s in sources
        }
        source_ids.discard("")
        if held_ids and source_ids & held_ids:
            linked.append(row)
        else:
            other.append(row)

    lines = [
        "[Synthesis DESK_FACTS]",
        "Measured via research_discover_desk (L0 hands). Not ranked for fit.",
        "Do not invent dataset_ids or source_ids outside this block.",
        "Do not treat this list as proof of coverage or a completed construct.",
    ]
    if q:
        lines.append(f"Open construct / measure query: {q[:220]}")

    if strong and held:
        lines.append(f"Strong Library holdings ({len(held)}):")
        for row in held:
            title = str(row.get("title") or row.get("dataset_id") or "Dataset").strip()
            dataset_id = str(row.get("dataset_id") or "").strip()
            identifier = f" [{dataset_id}]" if dataset_id else ""
            lines.append(f"- held: {title}{identifier}")
    elif held:
        lines.append(f"Weak/lexical Library hits ({len(held)}) — verify before use:")
        for row in held:
            title = str(row.get("title") or row.get("dataset_id") or "Dataset").strip()
            dataset_id = str(row.get("dataset_id") or "").strip()
            identifier = f" [{dataset_id}]" if dataset_id else ""
            lines.append(f"- held?: {title}{identifier}")
    else:
        lines.append("Library holdings: none measured for this question.")

    if routes and not strong:
        lines.append(f"Declared collectable routes ({len(routes)}):")
        for row in routes:
            title = str(row.get("title") or row.get("label") or row.get("source_id") or "").strip()
            sid = str(row.get("source_id") or "").strip()
            why = str(row.get("why") or row.get("selection_reason") or "").strip()[:160]
            detail = f" — {why}" if why else ""
            lines.append(f"- route: {title} [{sid}]{detail}")
    elif not strong:
        lines.append("Declared collectable routes: none for this question.")

    if linked:
        lines.append("Declared synthesis profiles citing measured holdings:")
        for row in linked[:profile_limit]:
            title = str(row.get("title") or row.get("id") or "profile").strip()
            pid = str(row.get("id") or "").strip()
            lines.append(f"- profile: {title}" + (f" [{pid}]" if pid else ""))
    elif profiles:
        ids = [
            str(row.get("id") or row.get("title") or "").strip()
            for row in other[:profile_limit]
            if str(row.get("id") or row.get("title") or "").strip()
        ]
        lines.append(
            f"Declared synthesis profiles on this desk ({len(profiles)}); "
            f"none cite measured holdings for this question. "
            f"Ids: {', '.join(ids) if ids else '(none)'}."
        )
        lines.append(
            "Call research_synthesis_list_profiles / research_synthesis_run only when a "
            "profile actually matches the construct — do not invent relevance from names."
        )
    else:
        lines.append("Declared synthesis profiles: unavailable or empty.")

    lines.append(
        "Use MCP tools to verify holdings and routes. Composer owns fit judgment."
    )
    lines.append("[/Synthesis DESK_FACTS]")
    return "\n".join(lines)[:6000]
