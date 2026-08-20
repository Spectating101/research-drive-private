#!/usr/bin/env python3
"""Web discovery for Composer procurement — Tavily, DataCite, catalogs, DuckDuckGo."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path
from typing import Any, Callable


_ACADEMIC_PORTAL_RE = re.compile(r"\b(zenodo|figshare|dryad|osf|github|kaggle|huggingface)\b", re.I)
_DATASET_NOISE_RE = re.compile(r"\b(dataset|datasets|data|open|download|portal)\b", re.I)
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-]{1,}", re.I)
# Meaningful geography / country codes retained as query terms (not generic filler).
_GEO_CODES = frozenset(
    {
        "us",
        "usa",
        "uk",
        "eu",
        "cn",
        "jp",
        "tw",
        "kr",
        "au",
        "ca",
        "nz",
        "de",
        "fr",
        "ie",
        "in",
        "br",
        "mx",
        "sg",
        "hk",
        "id",
        "vn",
        "ph",
        "my",
        "th",
    }
)
_GEO_ALIASES: dict[str, frozenset[str]] = {
    "us": frozenset({"us", "usa", "america", "american", "americans"}),
    "usa": frozenset({"us", "usa", "america", "american", "americans"}),
    "uk": frozenset({"uk", "britain", "british", "england", "english"}),
    "eu": frozenset({"eu", "europe", "european"}),
    "cn": frozenset({"cn", "china", "chinese"}),
    "jp": frozenset({"jp", "japan", "japanese"}),
    "tw": frozenset({"tw", "taiwan", "taiwanese"}),
    "kr": frozenset({"kr", "korea", "korean"}),
    "au": frozenset({"au", "australia", "australian"}),
    "ca": frozenset({"ca", "canada", "canadian"}),
    "ie": frozenset({"ie", "ireland", "irish"}),
    "in": frozenset({"in", "india", "indian"}),
    "br": frozenset({"br", "brazil", "brazilian"}),
    "mx": frozenset({"mx", "mexico", "mexican"}),
    "sg": frozenset({"sg", "singapore"}),
    "hk": frozenset({"hk", "hongkong"}),
    "id": frozenset({"id", "indonesia", "indonesian"}),
    "vn": frozenset({"vn", "vietnam", "vietnamese"}),
    "ph": frozenset({"ph", "philippines", "filipino"}),
    "my": frozenset({"my", "malaysia", "malaysian"}),
    "th": frozenset({"th", "thailand", "thai"}),
    "nz": frozenset({"nz", "zealand"}),
    "de": frozenset({"de", "germany", "german"}),
    "fr": frozenset({"fr", "france", "french"}),
}
_GEO_NAME_TOKENS = frozenset(a for aliases in _GEO_ALIASES.values() for a in aliases) | frozenset(
    {
        "america",
        "american",
        "britain",
        "british",
        "europe",
        "european",
        "china",
        "chinese",
        "japan",
        "japanese",
        "taiwan",
        "korea",
        "australia",
        "canada",
        "ireland",
        "irish",
        "india",
        "brazil",
        "mexico",
        "singapore",
        "indonesia",
        "vietnam",
        "philippines",
        "malaysia",
        "thailand",
        "germany",
        "france",
    }
)
_WEB_GENERIC_TOKENS = frozenset(
    {
        "dataset",
        "datasets",
        "data",
        "panel",
        "research",
        "study",
        "metadata",
        "graph",
        "source",
        "sources",
        "catalog",
        "catalogue",
        "public",
        "open",
        "download",
        "portal",
        "global",
        "world",
        "doi",
        "http",
        "https",
        "www",
        "org",
        "com",
        "html",
    }
)


def _web_tokens(text: str) -> set[str]:
    """Tokenize text; keep short country codes that are meaningful geography terms."""
    out: set[str] = set()
    for t in _TOKEN_RE.findall(text or ""):
        tl = t.lower()
        if len(tl) > 2 or tl in _GEO_CODES:
            out.add(tl)
    return out


def _web_distinctive_tokens(query: str) -> set[str]:
    return {
        t
        for t in _web_tokens(query)
        if t not in _WEB_GENERIC_TOKENS and (len(t) > 2 or t in _GEO_CODES)
    }


def web_query_aspects(query: str) -> dict[str, set[str]]:
    """Split distinctive query terms into geography vs topic aspects."""
    distinctive = _web_distinctive_tokens(query)
    geography: set[str] = set()
    topic: set[str] = set()
    for tok in distinctive:
        if tok in _GEO_CODES or tok in _GEO_NAME_TOKENS:
            geography |= set(_GEO_ALIASES.get(tok, {tok}))
            geography.add(tok)
        else:
            topic.add(tok)
    return {"geography": geography, "topic": topic}


def min_web_relevance(query: str) -> float:
    """Require enough distinct aspects that geo+topic queries need both."""
    aspects = web_query_aspects(query)
    n = int(bool(aspects.get("geography"))) + int(bool(aspects.get("topic")))
    if n >= 2:
        return 2.0
    if n == 1:
        return 1.0
    return 0.0


def _hit_blob(hit: dict[str, Any]) -> str:
    return " ".join(
        [
            str(hit.get("title") or ""),
            str(hit.get("snippet") or hit.get("description") or hit.get("content") or ""),
            str(hit.get("url") or ""),
            str(hit.get("source") or ""),
        ]
    ).lower()


def _token_matches_blob(tok: str, blob: str, blob_tokens: set[str]) -> bool:
    """Match distinctive tokens; short geo codes use whole-token match only."""
    if len(tok) <= 3 or tok in _GEO_CODES:
        aliases = _GEO_ALIASES.get(tok, {tok})
        return bool(aliases & blob_tokens) or tok in blob_tokens
    if tok in blob_tokens or tok in blob:
        return True
    if len(tok) >= 4 and any(
        tok.startswith(w) or w.startswith(tok) for w in blob_tokens if len(w) >= 4
    ):
        return True
    return False


def _aspect_covered(aspect_tokens: set[str], blob: str, blob_tokens: set[str]) -> bool:
    return any(_token_matches_blob(tok, blob, blob_tokens) for tok in aspect_tokens)


def web_hit_relevance(hit: dict[str, Any], query: str) -> float:
    """Deterministic title/snippet/url overlap on distinctive query aspects/tokens."""
    aspects = web_query_aspects(query)
    geography = aspects.get("geography") or set()
    topic = aspects.get("topic") or set()
    if not geography and not topic:
        return 0.0
    blob = _hit_blob(hit)
    blob_tokens = _web_tokens(blob)
    # Also expand hyphen/underscore parts for alias matching.
    for tok in list(blob_tokens):
        for part in re.split(r"[_\-]+", tok):
            if len(part) > 1:
                blob_tokens.add(part.lower())

    score = 0.0
    # Geography is one aspect (any alias match counts once).
    if geography:
        if _aspect_covered(geography, blob, blob_tokens):
            score += 1.0
        else:
            # Missing required geography aspect — reject (do not admit non-US for "US …").
            return 0.0
    # Topic tokens each contribute; require at least one when present.
    topic_hits = 0.0
    for tok in topic:
        if _token_matches_blob(tok, blob, blob_tokens):
            topic_hits += 1.0
            continue
        if len(tok) >= 4 and any(
            tok.startswith(w) or w.startswith(tok) for w in blob_tokens if len(w) >= 4
        ):
            topic_hits += 0.75
    if topic and topic_hits <= 0:
        return 0.0
    score += topic_hits
    return float(score)


def rank_web_results_by_relevance(
    results: list[dict[str, Any]],
    query: str,
    *,
    min_relevance: float | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Rerank external catalogue/web hits and drop weak relevance before presentation."""
    threshold = float(min_web_relevance(query) if min_relevance is None else min_relevance)
    scored: list[dict[str, Any]] = []
    for hit in results or []:
        if not isinstance(hit, dict):
            continue
        row = dict(hit)
        rel = web_hit_relevance(row, query)
        row["query_relevance"] = round(rel, 2)
        scored.append(row)
    scored.sort(
        key=lambda r: (
            -float(r.get("query_relevance") or 0),
            str(r.get("title") or ""),
            str(r.get("url") or ""),
        )
    )
    kept = [r for r in scored if float(r.get("query_relevance") or 0) >= threshold]
    if limit is not None:
        kept = kept[: max(0, int(limit))]
    return kept


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

    # MCP tool handlers may run inside an active AnyIO/asyncio loop.  Calling
    # asyncio.run (or run_until_complete on a second loop) from there both
    # fails and leaves the coroutine un-awaited.  Use a short-lived worker
    # thread in that case so live/disabled Tavily fallback remains callable
    # over stdio without leaking RuntimeWarnings.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            rows = asyncio.run(_run())
        except Exception:
            return []
    else:
        result: list[list[dict[str, Any]]] = []
        errors: list[BaseException] = []

        def _thread_run() -> None:
            try:
                result.append(asyncio.run(_run()))
            except BaseException as exc:  # pragma: no cover - provider/runtime dependent
                errors.append(exc)

        worker = threading.Thread(target=_thread_run, name="research-tavily-search", daemon=True)
        worker.start()
        worker.join(timeout=45)
        if worker.is_alive() or errors or not result:
            return []
        rows = result[0]
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
    from scripts.research_data_mcp.query_translation import catalogue_query_variants

    requested_queries: list[str] = []
    for item in [query, *(extra_queries or [])]:
        item = " ".join(str(item or "").split())
        if item and item.casefold() not in {seen.casefold() for seen in requested_queries}:
            requested_queries.append(item)
    if not requested_queries:
        return {
            "query": "",
            "queries_tried": [],
            "results": [],
            "sources_tried": [],
            "provider_attempts": [],
            "relevance": {"rule": "distinctive_aspect_overlap", "min_query_relevance": 0.0},
        }

    # Bound the candidate pool, but give every provider a chance to contribute.
    pool_limit = max(int(max_results) * 3, int(max_results), 12)
    per_provider = max(2, min(int(max_results), 4))
    threshold = min_web_relevance(query)
    providers: list[tuple[str, Callable[[str], list[dict[str, Any]]], bool]] = [
        ("datacite", lambda q: _search_datacite(q, per_provider), True),
        ("zenodo_api", lambda q: _search_zenodo_api(q, per_provider), True),
        ("openalex", lambda q: _search_openalex_api(q, per_provider), True),
        # General web engines already accept natural-language requests.  Do not
        # fan out translated variants here, especially when Tavily is metered.
        ("tavily", lambda q: _search_tavily(repo_root, q, per_provider, live=tavily_live), False),
        ("duckduckgo_html", lambda q: _search_duckduckgo_html(q, per_provider), False),
        ("duckduckgo_instant", lambda q: _search_duckduckgo_instant(q, per_provider), False),
    ]

    provider_buckets: list[list[dict[str, Any]]] = []
    provider_attempts: list[dict[str, Any]] = []
    attempted_queries: list[str] = []
    for source, fn, catalogue_style in providers:
        plan: list[str] = []
        for requested in requested_queries:
            variants = (
                catalogue_query_variants(requested, provider=source)
                if catalogue_style
                else [requested]
            )
            for variant in variants:
                if variant.casefold() not in {seen.casefold() for seen in plan}:
                    plan.append(variant)

        attempts: list[dict[str, Any]] = []
        selected: list[dict[str, Any]] = []
        query_used = ""
        for phrase in plan:
            attempted_queries.append(phrase)
            try:
                rows = fn(phrase)
            except Exception as exc:  # provider failure must not stop the rest of Discover
                attempts.append({"query": phrase, "returned": 0, "accepted": 0, "error": str(exc)[:160]})
                continue
            rows = [row for row in (rows or []) if isinstance(row, dict)]
            accepted = (
                rank_web_results_by_relevance(rows, query, min_relevance=threshold, limit=per_provider)
                if threshold > 0
                else rows[:per_provider]
            )
            attempts.append({"query": phrase, "returned": len(rows), "accepted": len(accepted)})
            if accepted:
                selected = accepted
                query_used = phrase
                break
        provider_buckets.append(selected)
        provider_attempts.append(
            {
                "source": source,
                "catalogue_style": catalogue_style,
                "queries_tried": plan,
                "query_used": query_used or None,
                "attempts": attempts,
                "returned": len(selected),
            }
        )

    # Round-robin provider buckets before the final cap: the first catalogue
    # must not hide results from every other source merely by returning quickly.
    merged: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    positions = [0] * len(provider_buckets)
    while len(merged) < pool_limit:
        progressed = False
        for index, bucket in enumerate(provider_buckets):
            while positions[index] < len(bucket):
                row = bucket[positions[index]]
                positions[index] += 1
                url = str(row.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                merged.append(row)
                progressed = True
                break
            if len(merged) >= pool_limit:
                break
        if not progressed:
            break

    # Collect a bounded multi-provider pool, then deterministically rerank/filter.
    pool = merged[:pool_limit]
    ranked = rank_web_results_by_relevance(
        pool,
        query,
        min_relevance=threshold,
        limit=max_results,
    )
    # Preserve browse-like behavior only when the query has no distinctive aspects.
    results = ranked if threshold > 0 else pool[:max_results]
    return {
        "query": query,
        "queries_tried": list(dict.fromkeys(attempted_queries)),
        "results": results,
        "sources_tried": [source for source, _fn, _catalogue_style in providers],
        "provider_attempts": provider_attempts,
        "relevance": {
            "rule": "distinctive_aspect_overlap",
            "min_query_relevance": threshold,
            "candidates_before_gate": len(pool),
            "candidates_after_gate": len(results),
            "aspects": {
                "geography": sorted(web_query_aspects(query).get("geography") or []),
                "topic": sorted(web_query_aspects(query).get("topic") or []),
            },
        },
    }


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
