#!/usr/bin/env python3
"""Honest evidence placement for Discover / Library / Synthesis.

Scripts must not invent research judgment. Placement is factual possession or
route shape; ``why`` is only an agent- or author-supplied sentence (never a
canned pipeline phrase).
"""

from __future__ import annotations

from typing import Any

PLACEMENT_HELD = "held"
PLACEMENT_ROUTE = "route"
PLACEMENT_CONTEXT = "context"
PLACEMENT_MISSING = "missing"

CANNED_WHY = frozenset(
    {
        "matched on meaning, not wording",
        "matched on meaning not wording",
    }
)


def clean_why(value: Any) -> str:
    """Return a real why sentence, or empty when the value is wallpaper."""
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""
    if text.lower().rstrip(".") in CANNED_WHY:
        return ""
    return text[:240]


def evidence_placement(row: dict[str, Any] | None, *, lab_ids: set[str] | None = None) -> str:
    """Factual placement for a candidate or evidence node.

    held    — Library registry holding (query-ready, connected, or metadata card)
    route   — collectable / external source with a path to acquire or inspect
    context — reference / web / non-actionable context only
    """
    if not isinstance(row, dict):
        return PLACEMENT_CONTEXT

    explicit = str(row.get("placement") or "").strip().lower()
    if explicit in {PLACEMENT_HELD, PLACEMENT_ROUTE, PLACEMENT_CONTEXT, PLACEMENT_MISSING}:
        return explicit

    status = str(row.get("status") or "").strip().lower()
    if status in {"held", "queryable", "query_ready"}:
        return PLACEMENT_HELD
    if status in {"missing", "needs_access", "sourceable"}:
        return PLACEMENT_MISSING if status == "missing" else PLACEMENT_ROUTE

    dataset_id = str(row.get("dataset_id") or row.get("id") or "").strip()
    if lab_ids and dataset_id and dataset_id in lab_ids:
        return PLACEMENT_HELD
    if row.get("local_ready") or row.get("in_vault") or row.get("in_lab") is True:
        return PLACEMENT_HELD

    kind = str(row.get("kind") or row.get("type") or "").strip().lower()
    if kind in {"local_registry", "lab", "registry_dataset", "dataset"} and dataset_id:
        return PLACEMENT_HELD
    if kind in {"paper", "article", "literature", "publication", "web", "page", "context"}:
        return PLACEMENT_CONTEXT

    if row.get("collect_via") or row.get("collectable") or row.get("url") or row.get("doi"):
        return PLACEMENT_ROUTE
    if row.get("connector_id") or row.get("source_id") or row.get("hf_id"):
        return PLACEMENT_ROUTE

    return PLACEMENT_CONTEXT


def stamp_evidence_fields(
    row: dict[str, Any],
    *,
    lab_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Attach placement + cleaned why; drop canned selection_reason wallpaper."""
    out = dict(row)
    why = clean_why(out.get("why") or out.get("selection_reason"))
    out["placement"] = evidence_placement(out, lab_ids=lab_ids)
    if why:
        out["why"] = why
        out["selection_reason"] = why
    else:
        out.pop("why", None)
        # Keep empty selection_reason out of the wire so UI does not render wallpaper.
        if clean_why(out.get("selection_reason")) == "":
            out.pop("selection_reason", None)
    # Embedding filler must never look like a Recommended hit.
    if str(out.get("selected_by") or "") == "semantic" and not why:
        out["placement"] = PLACEMENT_CONTEXT
    return out


def drop_semantic_filler(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove embedding backstop rows that only carried canned why."""
    kept: list[dict[str, Any]] = []
    for row in candidates or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("selected_by") or "") == "semantic":
            why = clean_why(row.get("selection_reason") or row.get("why"))
            if not why:
                continue
        kept.append(row)
    return kept
