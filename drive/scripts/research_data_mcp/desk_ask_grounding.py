#!/usr/bin/env python3
"""Mandatory L0 Ask grounding — same desk measure Discover uses.

Probe/default Ask injects query-scoped held + declared routes before Composer
drafts. Not Discover's full enrich stack: conversational L1 on authoritative L0.

When the typed Ask diverges from the open Discover/Library/Synthesis workspace
query, both are measured (dual measure) so Ask assists the open surface without
ignoring the researcher's actual question.
"""

from __future__ import annotations

import re
from typing import Any


def strip_ask_message(message: str) -> str:
    q = str(message or "").strip()
    return re.sub(r"^\[context:[^\]]*\]\s*", "", q, flags=re.I).strip() or q


def resolve_workspace_measure_query(rail_context: dict[str, Any] | None = None) -> str:
    rail = rail_context if isinstance(rail_context, dict) else {}
    workspace = rail.get("workspace") if isinstance(rail.get("workspace"), dict) else {}
    surface = str(workspace.get("surface") or rail.get("surface") or rail.get("tab") or "").lower()
    open_q = str(workspace.get("query") or rail.get("search_query") or "").strip()
    objective = str(workspace.get("objective") or "").strip()
    selected = rail.get("selected") if isinstance(rail.get("selected"), dict) else {}
    selected_objective = str(selected.get("objective") or "").strip()
    if open_q and surface in {"discover", "browse", "library", "explore"}:
        return open_q[:240]
    if objective and surface in {"synthesis"}:
        return objective[:240]
    if selected_objective and surface in {"synthesis"}:
        return selected_objective[:240]
    return (open_q or objective or selected_objective)[:240]


def resolve_ask_measure_query(message: str, rail_context: dict[str, Any] | None = None) -> str:
    """Primary L0 measure query — open workspace when present, else typed Ask."""
    typed = strip_ask_message(message)
    open_q = resolve_workspace_measure_query(rail_context)
    return (open_q or typed)[:240]


def _norm_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(t) > 1}


_ASK_STOPWORDS = {
    "what",
    "which",
    "how",
    "can",
    "could",
    "should",
    "would",
    "do",
    "does",
    "did",
    "is",
    "are",
    "was",
    "were",
    "the",
    "a",
    "an",
    "to",
    "for",
    "from",
    "this",
    "that",
    "these",
    "those",
    "next",
    "now",
    "here",
    "there",
    "about",
    "with",
    "into",
    "over",
    "under",
    "and",
    "or",
    "of",
    "in",
    "on",
    "my",
    "our",
    "we",
    "i",
    "me",
    "it",
    "its",
    "please",
    "collect",
    "query",
    "held",
    "route",
    "routes",
    "explore",
    "library",
    "ask",
    "compare",
    "coverage",
    "also",
    "versus",
    "vs",
    "against",
    "than",
    "same",
    "open",
    "still",
    "again",
    "just",
    "more",
    "less",
}


