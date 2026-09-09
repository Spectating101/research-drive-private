#!/usr/bin/env python3
"""Semantic widening for explicit Library/agent retrieval requests.

Structured evidence ranking remains primary. Semantic hits are appended only as
a bounded widening step and are labelled as such; they never manufacture a held
state or pretend cosine similarity is source/coverage/schema evidence.
"""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.library_possession import is_library_holding
from scripts.research_data_mcp.library_retrieval import score_registry_asset
from scripts.research_data_mcp.semantic_index import get_semantic_index


def _dataset_id(row: dict[str, Any]) -> str:
    return str(row.get("dataset_id") or row.get("registry_id") or row.get("id") or "").strip()


def _annotate_structured(row: dict[str, Any], query: str) -> dict[str, Any]:
    out = dict(row)
    match = score_registry_asset(out, query)
    if match.get("score"):
        out.setdefault("match_score", match["score"])
        out.setdefault("match_coverage", match["coverage"])
        out.setdefault("match_confidence", match["confidence"])
        out.setdefault("match_terms", list(match["matched_terms"]))
        out.setdefault("match_evidence", list(match["match_evidence"]))
        out.setdefault("match_phrase", bool(match["phrase_match"]))
    return out


def widen_library_result(
    gateway: Any,
    result: dict[str, Any],
    *,
    query: str,
    limit: int,
    held_only: bool,
) -> dict[str, Any]:
    q = str(query or "").strip()
    if not q:
        return result

    bounded = max(1, min(int(limit or 50), 200))
    index = get_semantic_index(gateway)
    mode = "semantic"
    try:
        hits = index.semantic_search(
            q,
            limit=bounded,
            kinds={"registry_dataset"},
            require_ready=True,
        )
    except Exception:
        hits = []
    if not hits:
        mode = "subject"
        hits = index.subject_search(q, limit=bounded, kinds={"registry_dataset"})

    rows = [dict(row) for row in (result.get("datasets") or []) if isinstance(row, dict)]
    by_id = {_dataset_id(row): row for row in rows if _dataset_id(row)}
    hit_by_id = {_dataset_id(hit): hit for hit in hits if _dataset_id(hit)}

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        dataset_id = _dataset_id(row)
        hit = hit_by_id.get(dataset_id)
        out = _annotate_structured(row, q)
        if hit:
            if hit.get("score") is not None:
                out["semantic_score"] = hit.get("score")
            if hit.get("subject_score") is not None:
                out["subject_score"] = hit.get("subject_score")
            out["match_basis"] = "hybrid" if out.get("match_score") else f"{mode}_widening"
        elif out.get("match_score"):
            out["match_basis"] = "structured"
        merged.append(out)
        if dataset_id:
            seen.add(dataset_id)

    for hit in hits:
        dataset_id = _dataset_id(hit)
        if not dataset_id or dataset_id in seen:
            continue
        try:
            row = gateway.describe_dataset(dataset_id)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        if held_only and not is_library_holding(row):
            continue
        out = _annotate_structured(row, q)
        if hit.get("score") is not None:
            out["semantic_score"] = hit.get("score")
        if hit.get("subject_score") is not None:
            out["subject_score"] = hit.get("subject_score")
        out["match_basis"] = "hybrid" if out.get("match_score") else f"{mode}_widening"
        merged.append(out)
        seen.add(dataset_id)
        if len(merged) >= bounded:
            break

    out_result = dict(result)
    out_result["datasets"] = merged[:bounded]
    out_result["returned"] = len(out_result["datasets"])
    out_result["total"] = max(int(result.get("total") or 0), len(out_result["datasets"]))
    out_result["retrieval"] = {
        "mode": "hybrid",
        "structured_primary": True,
        "semantic_requested": True,
        "semantic_mode": mode,
        "semantic_hits": len(hits),
        "held_only": bool(held_only),
        "note": (
            "Structured match evidence remains primary. Semantic/subject hits are bounded widening only; "
            "describe a widened asset before making source, coverage, schema, readiness, or verification claims."
        ),
    }
    return out_result
