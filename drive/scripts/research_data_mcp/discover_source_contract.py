"""Discover Explore row contract — plain text, identity, exact dedupe, offering taxonomy.

Supports the faculty Discover UI without inventing collectability or collapsing
distinct records. Exact duplicates share the same candidate_key; distinct DOIs,
URLs, and source ids stay separate.
"""

from __future__ import annotations

import html
import re
from typing import Any

from scripts.research_data_mcp.candidate_key import candidate_key, with_candidate_key

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

OFFERING_COLLECTIBLE_DATA = "collectible_data"
OFFERING_PAPER = "paper"
OFFERING_CATALOGUE_RECORD = "catalogue_record"
OFFERING_METADATA_ONLY = "metadata_only"

OFFERING_KINDS = frozenset(
    {
        OFFERING_COLLECTIBLE_DATA,
        OFFERING_PAPER,
        OFFERING_CATALOGUE_RECORD,
        OFFERING_METADATA_ONLY,
    }
)

_PAPER_CAPABILITIES = frozenset({"scholarly_works", "academic_papers", "publications"})
_PAPER_PROVIDERS = frozenset({"openalex", "crossref", "pubmed", "arxiv"})
_CATALOGUE_CAPABILITIES = frozenset({"doi_metadata", "dataset_cards", "repository_files"})
_COLLECT_ACCESS = frozenset(
    {"live_connector", "materialized_bulk", "materialized_instant", "direct_file", "http_manifest"}
)


def plain_text_description(value: Any) -> str:
    """Return clean plain text suitable for Discover row descriptions."""
    text = str(value or "")
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = _WS_RE.sub(" ", text).strip()
    return text


def classify_offering(row: dict[str, Any] | None) -> str:
    """Classify a Discover row into an explicit source/offering taxonomy.

    Distinguishes collectible data/API sources from papers, catalogue records,
    and metadata-only / inspect-only records. Never invents collectability.
    """
    if not isinstance(row, dict):
        return OFFERING_METADATA_ONLY

    caps = {str(c).strip().lower() for c in (row.get("capabilities") or []) if str(c).strip()}
    provider = str(row.get("provider") or row.get("source") or "").strip().lower()
    source_id = str(row.get("source_id") or "").strip().lower()
    kind = str(row.get("kind") or "").strip().lower()
    access = str(row.get("access_mode") or "").strip().lower()
    collect = row.get("collect_via") or []
    if isinstance(collect, str):
        collect = [collect] if collect.strip() else []
    collect_n = [str(c).strip() for c in collect if str(c).strip() and str(c).strip().lower() != "none"]

    resource_type = str(row.get("resource_type") or row.get("type") or "").strip().lower()
    if resource_type in {"journal-article", "article", "paper", "preprint", "book-chapter"}:
        return OFFERING_PAPER
    if caps & _PAPER_CAPABILITIES or provider in _PAPER_PROVIDERS or source_id in _PAPER_PROVIDERS:
        return OFFERING_PAPER

    inspect_only = bool(row.get("inspect_only")) or str(row.get("trust_tier") or "").lower() == "inspect_only"
    if collect_n and not inspect_only:
        return OFFERING_COLLECTIBLE_DATA
    if access in _COLLECT_ACCESS and kind in {"source", "provider", "connector"} and not inspect_only:
        return OFFERING_COLLECTIBLE_DATA

    if kind == "live_candidate" or caps & _CATALOGUE_CAPABILITIES or row.get("doi"):
        if inspect_only or not collect_n:
            # Dataset hub cards without a collect route are metadata-only offerings.
            if "dataset_cards" in caps and not row.get("doi"):
                return OFFERING_METADATA_ONLY
            return OFFERING_CATALOGUE_RECORD

    if inspect_only or str(row.get("availability") or "").lower() in {"metadata_only", "remote_live"}:
        return OFFERING_METADATA_ONLY

    if kind in {"source", "provider", "connector"} and collect_n:
        return OFFERING_COLLECTIBLE_DATA

    return OFFERING_METADATA_ONLY


def _description_for_row(row: dict[str, Any]) -> str:
    for key in ("description", "notes", "summary", "abstract"):
        text = plain_text_description(row.get(key))
        if text:
            return text
    return ""


def suppress_exact_duplicates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop exact candidate_key duplicates; preserve first occurrence and distinct keys."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("candidate_key") or candidate_key(row) or "").strip()
        if key:
            if key in seen:
                continue
            seen.add(key)
        out.append(row)
    return out


def finalize_discover_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Stamp plain description, stable identity, and offering taxonomy on one row."""
    if not isinstance(row, dict):
        return row
    stamped = with_candidate_key(dict(row)) or dict(row)
    key = str(stamped.get("candidate_key") or candidate_key(stamped) or "").strip()
    if key:
        stamped["candidate_key"] = key
    desc = _description_for_row(stamped)
    if desc:
        stamped["description"] = desc
    if stamped.get("notes"):
        stamped["notes"] = plain_text_description(stamped.get("notes"))
    offering = classify_offering(stamped)
    stamped["offering_kind"] = offering
    return stamped


def finalize_discover_rows(rows: list[Any] | None) -> list[dict[str, Any]]:
    """Apply the Discover Explore contract to a result list."""
    finalized: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = finalize_discover_row(row)
        if item is not None:
            finalized.append(item)
    return suppress_exact_duplicates(finalized)
