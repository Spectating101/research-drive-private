#!/usr/bin/env python3
"""Academic dataset discovery — Zenodo + OpenAlex APIs (no browser)."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

_PORTAL_NOISE_RE = re.compile(r"\b(zenodo|figshare|dryad|dataset|datasets|open|data)\b", re.I)


def _clean_query(query: str) -> str:
    q = _PORTAL_NOISE_RE.sub(" ", query or "")
    return re.sub(r"\s+", " ", q).strip() or (query or "").strip()


def _normalize(title: str, url: str, source: str, snippet: str = "") -> dict[str, Any]:
    return {
        "title": (title or url)[:240],
        "url": url,
        "source": source,
        "snippet": (snippet or "")[:500],
    }


def search_zenodo(query: str, *, max_results: int = 5, timeout: float = 20.0) -> list[dict[str, Any]]:
    """Zenodo REST search — returns record pages (works on SPAs without Playwright)."""
    q = _clean_query(query)
    if not q:
        return []
    params = urllib.parse.urlencode({"q": q, "size": max(1, min(max_results, 25)), "sort": "bestmatch"})
    url = f"https://zenodo.org/api/records?{params}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for hit in payload.get("hits", {}).get("hits") or []:
        meta = hit.get("metadata") or {}
        rec_id = str(hit.get("id") or "")
        if not rec_id:
            continue
        record_url = f"https://zenodo.org/records/{rec_id}"
        doi = str(meta.get("doi") or hit.get("doi") or "").strip()
        title = str(meta.get("title") or record_url)
        desc = str(meta.get("description") or "")[:300]
        row = _normalize(title, record_url, "zenodo_api", desc)
        if doi:
            row["doi"] = doi
            row["doi_url"] = f"https://doi.org/{doi}"
        out.append(row)
        if len(out) >= max_results:
            break
    return out


def search_openalex_datasets(query: str, *, max_results: int = 5, timeout: float = 20.0) -> list[dict[str, Any]]:
    """OpenAlex works tagged as dataset-like (free, no API key)."""
    q = _clean_query(query)
    if not q:
        return []
    params = urllib.parse.urlencode(
        {
            "search": q,
            "filter": "type:dataset",
            "per_page": max(1, min(max_results, 25)),
        }
    )
    url = f"https://api.openalex.org/works?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "YZU-ResearchDesk/1.0 (mailto:research@yzu.edu.tw)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for hit in payload.get("results") or []:
        title = str(hit.get("display_name") or hit.get("title") or "")
        landing = str(hit.get("id") or "")
        doi = str(hit.get("doi") or "").replace("https://doi.org/", "")
        oa = hit.get("open_access") or {}
        open_url = str(oa.get("oa_url") or "")
        if not open_url and hit.get("primary_location"):
            open_url = str((hit.get("primary_location") or {}).get("landing_page_url") or "")
        page_url = open_url or (f"https://doi.org/{doi}" if doi else landing)
        if not page_url.startswith("http"):
            continue
        row = _normalize(title, page_url, "openalex", str(hit.get("publication_year") or ""))
        if doi:
            row["doi"] = doi
        out.append(row)
        if len(out) >= max_results:
            break
    return out


def resolve_zenodo_record(url: str, *, timeout: float = 15.0) -> dict[str, Any] | None:
    """Fetch Zenodo record metadata — DOI + downloadable files without Playwright."""
    m = re.search(r"zenodo\.org/records/(\d+)", url, re.I)
    if not m:
        return None
    rec_id = m.group(1)
    api = f"https://zenodo.org/api/records/{rec_id}"
    try:
        with urllib.request.urlopen(api, timeout=timeout) as resp:
            hit = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    meta = hit.get("metadata") or {}
    doi = str(meta.get("doi") or hit.get("doi") or "").strip()
    files: list[dict[str, str]] = []
    for f in hit.get("files") or []:
        link = str(f.get("links", {}).get("self") or f.get("link") or "")
        name = str(f.get("key") or f.get("filename") or "file")
        if link.startswith("http"):
            files.append({"url": link, "filename": name})
    return {
        "record_id": rec_id,
        "url": f"https://zenodo.org/records/{rec_id}",
        "doi": doi,
        "title": str(meta.get("title") or ""),
        "files": files[:12],
    }