def queries_diverge(primary: str, secondary: str) -> bool:
    """True when the typed Ask is a materially different question from open workspace."""
    a = str(primary or "").strip().lower()
    b = str(secondary or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return False
    if a in b or b in a:
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        if len(shorter) < 48 and len(_norm_tokens(shorter) - _norm_tokens(longer)) <= 1:
            return False
    ta, tb = _norm_tokens(a), _norm_tokens(b)
    if not ta or not tb:
        return True
    ta_content = {t for t in ta if t not in _ASK_STOPWORDS and len(t) > 2}
    tb_content = {t for t in tb if t not in _ASK_STOPWORDS and len(t) > 2}
    # Short follow-ups ("what should I collect next?") stay on the open workspace.
    if len(b) < 96 and not (tb_content - ta_content):
        return False
    # Distinct subject on both sides (Taiwan vs Indonesia) → dual measure even when
    # shared domain words like "stock prices" inflate raw token overlap.
    if (tb_content - ta_content) and (ta_content - tb_content):
        return True
    if not ta_content or not tb_content:
        return True
    overlap = len(ta_content & tb_content) / max(1, min(len(ta_content), len(tb_content)))
    return overlap < 0.45


def resolve_ask_measure_queries(
    message: str,
    rail_context: dict[str, Any] | None = None,
) -> tuple[str, str | None]:
    """Return (primary, secondary?) — secondary only when typed Ask diverges from open work."""
    typed = strip_ask_message(message)[:240]
    open_q = resolve_workspace_measure_query(rail_context)
    primary = (open_q or typed)[:240]
    if open_q and typed and queries_diverge(open_q, typed):
        return open_q[:240], typed
    return primary, None


def _run_desk_check(gateway: Any, q: str, *, candidate_limit: int) -> dict[str, Any]:
    from scripts.research_data_mcp.discover_desk import desk_check

    try:
        desk = desk_check(gateway, q, limit=candidate_limit)
    except Exception:  # noqa: BLE001
        return {
            "held": [],
            "routes": [],
            "strong_held": False,
            "held_count": 0,
            "route_count": 0,
            "route_reason": "desk_check_failed",
            "query": q,
        }
    return {
        "held": [dict(r) for r in (desk.get("held") or [])[:candidate_limit] if isinstance(r, dict)],
        "routes": [dict(r) for r in (desk.get("routes") or [])[:3] if isinstance(r, dict)],
        "strong_held": bool(desk.get("strong_held")),
        "held_count": int(desk.get("held_count") or 0),
        "route_count": int(desk.get("route_count") or 0),
        "route_reason": str(desk.get("route_reason") or ""),
        "query": q,
    }


def _merge_held(primary: list[dict[str, Any]], secondary: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in list(primary) + list(secondary):
        if not isinstance(row, dict):
            continue
        key = str(row.get("dataset_id") or row.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _merge_routes(primary: list[dict[str, Any]], secondary: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in list(primary) + list(secondary):
        if not isinstance(row, dict):
            continue
        key = str(row.get("source_id") or row.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def measure_ask_desk(
    gateway: Any,
    message: str,
    *,
    candidate_limit: int = 8,
    rail_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Discover's L0 desk_check for open workspace and, when needed, typed Ask."""
    primary_q, secondary_q = resolve_ask_measure_queries(message, rail_context)
    primary = _run_desk_check(gateway, primary_q, candidate_limit=candidate_limit)
    secondary: dict[str, Any] | None = None
    if secondary_q:
        secondary = _run_desk_check(gateway, secondary_q, candidate_limit=min(candidate_limit, 6))

    held = list(primary.get("held") or [])
    routes = list(primary.get("routes") or [])
    strong = bool(primary.get("strong_held"))
    if secondary:
        held = _merge_held(held, list(secondary.get("held") or []), limit=candidate_limit)
        routes = _merge_routes(routes, list(secondary.get("routes") or []))
        strong = strong or bool(secondary.get("strong_held"))

    held = _inject_selected_library_asset(held, rail_context, limit=candidate_limit)
    held = _inject_synthesis_mapped_evidence(held, rail_context, limit=candidate_limit)
    held = _inject_synthesis_related_holdings(
        gateway, held, rail_context, limit=candidate_limit
    )

    return {
        "held": held,
        "routes": routes,
        "strong_held": strong or any(bool(r.get("local_ready")) for r in held[:3]),
        "held_count": max(
            int(primary.get("held_count") or 0)
            + (int(secondary.get("held_count") or 0) if secondary else 0),
            len(held),
        ),
        "route_count": len(routes) if not strong else int(primary.get("route_count") or 0),
        "route_reason": str(primary.get("route_reason") or ""),
        "query": primary_q,
        "secondary_query": secondary_q or "",
        "primary": {
            "query": primary_q,
            "held_count": int(primary.get("held_count") or 0),
            "route_count": int(primary.get("route_count") or 0),
            "strong_held": bool(primary.get("strong_held")),
        },
        "secondary": (
            {
                "query": secondary_q,
                "held_count": int(secondary.get("held_count") or 0),
                "route_count": int(secondary.get("route_count") or 0),
                "strong_held": bool(secondary.get("strong_held")),
            }
            if secondary and secondary_q
            else None
        ),
    }


def _inject_selected_library_asset(
    held: list[dict[str, Any]],
    rail_context: dict[str, Any] | None,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Ensure the open Library selection's labelling is present in DESK_FACTS held rows."""
    rail = rail_context if isinstance(rail_context, dict) else {}
    selected = rail.get("selected") if isinstance(rail.get("selected"), dict) else {}
    entity = rail.get("entity") if isinstance(rail.get("entity"), dict) else {}
    workspace = rail.get("workspace") if isinstance(rail.get("workspace"), dict) else {}
    dataset_id = str(
        selected.get("dataset_id")
        or rail.get("dataset_id")
        or (entity.get("id") if entity.get("kind") == "dataset" else "")
        or workspace.get("dataset_id")
        or ""
    ).strip()
    if not dataset_id:
        return held[:limit]
    title = str(
        selected.get("title")
        or entity.get("title")
        or workspace.get("dataset_title")
        or dataset_id
    ).strip()
    row = {
        "dataset_id": dataset_id,
        "title": title,
        "analysis_readiness": str(
            selected.get("analysis_readiness")
            or selected.get("readiness")
            or selected.get("canonical_readiness")
            or ""
        ).strip(),
        "grain": str(selected.get("grain") or "").strip(),
        "coverage": str(selected.get("coverage") or selected.get("date_range") or "").strip(),
        "local_ready": bool(selected.get("local_ready") or selected.get("query_ready")),
    }
    for key in ("archive_verified", "registry_verified"):
        if selected.get(key) is not None:
            row[key] = selected.get(key)
    return _merge_held([row], held, limit=limit)


def _inject_synthesis_mapped_evidence(
    held: list[dict[str, Any]],
    rail_context: dict[str, Any] | None,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Prefer evidence nodes already mapped on the open Synthesis thread."""
    rail = rail_context if isinstance(rail_context, dict) else {}
    workspace = rail.get("workspace") if isinstance(rail.get("workspace"), dict) else {}
    selected = rail.get("selected") if isinstance(rail.get("selected"), dict) else {}
    mapped = workspace.get("mapped_evidence") or selected.get("mapped_evidence") or []
    if not isinstance(mapped, list) or not mapped:
        return held[:limit]
    rows: list[dict[str, Any]] = []
    for item in mapped:
        if not isinstance(item, dict):
            continue
        dataset_id = str(item.get("dataset_id") or "").strip()
        if not dataset_id:
            continue
        rows.append(
            {
                "dataset_id": dataset_id,
                "title": str(item.get("title") or dataset_id).strip(),
                "grain": str(item.get("grain") or "").strip(),
                "coverage": str(item.get("coverage") or "").strip(),
                "analysis_readiness": str(item.get("analysis_readiness") or item.get("status") or "").strip(),
                "role": str(item.get("role") or "").strip(),
                "local_ready": bool(item.get("local_ready")),
            }
        )
    if not rows:
        return held[:limit]
    return _merge_held(rows, held, limit=limit)


def _registry_row_as_held(spec: dict[str, Any], *, role: str = "") -> dict[str, Any]:
    from scripts.research_data_mcp.vault_meaning import faculty_face, is_ops_face

    face = faculty_face(spec)
    title = str(face.get("title") or "").strip()
    # Prefer description snippet only when title still looks like an id
    if is_ops_face(title):
        title = str(spec.get("dataset_id") or "").strip()
    return {
        "dataset_id": str(spec.get("dataset_id") or "").strip(),
        "title": title,
        "description": str(face.get("description") or "")[:240] or None,
        "analysis_readiness": str(spec.get("analysis_readiness") or "").strip(),
        "grain": str(spec.get("grain") or "").strip(),
        "coverage": str(spec.get("coverage") or spec.get("date_range") or "").strip(),
        "local_ready": bool(
            spec.get("local_ready")
            or str(spec.get("analysis_readiness") or "").lower() in {"instant", "query_ready"}
        ),
        "role": role,
        "source_dataset_id": str(spec.get("source_dataset_id") or "").strip() or None,
    }


def _collect_related_dataset_ids(
    held: list[dict[str, Any]],
    rail_context: dict[str, Any] | None,
) -> list[str]:
    """Input/output IDs linked to open Synthesis workspace or already-held synthesis rows."""
    ids: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        did = str(value or "").strip()
        if not did or did in seen:
            return
        seen.add(did)
        ids.append(did)

    rail = rail_context if isinstance(rail_context, dict) else {}
    workspace = rail.get("workspace") if isinstance(rail.get("workspace"), dict) else {}
    selected = rail.get("selected") if isinstance(rail.get("selected"), dict) else {}
    for blob in (workspace, selected):
        spec = blob.get("execution_spec") if isinstance(blob.get("execution_spec"), dict) else {}
        add(spec.get("input_dataset_id"))
        add(spec.get("output_dataset_id"))
        add(blob.get("output_dataset_id"))
        add(blob.get("dataset_id"))
        for node in blob.get("mapped_evidence") or []:
            if isinstance(node, dict):
                add(node.get("dataset_id"))

    for row in held:
        if not isinstance(row, dict):
            continue
        add(row.get("dataset_id"))
        add(row.get("source_dataset_id"))
        # Titles sometimes embed source craft ids — keep explicit fields only.

    return ids


def _inject_synthesis_related_holdings(
    gateway: Any,
    held: list[dict[str, Any]],
    rail_context: dict[str, Any] | None,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Expand DESK_FACTS with synthesis input↔output peers from the registry.

    Faculty Ask for “Keeling acceleration” should see both the clean monthly
    input and the materialised acceleration panel — not only one lexical hit.
    """
    seed_ids = _collect_related_dataset_ids(held, rail_context)
    if not seed_ids and not held:
        return held[:limit]

    describe = getattr(gateway, "describe_dataset", None)
    if not callable(describe):
        return held[:limit]

    related_rows: list[dict[str, Any]] = []
    expand_ids: list[str] = list(seed_ids)

    def _peer_ids_from_spec(spec: dict[str, Any]) -> list[str]:
        peers: list[str] = []
        for key in ("source_dataset_id",):
            peer = str(spec.get(key) or "").strip()
            if peer:
                peers.append(peer)
        lineage = spec.get("lineage") if isinstance(spec.get("lineage"), dict) else {}
        for key in ("source_dataset_id", "input_dataset_id"):
            peer = str(lineage.get(key) or "").strip()
            if peer:
                peers.append(peer)
        upstream = lineage.get("upstream_dataset_ids") or []
        if isinstance(upstream, list):
            for peer in upstream:
                peer_id = str(peer or "").strip()
                if peer_id:
                    peers.append(peer_id)
        exec_spec = spec.get("execution_spec") if isinstance(spec.get("execution_spec"), dict) else {}
        peer = str(exec_spec.get("input_dataset_id") or "").strip()
        if peer:
            peers.append(peer)
        out_id = str(exec_spec.get("output_dataset_id") or "").strip()
        if out_id:
            peers.append(out_id)
        return peers

    def _spec_cites_seed(spec: dict[str, Any], seed: str) -> bool:
        if not seed:
            return False
        if seed in _peer_ids_from_spec(spec):
            return True
        did = str(spec.get("dataset_id") or "")
        return bool(did.startswith("synthesis_") and seed and seed in did)

    # Reverse: held inputs → synthesis_* outputs that cite them (bounded catalog scan).
    list_fn = getattr(gateway, "list_datasets", None)
    if callable(list_fn):
        for seed in list(seed_ids)[:6]:
            try:
                payload = list_fn(q=seed, limit=16)
            except Exception:  # noqa: BLE001
                continue
            rows = []
            if isinstance(payload, dict):
                rows = list(payload.get("datasets") or payload.get("items") or [])
            elif isinstance(payload, list):
                rows = payload
            for row in rows:
                if not isinstance(row, dict):
                    continue
                did = str(row.get("dataset_id") or "").strip()
                if not did or did in expand_ids:
                    continue
                if _spec_cites_seed(row, seed) or did.startswith("synthesis_"):
                    # Prefer cite proof; allow synthesis_* lexical neighbors of the seed id.
                    if _spec_cites_seed(row, seed) or seed.replace("-", "_") in did:
                        expand_ids.append(did)

    # Bounded multi-hop expand: synthesis ↔ input ↔ raw craft.
    described: dict[str, dict[str, Any]] = {}
    pending: list[str] = list(dict.fromkeys(expand_ids))
    seen_pending: set[str] = set()
    while pending and len(described) < max(limit * 3, 12):
        did = pending.pop(0)
        if not did or did in seen_pending:
            continue
        seen_pending.add(did)
        try:
            spec = describe(did)
        except Exception:  # noqa: BLE001 — missing ids are skipped
            continue
        if not isinstance(spec, dict) or not spec.get("dataset_id"):
            continue
        described[str(spec["dataset_id"])] = spec
        for peer in _peer_ids_from_spec(spec):
            if peer and peer not in seen_pending:
                pending.append(peer)

    # Prefer pairing: if we hold a synthesis_* output, mark its input; and vice versa.
    held_ids = {
        str(r.get("dataset_id") or "").strip()
        for r in held
        if isinstance(r, dict) and str(r.get("dataset_id") or "").strip()
    }
    for did, spec in described.items():
        role = ""
        if did.startswith("synthesis_"):
            role = "synthesis_output"
        elif did in held_ids:
            role = "held"
        elif str(spec.get("source_dataset_id") or "").strip() or did.startswith("keeling_"):
            role = "synthesis_input"
        related_rows.append(_registry_row_as_held(spec, role=role))

    if not related_rows:
        return held[:limit]
    return _merge_held(related_rows, held, limit=limit)


def build_ask_desk_grounding_brief(
    gateway: Any,
    message: str,
    *,
    candidate_limit: int = 8,
    rail_context: dict[str, Any] | None = None,
) -> str:
    """Bounded DESK_FACTS for Ask — held/routes only, no catalog wallpaper."""
    desk = measure_ask_desk(
        gateway, message, candidate_limit=candidate_limit, rail_context=rail_context
    )
    return format_ask_desk_grounding_brief(desk)


def _held_label_suffix(row: dict[str, Any]) -> str:
    bits: list[str] = []
    readiness = str(
        row.get("analysis_readiness") or row.get("readiness") or row.get("canonical_readiness") or ""
    ).strip()
    grain = str(row.get("grain") or "").strip()
    coverage = str(
        row.get("coverage") or row.get("date_range") or row.get("temporal_coverage") or ""
    ).strip()
    if readiness:
        bits.append(f"readiness={readiness[:48]}")
    if grain:
        bits.append(f"grain={grain[:48]}")
    if coverage:
        bits.append(f"coverage={coverage[:64]}")
    if row.get("local_ready") is True:
        bits.append("local_ready")
    return (" · " + " · ".join(bits)) if bits else ""


def format_ask_desk_grounding_brief(desk: dict[str, Any]) -> str:
    held = [dict(r) for r in (desk.get("held") or []) if isinstance(r, dict)]
    routes = [dict(r) for r in (desk.get("routes") or []) if isinstance(r, dict)]
    strong = bool(desk.get("strong_held"))
    q = str(desk.get("query") or "").strip()
    secondary_q = str(desk.get("secondary_query") or "").strip()

    lines = [
        "[Ask DESK_FACTS]",
        "Measured via research_discover_desk (L0 hands) — same measure as Discover.",
        "Authoritative for vault holdings and declared collect routes on this question.",
        "Library labelling (readiness / grain / coverage) below is from registry measure — do not invent.",
        "Answer from this block in short prose NOW.",
        "Do NOT call research_discover_desk / collection_status / vault inventory tools — already measured.",
        "Call MCP only if the user asks to collect, query, sample, hydrate, or submit a job.",
        "Mutating collect/submit requires an explicit reviewable proposal — do not claim queued without a tool result.",
        "Do not invent dataset_ids or source_ids outside this block.",
        "When naming a holding, copy dataset_id EXACTLY from the [brackets] — never substitute a related craft_* id or title fragment.",
        "Do not claim the vault is empty of routes when routes are listed below.",
    ]
    if q:
        lines.append(f"Open workspace / primary query: {q[:200]}")
    if secondary_q:
        lines.append(
            f"Typed Ask (also measured — diverges from open workspace): {secondary_q[:200]}"
        )

    if strong and held:
        lines.append(f"Strong Library holdings ({len(held)}):")
        for row in held:
            title = str(row.get("title") or row.get("dataset_id") or "Dataset").strip()
            dataset_id = str(row.get("dataset_id") or "").strip()
            identifier = f" [{dataset_id}]" if dataset_id else ""
            lines.append(f"- held: {title}{identifier}{_held_label_suffix(row)}")
    elif held:
        lines.append(f"Weak/lexical Library hits ({len(held)}) — verify before use:")
        for row in held:
            title = str(row.get("title") or row.get("dataset_id") or "Dataset").strip()
            dataset_id = str(row.get("dataset_id") or "").strip()
            identifier = f" [{dataset_id}]" if dataset_id else ""
            lines.append(f"- held?: {title}{identifier}{_held_label_suffix(row)}")
    else:
        lines.append("Library holdings: none measured for this question.")

    if routes and not strong:
        lines.append(f"Declared collectable routes ({len(routes)}):")
        for row in routes:
            title = str(
                row.get("title") or row.get("label") or row.get("source_id") or ""
            ).strip()
            sid = str(row.get("source_id") or "").strip()
            why = str(row.get("why") or row.get("selection_reason") or "").strip()[:160]
            detail = f" — {why}" if why else ""
            lines.append(f"- route: {title} [{sid}]{detail}")
        lines.append(
            "When the user asks what is held / how to collect, name these routes. "
            "Prefer collect_via / research_craft_collect_plan over inventing a blank URL ask."
        )
    elif not strong:
        lines.append("Declared collectable routes: none for this question.")

    lines.append(
        "Composer owns conversational judgment; DESK_FACTS own holdings/routes/labelling truth."
    )
    lines.append("[/Ask DESK_FACTS]")
    return "\n".join(lines)[:6000]


def _serialize_held_row(row: dict[str, Any]) -> dict[str, Any] | None:
    title = str(
        row.get("title")
        or row.get("display_name")
        or row.get("name")
        or row.get("dataset_id")
        or ""
    ).strip()
    dataset_id = str(row.get("dataset_id") or "").strip()
    if not title and not dataset_id:
        return None
    # Never surface opaque ids as the faculty title when a name exists elsewhere.
    if title == dataset_id:
        alt = str(row.get("display_name") or row.get("name") or "").strip()
        if alt:
            title = alt
    out: dict[str, Any] = {"title": title or dataset_id, "dataset_id": dataset_id}
    readiness = str(
        row.get("analysis_readiness") or row.get("readiness") or row.get("canonical_readiness") or ""
    ).strip()
    grain = str(row.get("grain") or "").strip()
    coverage = str(
        row.get("coverage") or row.get("date_range") or row.get("temporal_coverage") or ""
    ).strip()
    if readiness:
        out["analysis_readiness"] = readiness[:64]
    if grain:
        out["grain"] = grain[:64]
    if coverage:
        out["coverage"] = coverage[:96]
    if row.get("local_ready") is True:
        out["local_ready"] = True
    return out


def serialize_desk_facts_ui(desk: dict[str, Any]) -> dict[str, Any]:
    """Wire payload for Ask UI — measured rows + Library labelling fields."""
    held_out: list[dict[str, Any]] = []
    for row in desk.get("held") or []:
        if not isinstance(row, dict):
            continue
        serialized = _serialize_held_row(row)
        if serialized:
            held_out.append(serialized)

    routes_out: list[dict[str, str]] = []
    for row in desk.get("routes") or []:
        if not isinstance(row, dict):
            continue
        title = str(
            row.get("title") or row.get("label") or row.get("source_id") or ""
        ).strip()
        source_id = str(row.get("source_id") or row.get("collect_via") or "").strip()
        if not title and not source_id:
            continue
        routes_out.append({"title": title or source_id, "source_id": source_id})

    strong = bool(desk.get("strong_held"))
    secondary_q = str(desk.get("secondary_query") or "").strip()
    payload: dict[str, Any] = {
        "query": str(desk.get("query") or "")[:200],
        "strong_held": strong,
        "held_count": int(desk.get("held_count") or len(held_out)),
        "route_count": int(desk.get("route_count") or len(routes_out)),
        "held": held_out[:8],
        "routes": [] if strong else routes_out[:3],
        "engine": "research_discover_desk",
    }
    if secondary_q:
        payload["secondary_query"] = secondary_q[:200]
        if isinstance(desk.get("secondary"), dict):
            payload["secondary"] = desk.get("secondary")
    return payload
