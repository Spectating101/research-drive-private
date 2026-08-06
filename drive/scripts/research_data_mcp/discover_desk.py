#!/usr/bin/env python3
"""Discover L0 hands — measured held + declared routes on this machine.

Composer must not invent vault holdings or collectable source_ids. This module
is the single measured desk check used by Explore and by MCP
``research_discover_desk``.
"""

from __future__ import annotations

import time
from typing import Any

from scripts.research_data_mcp.evidence_placement import (
    PLACEMENT_HELD,
    PLACEMENT_ROUTE,
    stamp_evidence_fields,
)

_STRONG_SCORE = 8.0
_READY_MIN_SCORE = 2.0


def strong_held_hits(candidates: list[dict[str, Any]]) -> bool:
    """True when the desk already has a confident local answer — not mere token overlap."""
    if not candidates:
        return False
    top = candidates[0]
    if float(top.get("score") or 0) >= _STRONG_SCORE:
        return True
    return any(
        bool(c.get("local_ready")) and float(c.get("score") or 0) >= _READY_MIN_SCORE
        for c in candidates[:5]
    )


def _stamp_held(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["placement"] = PLACEMENT_HELD
    out.setdefault("kind", "dataset")
    out["selected_by"] = out.get("selected_by") or "lexical"
    return stamp_evidence_fields(out)


def _stamp_route(route: dict[str, Any]) -> dict[str, Any]:
    source_id = str(route.get("source_id") or "").strip()
    return stamp_evidence_fields(
        {
            "kind": "declared_route",
            "placement": PLACEMENT_ROUTE,
            "source_id": source_id,
            "title": route.get("label") or source_id,
            "label": route.get("label") or source_id,
            "provider": route.get("provider"),
            "collect_via": source_id,
            "access_mode": route.get("access_mode"),
            "actionable": route.get("actionable"),
            "action": route.get("action"),
            "why": route.get("reason") or "",
            "selection_reason": route.get("reason") or "",
            "selected_by": "gap_routes",
        }
    )


def desk_check(
    gateway: Any,
    query: str,
    *,
    email: str = "",
    limit: int = 12,
) -> dict[str, Any]:
    """One-shot measured desk facts: held (lexical) + declared routes.

    Latency target: tens of milliseconds. No LLM.
    """
    from scripts.research_data_mcp.gap_routes import routes_for_query

    q = str(query or "").strip()
    t0 = time.perf_counter()

    lexical = gateway.discover_search_lexical(q, email=email, limit=limit)
    held: list[dict[str, Any]] = []
    for section in lexical.get("sections") or []:
        if section.get("id") != "held":
            continue
        for row in section.get("rows") or []:
            held.append(_stamp_held(dict(row)))
    held = held[:limit]
    t_lex = time.perf_counter()

    try:
        routes_payload = routes_for_query(q, gateway.repo_root, timeout=5.0)
    except Exception:  # noqa: BLE001
        routes_payload = {"routes": [], "reason": "backend_unavailable"}
    route_reason = str(routes_payload.get("reason") or "")
    routes: list[dict[str, Any]] = []
    for route in routes_payload.get("routes") or []:
        if not isinstance(route, dict):
            continue
        if not str(route.get("source_id") or "").strip():
            continue
        routes.append(_stamp_route(route))
    routes = routes[: min(3, limit)]
    t_end = time.perf_counter()

    strong = strong_held_hits(held)
    held_out = held
    routes_out: list[dict[str, Any]] = [] if strong else routes
    return {
        "query": q,
        "held": held_out,
        "routes": routes_out,
        "route_reason": route_reason,
        "strong_held": strong,
        "held_count": len(held_out),
        "route_count": len(routes_out),
        "index_miss": len(held_out) == 0,
        "timing_ms": {
            "lexical": round((t_lex - t0) * 1000, 1),
            "routes": round((t_end - t_lex) * 1000, 1),
            "total": round((t_end - t0) * 1000, 1),
        },
        "layer": "L0_hands",
    }
