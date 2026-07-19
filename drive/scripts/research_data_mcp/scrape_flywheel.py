#!/usr/bin/env python3
"""Post-scrape flywheel — snippet index + optional http_manifest follow-up."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")
SNIPPET_JSONL = "data_lake/dataset_catalog/scrape_snippets/scrape_index.jsonl"
MAX_FOLLOW_DOWNLOADS = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def snippet_jsonl_path(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / SNIPPET_JSONL


def _goal_tags(goal: str) -> list[str]:
    return list(dict.fromkeys(TOKEN_RE.findall(goal.lower())))[:16]


def row_from_extract(
    *,
    job_id: str,
    plan: dict[str, Any],
    extract: dict[str, Any],
    registry_row: dict[str, Any] | None = None,
    search_goal: str = "",
) -> dict[str, Any]:
    url = str(extract.get("url") or plan.get("url") or "")
    title = str(extract.get("title") or plan.get("title") or f"Web scrape {job_id[:8]}")[:500]
    dataset_id = str((registry_row or {}).get("dataset_id") or f"scrape_{job_id}")
    text = str(extract.get("text_sample") or "")
    meta = str(extract.get("meta_description") or "")
    headings = extract.get("headings") or {}
    h1 = " ".join(headings.get("h1") or [])[:300]
    links = extract.get("dataset_links") or extract.get("links") or []
    link_text = " ".join(str(x.get("text") or "") for x in links[:40] if isinstance(x, dict))
    tags = _goal_tags(search_goal)
    tags.extend(TOKEN_RE.findall(f"{title} {h1} {meta}".lower())[:12])
    tags = list(dict.fromkeys(t for t in tags if t))[:24]
    host = urlparse(url).netloc if url else ""

    return {
        "indexed_at": _now(),
        "kind": "web_scrape_snippet",
        "dataset_id": dataset_id,
        "job_id": job_id,
        "url": url,
        "title": title,
        "host": host,
        "engine": extract.get("engine"),
        "description": (meta or h1 or text[:500])[:2000],
        "text_sample": text[:8000],
        "dataset_link_count": len(extract.get("dataset_links") or []),
        "link_count": len(extract.get("links") or []),
        "tags": tags,
        "search_goal": search_goal[:500],
        "local_path": str(
            (registry_row or {}).get("local_path")
            or f"data_lake/spectator_engine/scrapes/{job_id}/extract.json"
        ),
        "source": "scrape_flywheel",
    }


def append_snippet_row(repo_root: Path, row: dict[str, Any]) -> bool:
    path = snippet_jsonl_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    job_id = str(row.get("job_id") or "")
    url = str(row.get("url") or "")
    key = f"{job_id}:{url}"
    existing_lines: list[str] = []
    replaced = False
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                existing_lines.append(line)
                continue
            existing_key = f"{existing.get('job_id')}:{existing.get('url')}"
            if existing_key == key or (job_id and str(existing.get("job_id") or "") == job_id):
                if not replaced:
                    existing_lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
                    replaced = True
                continue
            existing_lines.append(line)
    if replaced:
        path.write_text("\n".join(existing_lines) + ("\n" if existing_lines else ""), encoding="utf-8")
        return True
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if f"{existing.get('job_id')}:{existing.get('url')}" == key:
                return False
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return True


def load_extract(repo_root: Path, job: dict[str, Any], registry_row: dict[str, Any] | None = None) -> dict[str, Any] | None:
    plan = job.get("plan") or {}
    rel = str((registry_row or {}).get("local_path") or "")
    if not rel:
        result = job.get("result") or {}
        materialized = result.get("materialized") or {}
        rel = str(materialized.get("local_path") or "")
    if not rel:
        rel = f"data_lake/spectator_engine/scrapes/{job.get('id')}/extract.json"
    path = Path(repo_root).resolve() / rel
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def promote_scrape_job(
    repo_root: Path,
    job: dict[str, Any],
    *,
    registry_row: dict[str, Any] | None = None,
    search_goal: str = "",
    rebuild_fts: bool = True,
    follow_downloads: bool = True,
) -> dict[str, Any]:
    """Index scrape extract for search; optionally queue http_manifest for dataset_links."""
    repo_root = Path(repo_root).resolve()
    if str((job.get("plan") or {}).get("job_type") or "") != "scraper_run":
        return {"skipped": True, "reason": "not scraper_run"}
    extract = load_extract(repo_root, job, registry_row)
    if not extract:
        return {"skipped": True, "reason": "no extract.json"}

    job_id = str(job.get("id") or "")
    row = row_from_extract(
        job_id=job_id,
        plan=job.get("plan") or {},
        extract=extract,
        registry_row=registry_row,
        search_goal=search_goal,
    )
    added = append_snippet_row(repo_root, row)
    fts_stats = None
    if rebuild_fts and added:
        try:
            from scripts.data_catalog.build_scrape_snippet_fts import build_scrape_snippet_fts

            fts_stats = build_scrape_snippet_fts(repo_root)
        except Exception:
            fts_stats = None

    follow_jobs: list[dict[str, Any]] = []
    if follow_downloads:
        follow_jobs = plan_follow_up_downloads(repo_root, job, extract, search_goal=search_goal)

    return {
        "snippet_indexed": added,
        "fts": fts_stats,
        "follow_up_jobs": follow_jobs,
        "dataset_links": len(extract.get("dataset_links") or []),
    }


def plan_follow_up_downloads(
    repo_root: Path,
    job: dict[str, Any],
    extract: dict[str, Any],
    *,
    search_goal: str = "",
    limit: int = MAX_FOLLOW_DOWNLOADS,
) -> list[dict[str, Any]]:
    """Build http_manifest plans for direct file URLs found in a scrape."""
    from scripts.research_data_mcp.scrape_plan import build_http_manifest_plan_for_url, classify_url

    plans: list[dict[str, Any]] = []
    seen: set[str] = set()
    candidates = list(extract.get("dataset_links") or [])
    if not candidates and str(extract.get("mode") or "") != "datasets":
        for link in extract.get("links") or []:
            if not isinstance(link, dict):
                continue
            href = str(link.get("href") or "")
            if classify_url(href) == "direct_http":
                candidates.append(link)

    for link in candidates:
        if len(plans) >= limit:
            break
        if not isinstance(link, dict):
            continue
        href = str(link.get("href") or "").strip()
        if not href.startswith("http") or href in seen:
            continue
        if classify_url(href) != "direct_http":
            continue
        seen.add(href)
        try:
            plan = build_http_manifest_plan_for_url(href, title=str(link.get("text") or href)[:120])
        except Exception:
            continue
        if not plan.get("launchable"):
            continue
        plan["parent_scrape_job_id"] = str(job.get("id") or "")
        plan["search_goal"] = search_goal[:500]
        plan["flywheel_follow_up"] = True
        plans.append(plan)
    return plans


def submit_follow_up_downloads(gateway: Any, job: dict[str, Any], plans: list[dict[str, Any]]) -> list[str]:
    """Submit http_manifest jobs discovered from scrape (auto-approved when configured)."""
    from scripts.research_data_mcp.magic_config import load_magic_config

    if not plans:
        return []
    cfg = load_magic_config(gateway.repo_root).get("flywheel") or {}
    if cfg.get("auto_follow_scrape_downloads") is False:
        return []

    job_ids: list[str] = []
    campaign_id = str((job.get("request") or {}).get("campaign_id") or "")
    for plan in plans:
        try:
            submitted = gateway.jobs.submit(
                str(plan.get("title") or "Follow-up download"),
                plan,
                {
                    "parent_job_id": job.get("id"),
                    "campaign_id": campaign_id,
                    "search_goal": plan.get("search_goal") or "",
                },
                auto_approve=bool(cfg.get("auto_approve_scrape_downloads", True)),
            )
            if submitted and submitted.get("id"):
                job_ids.append(str(submitted["id"]))
        except Exception:
            continue
    return job_ids
