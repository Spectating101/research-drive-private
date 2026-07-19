#!/usr/bin/env python3
"""Web discovery for Composer procurement — Tavily, DataCite, catalogs, DuckDuckGo."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path
from typing import Any, Callable


_ACADEMIC_PORTAL_RE = re.compile(r"\b(zenodo|figshare|dryad|osf|github|kaggle|huggingface)\b", re.I)
_DATASET_NOISE_RE = re.compile(r"\b(dataset|datasets|data|open|download|portal)\b", re.I)


def _datacite_query(query: str) -> str:
    """Strip repository branding so DataCite full-text search returns DOI hits."""
    q = _ACADEMIC_PORTAL_RE.sub(" ", query or "")
    q = _DATASET_NOISE_RE.sub(" ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q or (query or "").strip()


def _normalize_hit(title: str, url: str, source: str, snippet: str = "") -> dict[str, Any]:
    return {
        "title": (title or url)[:240],
        "url": url,
        "source": source,
        "snippet": (snippet or "")[:500],
    }


def _optiplex_root(repo_root: Path) -> Path | None:
    candidate = repo_root.parent
    if (candidate / "src" / "utils" / "tavily_balancer.py").exists():
        return candidate
    alt = repo_root.parent / "Molina-Optiplex"
    return alt if alt.exists() else None


def _search_datacite(query: str, max_results: int) -> list[dict[str, Any]]:
    from scripts.research_data_mcp import datacite_client

    payload = datacite_client.search(query=_datacite_query(query), page_size=max_results)
    rows: list[dict[str, Any]] = []
    for row in payload.get("rows") or []:
        doi = str(row.get("doi") or "").strip()
        url = str(row.get("url") or "").strip()
        if not url and doi:
            url = f"https://doi.org/{doi}"
        if not url:
            continue
        rows.append(_normalize_hit(str(row.get("title") or doi), url, "datacite", str(row.get("publisher") or "")))
    return rows


def _search_zenodo_api(query: str, max_results: int) -> list[dict[str, Any]]:
    from scripts.research_data_mcp.academic_discovery import search_zenodo

    return search_zenodo(query, max_results=max_results)


def _search_openalex_api(query: str, max_results: int) -> list[dict[str, Any]]:
    from scripts.research_data_mcp.academic_discovery import search_openalex_datasets

    return search_openalex_datasets(query, max_results=max_results)


def _search_tavily(repo_root: Path, query: str, max_results: int, *, live: bool = False) -> list[dict[str, Any]]:
    optiplex = _optiplex_root(repo_root)
    if not optiplex:
        return []
    root = str(optiplex)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from src.utils.tavily_balancer import TavilyBalancer
    except Exception:
        return []

    if live:
        os.environ["TAVILY_LIVE_ENABLED"] = "1"

    balancer = TavilyBalancer()

    async def _run() -> list[dict[str, Any]]:
        hits = await balancer.search(query, search_depth="basic", max_results=max_results)
        rows: list[dict[str, Any]] = []
        for hit in hits or []:
            url = str(hit.get("url") or "").strip()
            if not url:
                continue
            rows.append(
                _normalize_hit(
                    str(hit.get("title") or url),
                    url,
                    "tavily",
                    str(hit.get("content") or hit.get("snippet") or ""),
                )
            )
        return rows

    try:
        rows = asyncio.run(_run())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            rows = loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception:
        return []
    if rows:
        try:
            from scripts.research_data_mcp.desk_activity import record_activity
            from scripts.research_data_mcp.desk_usage import record_tavily_call

            record_tavily_call(repo_root=repo_root)
            record_activity(
                "discover",
                query[:200],
                repo_root=repo_root,
                tavily_calls=1,
            )
        except Exception:
            pass
    return rows


def _search_duckduckgo_html(query: str, max_results: int) -> list[dict[str, Any]]:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; SharpeProcurement/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    patterns = [
        re.compile(r'uddg=([^&"]+)', re.I),
        re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S),
        re.compile(r'<a[^>]+class="[^"]*result-link[^"]*"[^>]+href="([^"]+)"', re.I),
    ]
    for pattern in patterns:
        for match in pattern.finditer(html):
            href = match.group(1)
            if "uddg=" in href or href.startswith("/l/?"):
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = (parsed.get("uddg") or [href])[0]
            href = urllib.parse.unquote(href)
            if href.startswith("//"):
                href = "https:" + href
            if not href.startswith("http"):
                continue
            title = href
            if match.lastindex and match.lastindex >= 2:
                title = re.sub(r"<[^>]+>", "", match.group(2))
                title = unescape(title).strip() or href
            rows.append(_normalize_hit(title, href, "duckduckgo"))
            if len(rows) >= max_results:
                return rows
        if rows:
            return rows
    return rows


def _search_duckduckgo_instant(query: str, max_results: int) -> list[dict[str, Any]]:
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "no_redirect": "1", "no_html": "1", "skip_disambig": "1"}
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    abstract = str(payload.get("AbstractURL") or "").strip()
    if abstract.startswith("http"):
        rows.append(_normalize_hit(str(payload.get("Heading") or abstract), abstract, "duckduckgo_instant", str(payload.get("Abstract") or "")))

    def walk(topics: list[Any]) -> None:
        for topic in topics:
            if len(rows) >= max_results:
                return
            if not isinstance(topic, dict):
                continue
            if "Topics" in topic:
                walk(topic.get("Topics") or [])
                continue
            first = str(topic.get("FirstURL") or "").strip()
            if first.startswith("http"):
                rows.append(_normalize_hit(str(topic.get("Text") or first)[:120], first, "duckduckgo_instant"))

    walk(payload.get("RelatedTopics") or [])
    return rows[:max_results]


def discover_sources(
    repo_root: Path,
    query: str,
    *,
    max_results: int = 5,
    tavily_live: bool = False,
    extra_queries: list[str] | None = None,
) -> dict[str, Any]:
    queries = [query.strip()]
    for item in extra_queries or []:
        item = str(item).strip()
        if item and item not in queries:
            queries.append(item)

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources_tried: list[str] = []

    def _merge(hits: list[dict[str, Any]]) -> None:
        for hit in hits:
            url = hit.get("url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(hit)

    providers: list[tuple[str, Callable[[str], list[dict[str, Any]]]]] = [
        ("datacite", lambda q: _search_datacite(q, max_results)),
        ("zenodo_api", lambda q: _search_zenodo_api(q, max_results)),
        ("openalex", lambda q: _search_openalex_api(q, max_results)),
        ("tavily", lambda q: _search_tavily(repo_root, q, max_results, live=tavily_live)),
        ("duckduckgo_html", _search_duckduckgo_html),
        ("duckduckgo_instant", _search_duckduckgo_instant),
    ]

    for q in queries:
        for source, fn in providers:
            key = f"{source}"
            if key not in sources_tried:
                sources_tried.append(key)
            try:
                _merge(fn(q))
            except Exception:
                pass
            if len(merged) >= max_results:
                break
        if len(merged) >= max_results:
            break

    if not merged:
        fallback_q = _datacite_query(query)
        if fallback_q and fallback_q != query.strip():
            try:
                _merge(_search_datacite(fallback_q, max_results))
            except Exception:
                pass

    return {"query": query, "queries_tried": queries, "results": merged[:max_results], "sources_tried": sources_tried}


def discover_with_catalog(
    gateway: Any,
    message: str,
    *,
    search_queries: list[str] | None = None,
    max_results: int = 8,
    tavily_live: bool = False,
    skip_cache: bool = False,
) -> dict[str, Any]:
    from scripts.research_data_mcp.magic_config import load_magic_config
    from scripts.research_data_mcp.procurement_cache import ProcurementCache, catalog_fingerprint, goal_key

    cache_cfg = load_magic_config(gateway.repo_root).get("cache") or {}
    if not skip_cache:
        cache = ProcurementCache(gateway.repo_root)
        fp = catalog_fingerprint(gateway.repo_root, gateway.registry_path)
        cache_key = f"{goal_key(message)}:{int(tavily_live)}:{max_results}"
        hit = cache.get(
            "discovery",
            cache_key,
            fingerprint=fp,
            ttl_hours=float(cache_cfg.get("discovery_ttl_hours", 72)),
        )
        if hit:
            out = dict(hit)
            out["from_cache"] = True
            return out

    queries = [message.strip()]
    for q in search_queries or []:
        q = str(q).strip()
        if q and q not in queries:
            queries.append(q)

    catalog_rows: list[dict[str, Any]] = []
    for q in queries[:5]:
        try:
            payload = gateway.search_catalog(q=q, limit=max(5, max_results))
            catalog_rows.extend(payload.get("rows") or [])
        except Exception:
            pass

    source_rows: list[dict[str, Any]] = []
    try:
        source_rows = (gateway.plan_sources(message, limit=max_results).get("rows") or [])
    except Exception:
        pass
    for q in queries[1:3]:
        try:
            source_rows.extend(gateway.plan_sources(q, limit=5).get("rows") or [])
        except Exception:
            pass

    web = discover_sources(
        gateway.repo_root,
        message,
        max_results=max_results,
        tavily_live=tavily_live,
        extra_queries=queries[1:],
    )

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(row: dict[str, Any], source: str) -> None:
        url = str(row.get("url") or "").strip()
        if not url.startswith("http") or url in seen:
            return
        seen.add(url)
        merged.append(
            _normalize_hit(
                str(row.get("title") or row.get("name") or row.get("dataset_id") or url),
                url,
                source,
                str(row.get("snippet") or row.get("rationale") or row.get("access_recommendation") or ""),
            )
        )

    for row in catalog_rows:
        _add(row, "external_catalog")
    for row in source_rows:
        _add(row, "source_plan")
    for row in web.get("results") or []:
        url = row.get("url") or ""
        if url and url not in seen:
            seen.add(url)
            merged.append(row)

    result = {
        "query": message,
        "search_queries": queries,
        "catalog_hits": catalog_rows[:max_results],
        "source_plan_hits": source_rows[:max_results],
        "web": web,
        "results": merged[:max_results],
        "sources_tried": list(dict.fromkeys(["external_catalog", "source_plan", *(web.get("sources_tried") or [])])),
        "enabled": True,
    }
    if not skip_cache:
        cache.set(
            "discovery",
            cache_key,
            result,
            fingerprint=fp,
            ttl_hours=float(cache_cfg.get("discovery_ttl_hours", 72)),
        )
    return result
