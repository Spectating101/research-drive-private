#!/usr/bin/env python3
"""TTL cache for DataCite DOI → repository resolution (unified search hot path)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.procurement_cache import ProcurementCache


def cache_key(doi: str, max_file_bytes: int) -> str:
    clean = doi.strip().removeprefix("https://doi.org/")
    bucket = max_file_bytes // 1_000_000
    return hashlib.sha256(f"{clean}:{bucket}".encode()).hexdigest()[:20]


def get_cached_resolve(repo_root: Path, doi: str, *, max_file_bytes: int) -> dict[str, Any] | None:
    cache = ProcurementCache(repo_root)
    return cache.get("doi_resolve", cache_key(doi, max_file_bytes), ttl_hours=168)


def set_cached_resolve(repo_root: Path, doi: str, resolved: dict[str, Any], *, max_file_bytes: int) -> None:
    cache = ProcurementCache(repo_root)
    cache.set("doi_resolve", cache_key(doi, max_file_bytes), resolved, ttl_hours=168)


def resolve_doi_cached(repo_root: Path, doi: str, *, max_file_bytes: int = 50_000_000) -> dict[str, Any]:
    from scripts.research_data_mcp.datacite_repository import resolve_doi

    hit = get_cached_resolve(repo_root, doi, max_file_bytes=max_file_bytes)
    if hit:
        hit = dict(hit)
        if hit.get("resolve_failed"):
            raise RuntimeError(f"DOI resolve failed (cached): {hit.get('error') or 'unknown'}")
        hit["cache_hit"] = True
        return hit
    try:
        resolved = resolve_doi(doi, max_file_bytes=max_file_bytes)
    except Exception as exc:
        set_cached_resolve(
            repo_root,
            doi,
            {"resolve_failed": True, "error": str(exc), "files": [], "all_files": []},
            max_file_bytes=max_file_bytes,
        )
        raise
    set_cached_resolve(repo_root, doi, resolved, max_file_bytes=max_file_bytes)
    resolved["cache_hit"] = False
    return resolved
