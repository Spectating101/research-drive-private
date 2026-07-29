#!/usr/bin/env python3
"""Deterministic first-turn grounding for Synthesis Ask."""

from __future__ import annotations

import json
import re
from typing import Any

_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "among",
        "before",
        "between",
        "construct",
        "dataset",
        "define",
        "design",
        "from",
        "have",
        "measure",
        "should",
        "through",
        "using",
        "what",
        "where",
        "which",
        "with",
    }
)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", str(text or "").lower())
        if len(token) >= 4 and token not in _STOPWORDS
    }


def _profile_score(profile: dict[str, Any], query_tokens: set[str]) -> int:
    blob = json.dumps(profile, ensure_ascii=False, default=str).lower()
    return sum(1 for token in query_tokens if token in blob)


def build_synthesis_grounding_brief(
    gateway: Any,
    message: str,
    *,
    candidate_limit: int = 8,
    profile_limit: int = 3,
) -> str:
    """Build a bounded evidence map without making readiness or fit claims."""
    candidates: list[dict[str, Any]] = []
    try:
        from scripts.research_data_mcp.procurement_fast import local_search

        result = local_search(gateway, message, limit=candidate_limit)
        candidates = [
            dict(row)
            for row in (result.get("candidates") or [])[:candidate_limit]
            if isinstance(row, dict)
        ]
    except Exception:
        candidates = []

    profiles: list[dict[str, Any]] = []
    try:
        payload = gateway.synthesis_list_profiles()
        profiles = [
            dict(row)
            for row in payload.get("profiles") or []
            if isinstance(row, dict)
        ]
    except Exception:
        profiles = []
    query_tokens = _tokens(message)
    profiles.sort(
        key=lambda row: (-_profile_score(row, query_tokens), str(row.get("title") or ""))
    )
    profiles = [
        row
        for row in profiles
        if _profile_score(row, query_tokens) > 0
    ][:profile_limit]

    lines = [
        "[Synthesis grounding candidates]",
        "The following records came from the local Library index and existing synthesis profiles.",
        "They are candidates, not proof of fit, coverage, readiness, or a completed construct.",
    ]
    if candidates:
        lines.append("Indexed evidence:")
        for row in candidates:
            title = str(row.get("title") or row.get("dataset_id") or "Dataset").strip()
            dataset_id = str(row.get("dataset_id") or "").strip()
            readiness = str(row.get("analysis_readiness") or "not stated").strip()
            description = str(row.get("description") or "").strip()
            detail = f" — {description[:220]}" if description else ""
            identifier = f" [{dataset_id}]" if dataset_id else ""
            lines.append(f"- {title}{identifier}; readiness: {readiness}{detail}")
    else:
        lines.append("Indexed evidence: no local candidates were returned.")

    if profiles:
        lines.append("Relevant prior synthesis patterns:")
        for row in profiles:
            title = str(row.get("title") or row.get("id") or "Synthesis profile").strip()
            description = str(row.get("description") or "").strip()
            sources = [
                str(source.get("dataset_id") or source.get("id") or source)
                if isinstance(source, dict)
                else str(source)
                for source in (row.get("sources") or [])
            ]
            source_note = f"; sources: {', '.join(sources[:6])}" if sources else ""
            lines.append(f"- {title}: {description[:260]}{source_note}")

    lines.append(
        "Use targeted description/query/comparison tools to verify any candidate before "
        "asserting its role. Do not turn this list into an inventory dump."
    )
    lines.append("[/Synthesis grounding candidates]")
    return "\n".join(lines)[:6000]
