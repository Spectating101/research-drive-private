#!/usr/bin/env python3
"""Multi-step sourcing chain — harvest scrape links, plan follow-up actions."""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse

from scripts.research_data_mcp.probe_url_selection import url_goal_score
from scripts.research_data_mcp.scrape_plan import classify_url

ZENODO_RECORD_RE = re.compile(r"https?://zenodo\.org/records/(\d+)", re.I)
DOI_URL_RE = re.compile(r"https?://(?:dx\.)?doi\.org/(10\.\S+)", re.I)
DOI_INLINE_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>]+)", re.I)
FILE_EXT_RE = re.compile(r"\.(csv|tsv|json|jsonl|zip|gz|parquet|xlsx?|xml|pdf|dat)(\?|$)", re.I)
JUNK_LINK_RE = re.compile(
    r"(privacy|cookie|login|signin|signup|terms-of|/developer|rate threshold|javascript:void|"
    r"accessibility\.|/about$|/about\?|help\.|moda\.gov\.tw/Applications|sitemap\.xml|libanswers\.com|"
    r"errors\.edgesuite|/content/state-|state-transportation-numbers)",
    re.I,
)
GOVT_DATASET_RE = re.compile(r"data\.gov\.tw/dataset/", re.I)


def _is_junk_href(href: str) -> bool:
    if JUNK_LINK_RE.search(href):
        return True
    try:
        parsed = urlparse(href)
    except ValueError:
        return True
    if parsed.netloc.endswith("data.gov.tw") and parsed.path in {"", "/"}:
        return True
    if "/about" in (parsed.path or "") or "#about" in href:
        return True
    return False


def harvest_links_from_extract(extract: dict[str, Any], *, limit: int = 40, goal: str = "") -> list[dict[str, Any]]:
    """Classify links from a Spectator extract.json for follow-up sourcing."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    links = list(extract.get("dataset_links") or []) + list(extract.get("links") or [])

    text_blob = " ".join(
        [
            str(extract.get("title") or ""),
            str(extract.get("meta_description") or ""),
            str(extract.get("text_sample") or "")[:4000],
        ]
    )
    for m in DOI_INLINE_RE.finditer(text_blob):
        doi = m.group(1).rstrip(".,;)")
        href = f"https://doi.org/{doi}"
        if href not in seen:
            seen.add(href)
            out.append({"href": href, "text": doi, "kind": "doi"})

    for row in links:
        if not isinstance(row, dict):
            continue
        href = str(row.get("href") or "").strip()
        if not href.startswith("http") or href in seen or _is_junk_href(href):
            continue
        seen.add(href)
        kind = "generic"
        if FILE_EXT_RE.search(href) or classify_url(href) == "direct_http":
            kind = "direct_file"
        elif ZENODO_RECORD_RE.search(href):
            kind = "zenodo_record"
        elif DOI_URL_RE.search(href):
            kind = "doi"
        elif "zenodo.org" in href and "/records/" in href:
            kind = "zenodo_record"
        elif GOVT_DATASET_RE.search(href):
            kind = "gov_dataset"
        out.append({"href": href, "text": str(row.get("text") or "")[:200], "kind": kind})
        if len(out) >= limit:
            break
    priority = {"direct_file": 0, "doi": 1, "zenodo_record": 2, "gov_dataset": 2, "generic": 3}
    kind_bonus = {"direct_file": 0.3, "doi": 0.25, "zenodo_record": 0.2, "gov_dataset": 0.15, "generic": 0.0}

    def sort_key(row: dict[str, Any]) -> tuple[float, int, str]:
        kind = str(row.get("kind") or "generic")
        goal_score = url_goal_score(goal, str(row.get("href") or ""), title=str(row.get("text") or "")) if goal else 0.0
        goal_score += kind_bonus.get(kind, 0.0)
        return (-goal_score, priority.get(kind, 9), str(row.get("href") or ""))

    out.sort(key=sort_key)
    return out


def doi_from_url(url: str) -> str:
    m = DOI_URL_RE.search(url)
    if m:
        return m.group(1).rstrip(".,;)")
    m = DOI_INLINE_RE.search(url)
    if m:
        return m.group(1).rstrip(".,;)")
    return ""


def plan_from_harvested_link(link: dict[str, Any], *, goal: str = "") -> dict[str, Any] | None:
    href = str(link.get("href") or "")
    kind = str(link.get("kind") or "")
    if kind == "direct_file":
        from scripts.research_data_mcp.scrape_plan import build_http_manifest_plan_for_url

        try:
            plan = build_http_manifest_plan_for_url(href, title=str(link.get("text") or href)[:120])
            if plan.get("launchable"):
                plan["search_goal"] = goal[:500]
                return plan
        except Exception:
            return None
    if kind == "doi":
        doi = doi_from_url(href)
        if doi:
            return {"action": "collect_doi", "doi": doi}
    if kind == "zenodo_record":
        from scripts.research_data_mcp.academic_discovery import resolve_zenodo_record

        meta = resolve_zenodo_record(href)
        if meta and meta.get("doi"):
            return {"action": "collect_doi", "doi": str(meta["doi"])}
        if meta and meta.get("files"):
            file_url = str(meta["files"][0].get("url") or "")
            if file_url.startswith("http"):
                from scripts.research_data_mcp.scrape_plan import build_http_manifest_plan_for_url

                plan = build_http_manifest_plan_for_url(
                    file_url,
                    title=str(meta.get("title") or file_url)[:120],
                )
                if plan.get("launchable"):
                    plan["search_goal"] = goal[:500]
                    return plan
        return {"action": "probe_url", "url": href}
    if href:
        return {"action": "probe_url", "url": href}
    return None


def follow_plans_from_extract(extract: dict[str, Any], *, goal: str = "", limit: int = 3) -> list[dict[str, Any]]:
    """Top-N follow-up plans from a scrape extract (parallel probe/collect candidates)."""
    plans: list[dict[str, Any]] = []
    seen_actions: set[str] = set()
    for link in harvest_links_from_extract(extract, goal=goal):
        plan = plan_from_harvested_link(link, goal=goal)
        if not plan:
            continue
        key = f"{plan.get('action')}:{plan.get('doi') or plan.get('url') or plan.get('job_type')}"
        if key in seen_actions:
            continue
        seen_actions.add(key)
        plans.append(plan)
        if len(plans) >= limit:
            break
    return plans


def sync_wait_job(gateway: Any, job_id: str, *, max_seconds: int = 120) -> dict[str, Any] | None:
    """Tick workers until job completes or timeout (chat sourcing chain)."""
    if not job_id:
        return None
    deadline = time.time() + max_seconds
    job: dict[str, Any] | None = None
    while time.time() < deadline:
        try:
            gateway.jobs.tick()
        except Exception:
            pass
        try:
            job = gateway.jobs.get(job_id)
        except Exception:
            return None
        status = str(job.get("status") or "")
        if status in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(2)
    return job


def load_extract_for_job(repo_root: Any, job: dict[str, Any]) -> dict[str, Any] | None:
    from pathlib import Path

    from scripts.research_data_mcp.scrape_flywheel import load_extract

    return load_extract(Path(repo_root), job)
