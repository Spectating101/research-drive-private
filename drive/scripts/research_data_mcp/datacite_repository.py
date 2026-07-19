#!/usr/bin/env python3
"""Resolve DataCite DOIs to repository download URLs (Zenodo, OSF, etc.)."""

from __future__ import annotations

import re
from typing import Any

from scripts.research_data_mcp import datacite_client
from scripts.research_data_mcp.repository_adapters import (
    DEFAULT_MAX_FILE_BYTES,
    follow_landing_url,
    repository_slug,
    resolve_repository,
)

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\]>\"']+)", re.I)


def extract_doi(text: str) -> str | None:
    match = DOI_RE.search(text or "")
    if not match:
        return None
    return match.group(1).rstrip(".,;)")


def zenodo_files(landing_url: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> list[dict[str, Any]]:
    from scripts.research_data_mcp.repository_adapters import zenodo_files as _zenodo_files

    return _zenodo_files(landing_url, max_file_bytes=max_file_bytes)


def resolve_doi(doi: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> dict[str, Any]:
    clean = doi.strip().removeprefix("https://doi.org/")
    meta = datacite_client.get_doi(clean)
    landing = str(meta.get("url") or f"https://doi.org/{clean}")
    repo = resolve_repository(landing, max_file_bytes=max_file_bytes)
    if not repo.get("files") and "doi.org" in landing:
        landing = follow_landing_url(landing)
        repo = resolve_repository(landing, max_file_bytes=max_file_bytes)
    files = repo.get("files") or []
    chosen = files[0] if files else None
    return {
        "doi": clean,
        "title": meta.get("title") or clean,
        "publisher": meta.get("publisher"),
        "publication_year": meta.get("publication_year"),
        "resource_type": meta.get("resource_type"),
        "license": meta.get("license"),
        "metadata": meta,
        "repository": repo.get("repository"),
        "landing_url": repo.get("landing_url") or landing,
        "files": files,
        "all_files": repo.get("all_files") or files,
        "chosen_file": chosen,
    }


def search_and_resolve(
    query: str,
    *,
    created: str = "",
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    limit: int = 8,
) -> dict[str, Any]:
    payload = datacite_client.search(query, created=created, page_size=limit)
    attempts: list[dict[str, Any]] = []
    for row in payload.get("rows") or []:
        doi = str(row.get("doi") or "")
        if not doi:
            continue
        try:
            resolved = resolve_doi(doi, max_file_bytes=max_file_bytes)
            attempts.append(resolved)
            if resolved.get("files"):
                return {
                    "query": query,
                    "created": created,
                    "search_total": payload.get("total"),
                    "picked": resolved,
                    "attempts": len(attempts),
                }
        except Exception as exc:
            attempts.append({"doi": doi, "error": str(exc)})
    return {
        "query": query,
        "created": created,
        "search_total": payload.get("total"),
        "picked": None,
        "attempts": attempts,
        "error": "no DataCite hit with downloadable repository files under size cap",
    }


def build_http_manifest_plan(
    resolved: dict[str, Any],
    *,
    file_index: int = 0,
    destination: str = "",
) -> dict[str, Any]:
    files = resolved.get("files") or []
    if not files:
        raise ValueError(f"no downloadable files for DOI {resolved.get('doi')}")
    if file_index < 0 or file_index >= len(files):
        raise IndexError(f"file_index {file_index} out of range (0..{len(files) - 1})")
    chosen = files[file_index]
    doi = str(resolved.get("doi") or "")
    landing = str(resolved.get("landing_url") or "")
    slug = doi.replace("/", "_")
    if not destination:
        destination = f"data_lake/procured/{repository_slug(str(resolved.get('repository') or ''), landing, doi)}"
    return {
        "title": str(resolved.get("title") or f"DataCite {doi}"),
        "job_type": "http_manifest",
        "connector_id": f"datacite_{slug}",
        "url": landing,
        "items": [{"url": chosen["url"], "filename": chosen["key"]}],
        "destination": destination,
        "launchable": True,
        "timeout_seconds": 900,
        "datacite_doi": doi,
        "datacite_repository": resolved.get("repository"),
        "datacite_file": chosen.get("key"),
        "datacite_landing_url": landing,
        "datacite_checksum": chosen.get("checksum") or "",
    }
