#!/usr/bin/env python3
"""Goal-conditioned probe URL ranking — discovery-first, catalog-gated."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from scripts.research_data_mcp.procurement_search import QUERY_STOPWORDS, TOKEN_RE

JUNK_PROBE_RE = re.compile(
    r"(sitemap\.xml|libanswers\.com|errors\.edgesuite|/content/state-|state-transportation-numbers|"
    r"javascript:void|moda\.gov\.tw/Applications|studies/study/\d{1,2}#)",
    re.I,
)

DISCOVERY_SOURCE_BOOST = {
    "domain_pack": 0.45,
    "datacite": 0.35,
    "zenodo": 0.3,
    "openalex": 0.25,
    "tavily": 0.2,
    "duckduckgo": 0.15,
}

GENERIC_MACRO_HOSTS = frozenset(
    {
        "fred.stlouisfed.org",
        "data.worldbank.org",
    }
)


def goal_tokens(goal: str) -> set[str]:
    return {t for t in TOKEN_RE.findall(str(goal or "").lower()) if t not in QUERY_STOPWORDS and len(t) > 2}


def _host_token_boost(goal: str, url: str) -> float:
    """Prefer URLs whose host contains goal tokens (e.g. skynet + skynet.certik.com)."""
    host = (urlparse(url).netloc or "").lower()
    if not host:
        return 0.0
    hits = sum(1 for token in goal_tokens(goal) if token in host)
    return min(0.6, hits * 0.25)


def is_junk_probe_url(url: str) -> bool:
    url = str(url or "").strip()
    if not url.startswith("http"):
        return True
    return bool(JUNK_PROBE_RE.search(url))


def url_goal_score(goal: str, url: str, *, title: str = "", snippet: str = "") -> float:
    qtok = goal_tokens(goal)
    blob = f"{url} {title} {snippet}".lower()
    if not qtok:
        return 0.0
    hits = sum(1.0 for token in qtok if token in blob)
    host = (urlparse(url).netloc or "").lower()
    penalty = 0.15 if host in GENERIC_MACRO_HOSTS and hits < 2 else 0.0
    return (hits / len(qtok)) - penalty


def rank_probe_urls(
    goal: str,
    *,
    discovery_results: list[dict[str, Any]] | None = None,
    catalog_rows: list[dict[str, Any]] | None = None,
    source_plan_rows: list[dict[str, Any]] | None = None,
    extra_urls: list[str] | None = None,
    planner_urls: list[str] | None = None,
    min_catalog_score: float = 0.08,
    limit: int = 10,
) -> list[str]:
    """Planner URLs first, then web discovery; catalog/source-plan only when goal-relevant."""
    scored: list[tuple[float, str]] = []
    seen: set[str] = set()

    def add(url: str, score: float) -> None:
        url = str(url).strip()
        if not url.startswith("http") or is_junk_probe_url(url):
            return
        if url in seen:
            for index, (old_score, old_url) in enumerate(scored):
                if old_url == url and score > old_score:
                    scored[index] = (score, url)
            return
        seen.add(url)
        scored.append((score, url))

    for hit in discovery_results or []:
        if not isinstance(hit, dict):
            continue
        src = str(hit.get("source") or "").lower()
        if src in {"source_plan", "external_catalog"}:
            continue
        url = str(hit.get("url") or "")
        boost = DISCOVERY_SOURCE_BOOST.get(src, 0.2)
        score = url_goal_score(
            goal,
            url,
            title=str(hit.get("title") or ""),
            snippet=str(hit.get("snippet") or ""),
        )
        add(url, score + boost + 0.35 + _host_token_boost(goal, url))

    for row in catalog_rows or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "")
        score = url_goal_score(goal, url, title=str(row.get("title") or row.get("dataset_id") or ""))
        if score < min_catalog_score:
            continue
        add(url, score + 0.1)

    for row in source_plan_rows or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "")
        score = url_goal_score(goal, url, title=str(row.get("title") or row.get("dataset_id") or ""))
        if score < min_catalog_score:
            continue
        add(url, score + 0.05)

    for url in extra_urls or []:
        score = url_goal_score(goal, url)
        add(url, score + 0.3)

    for index, url in enumerate(planner_urls or []):
        score = url_goal_score(goal, url) + 1.5 - (index * 0.02)
        add(url, score)

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [url for _, url in scored[:limit]]


def filter_probe_urls_for_goal(goal: str, urls: list[str], *, min_score: float = 0.03) -> list[str]:
    """Drop low-relevance URLs when ranked alternatives exist."""
    ranked = rank_probe_urls(goal, extra_urls=urls, limit=max(len(urls), 10))
    if not ranked:
        return []
    if len(ranked) <= 3:
        return ranked
    strong = [url for url in ranked if url_goal_score(goal, url) >= min_score]
    return strong or ranked[:3]
