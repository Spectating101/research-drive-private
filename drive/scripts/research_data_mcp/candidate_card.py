#!/usr/bin/env python3
"""Mobus / data-aggregator-style candidate cards — license, format, trust, compare."""

from __future__ import annotations

import re
from typing import Any

from scripts.research_data_mcp.procurement_constants import DOWNLOADABLE_VIA

FIELD_LABELS = {
    "collect_via": "Collect path",
    "license": "License",
    "format": "Format",
    "modality": "Modality",
    "trust_tier": "Trust",
    "score": "Relevance",
    "publisher": "Publisher",
    "file_summary": "Files",
}


def _ext_from_name(name: str) -> str:
    m = re.search(r"\.([a-z0-9]{2,5})$", (name or "").lower())
    return m.group(1) if m else ""


def _infer_format(row: dict[str, Any], files: list[dict[str, Any]]) -> str:
    explicit = str(row.get("format") or row.get("media_type") or "").strip()
    if explicit:
        return explicit.split("/")[-1].upper() if "/" in explicit else explicit
    exts: list[str] = []
    for f in files[:6]:
        ext = _ext_from_name(str(f.get("key") or f.get("filename") or ""))
        if ext and ext not in exts:
            exts.append(ext)
    if exts:
        return ", ".join(exts[:4]).upper()
    kind = str(row.get("kind") or "")
    if kind == "local_registry":
        return "Panel"
    if kind == "huggingface":
        return "HF dataset"
    return "—"


def _infer_modality(row: dict[str, Any], blob: str) -> str:
    if row.get("kind") == "huggingface":
        return "ML corpus"
    if any(w in blob for w in ("panel", "time series", "timeseries", "daily", "weekly")):
        return "Time series panel"
    if any(w in blob for w in ("graph", "network", "kg", "knowledge")):
        return "Graph / events"
    if any(w in blob for w in ("sqlite", "database", "table")):
        return "Tabular"
    if any(w in blob for w in ("text", "headline", "article", "nlp")):
        return "Text"
    return "Tabular"


def _file_summary(files: list[dict[str, Any]]) -> str:
    if not files:
        return "—"
    n = len(files)
    total = sum(int(f.get("size") or f.get("bytes") or 0) for f in files)
    if total > 1_000_000_000:
        size = f"{total / 1_000_000_000:.1f} GB"
    elif total > 1_000_000:
        size = f"{total / 1_000_000:.1f} MB"
    elif total > 0:
        size = f"{total / 1_000:.0f} KB"
    else:
        size = ""
    base = f"{n} file{'s' if n != 1 else ''}"
    return f"{base} · {size}" if size else base


def _trust_tier(card: dict[str, Any]) -> str:
    via = str(card.get("collect_via") or "")
    status = str(card.get("status") or "")
    if via == "local_open" or card.get("analysis_readiness") == "instant":
        return "lab_ready"
    if via == "datacite" and card.get("can_collect") is not False and status not in {"error", "metadata_only"}:
        return "downloadable"
    if via in {"spectator", "magic", "queue", "pipeline"}:
        return "acquisition_route"
    if status in {"metadata_only", "sample_only"} or card.get("can_collect") is False:
        return "metadata_only"
    return "unknown"


def procureability_label(card: dict[str, Any]) -> str:
    """Short human label for chat/search replies."""
    via = str(card.get("collect_via") or "")
    readiness = str(card.get("analysis_readiness") or "")
    if readiness == "instant" or via == "local_open":
        return "Query now"
    if via == "queue":
        est = str(card.get("estimated_runtime") or "").strip()
        if card.get("refresh_only"):
            return f"Refresh (queue{': ' + est if est else ''})"
        return f"Collect (queue{': ' + est if est else ''})"
    if via in {"http_manifest", "datacite"}:
        return "Collect now"
    if via == "huggingface":
        return "HF collect"
    if via in {"spectator", "web_scrape"}:
        return "Scrape"
    if via == "magic":
        return "Source pipeline"
    if via == "pipeline":
        return "Run pipeline"
    if card.get("can_collect") is False:
        return "Metadata only"
    return "Review"


def enrich_candidate_card(card: dict[str, Any], row: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach catalog-style facets used by procurement UI compare tables."""
    row = row or {}
    resolved = row.get("resolved") or {}
    files = resolved.get("files") or row.get("files") or []
    blob = " ".join(
        str(x)
        for x in (
            card.get("title"),
            card.get("dataset_id"),
            row.get("description"),
            row.get("domain"),
        )
    ).lower()

    license_val = str(row.get("license") or row.get("rights") or row.get("rightsList") or "").strip()
    if not license_val and row.get("kind") == "local_registry":
        license_val = "Lab internal"

    card.setdefault("publisher", str(row.get("publisher") or row.get("source") or card.get("source") or "—"))
    published = str(row.get("published") or row.get("year") or row.get("publicationYear") or "").strip()
    if published:
        card.setdefault("published", published[:10])

    card.setdefault("license", license_val or "—")
    card.setdefault("format", _infer_format(row, files))
    card.setdefault("modality", _infer_modality(row, blob))
    card.setdefault("file_summary", _file_summary(files))
    card.setdefault("trust_tier", _trust_tier(card))
    card.setdefault("procureability_label", procureability_label(card))

    proc = row.get("procureability") or {}
    if proc.get("tone"):
        card.setdefault("tone", proc["tone"])

    return card


def normalize_candidate_scores(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return candidates
    max_score = max(float(c.get("score") or 0) for c in candidates) or 1.0
    for c in candidates:
        sc = float(c.get("score") or 0)
        c["score_pct"] = round(100 * sc / max_score) if max_score > 0 else 0
    return candidates


def _display_value(card: dict[str, Any], field: str) -> str:
    if field == "badges":
        return ", ".join(card.get("badges") or []) or "—"
    if field == "score":
        sc = card.get("score")
        return f"{sc}" if sc is not None else "—"
    val = card.get(field)
    return str(val) if val not in (None, "") else "—"


def build_compare_table(
    candidates: list[dict[str, Any]],
    indices: list[int],
) -> dict[str, Any] | None:
    """Structured side-by-side compare (Recure / Mobus pattern) for the desk UI."""
    picks = [candidates[i - 1] for i in indices if 1 <= i <= len(candidates)]
    if len(picks) < 2:
        return None

    compare_fields = [
        "collect_via",
        "license",
        "format",
        "modality",
        "trust_tier",
        "score",
        "publisher",
        "file_summary",
    ]
    rows = [
        {
            "field": field,
            "label": FIELD_LABELS.get(field, field.replace("_", " ").title()),
            "values": [_display_value(p, field) for p in picks],
        }
        for field in compare_fields
    ]

    downloadable = [c for c in picks if str(c.get("collect_via") or "") in DOWNLOADABLE_VIA]
    recommendation: dict[str, Any] | None = None
    if downloadable:
        best = max(downloadable, key=lambda x: float(x.get("score") or 0))
        via = str(best.get("collect_via") or "")
        if via in {"spectator", "magic"}:
            reason = "Best acquisition route when bytes are not directly downloadable."
        else:
            reason = "Highest relevance among directly collectible options."
        recommendation = {
            "index": best.get("index"),
            "title": best.get("title"),
            "collect_via": via,
            "reason": reason,
        }

    return {
        "indices": [p.get("index") for p in picks],
        "candidates": picks,
        "rows": rows,
        "recommendation": recommendation,
    }
