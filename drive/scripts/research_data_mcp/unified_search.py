#!/usr/bin/env python3
"""Unified dataset search — local registry, DataCite, catalog, Hugging Face."""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from scripts.research_data_mcp.credential_gate import classify_collect_gate
from scripts.research_data_mcp.doi_resolve_cache import resolve_doi_cached
from scripts.research_data_mcp.governance import classify_url
from scripts.research_data_mcp.procureability import (
    BADGE_DOWNLOADABLE,
    BADGE_METADATA_ONLY,
    BADGE_UNKNOWN_REPO,
    datacite_procureability,
    hf_reference_procureability,
    registry_procureability,
)

REPO_HINTS = (
    ("zenodo.org", "zenodo", BADGE_DOWNLOADABLE),
    ("osf.io", "osf", BADGE_DOWNLOADABLE),
    ("figshare.com", "figshare", BADGE_DOWNLOADABLE),
    ("datadryad.org", "dryad", BADGE_DOWNLOADABLE),
    ("github.com/releases", "github_release", BADGE_DOWNLOADABLE),
)

DEFAULT_SEARCH_BUDGET_SECONDS = float(os.environ.get("DESK_UNIFIED_SEARCH_BUDGET", "8"))


def search_budget_seconds() -> float:
    from scripts.research_data_mcp.desk_scale import search_budget_multiplier

    base = max(2.0, DEFAULT_SEARCH_BUDGET_SECONDS)
    return max(2.0, base * search_budget_multiplier())


def fast_datacite_procureability(row: dict[str, Any]) -> dict[str, Any]:
    url = str(row.get("url") or "").lower()
    for needle, repository, badge in REPO_HINTS:
        if needle in url:
            return {
                "badges": [badge, "pending_resolve"],
                "badge_labels": ["Likely downloadable", "Resolving…"],
                "tone": "blue",
                "status": "pending_resolve",
                "can_collect": None,
                "reason": "",
                "repository_hint": repository,
            }
    return {
        "badges": [BADGE_UNKNOWN_REPO, BADGE_METADATA_ONLY],
        "badge_labels": ["Unknown repository", "Metadata only"],
        "tone": "amber",
        "status": "metadata_only",
        "can_collect": False,
        "reason": "repository not recognized from metadata URL",
    }


def enrich_datacite_row(
    repo_root: Any,
    row: dict[str, Any],
    *,
    max_file_bytes: int = 50_000_000,
) -> dict[str, Any]:
    doi = str(row.get("doi") or "")
    if not doi:
        return row
    try:
        resolved = resolve_doi_cached(repo_root, doi, max_file_bytes=max_file_bytes)
        url = str(resolved.get("landing_url") or row.get("url") or "")
        gate = classify_collect_gate(
            url=url,
            license_text=str((resolved.get("metadata") or {}).get("license") or row.get("license") or ""),
            governance_class=classify_url(url, name=str(row.get("title") or "")),
            repository=str(resolved.get("repository") or ""),
            doi=doi,
            repo_root=repo_root,
        )
        proc = datacite_procureability(resolved)
        if gate.get("needs_approval") and not gate.get("allowed"):
            proc["can_collect"] = False
            proc["badges"] = list(proc.get("badges") or []) + ["needs_approval"]
            proc["reason"] = gate.get("blocked_reason") or proc.get("reason")
        elif gate.get("needs_approval") and gate.get("allowed"):
            proc["can_collect"] = True
            proc["reason"] = "license approved"
        if not gate.get("allowed") and gate.get("blocked_reason"):
            proc["can_collect"] = False
            proc["reason"] = gate.get("blocked_reason")
        item = dict(row)
        item["procureability"] = proc
        item["resolved"] = {
            "repository": resolved.get("repository"),
            "files": resolved.get("files") or [],
            "all_files": resolved.get("all_files") or [],
            "cache_hit": resolved.get("cache_hit"),
        }
        return item
    except Exception as exc:
        item = dict(row)
        item["procureability"] = {
            "badges": ["Unavailable"],
            "badge_labels": ["Unavailable"],
            "tone": "red",
            "status": "error",
            "can_collect": False,
            "reason": str(exc),
        }
        return item


def enrich_datacite_rows(
    repo_root: Any,
    rows: list[dict[str, Any]],
    *,
    max_file_bytes: int = 50_000_000,
    max_workers: int = 4,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    out: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(enrich_datacite_row, repo_root, row, max_file_bytes=max_file_bytes): row
            for row in rows
        }
        for fut in as_completed(futures):
            out.append(fut.result())
    order = {str(r.get("doi")): i for i, r in enumerate(rows)}
    out.sort(key=lambda item: order.get(str(item.get("doi")), 999))
    return out


def _collect_layer(
    layer_id: str,
    fn: Callable[[], tuple[list[dict[str, Any]], dict[str, Any] | None]],
) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None, str | None]:
    try:
        rows, section = fn()
        return layer_id, rows, section, None
    except Exception as exc:  # noqa: BLE001
        return layer_id, [], None, str(exc)


def _build_datacite_layer(
    repo_root: Any,
    q: str,
    *,
    limit: int,
    resolve_datacite: bool,
    max_file_bytes: int,
    budget_seconds: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    from scripts.research_data_mcp.datacite_prefetch import prefetch_datacite_layer

    dc_rows: list[dict[str, Any]] = []
    for row in prefetch_datacite_layer(repo_root, q, limit=limit, budget_seconds=budget_seconds):
        doi = str(row.get("doi") or "")
        proc = fast_datacite_procureability(row) if not resolve_datacite else None
        dc_rows.append(
            {
                "kind": "datacite",
                "id": doi,
                "doi": doi,
                "title": row.get("title") or doi,
                "source": row.get("source") or "datacite_vault",
                "publication_year": row.get("publication_year"),
                "publisher": row.get("publisher"),
                "url": row.get("url"),
                "license": row.get("license"),
                "vault_backed": row.get("vault_backed"),
                "local_path": row.get("local_path"),
                "tags": row.get("tags"),
                "score": row.get("score"),
                "procureability": proc,
                "resolved": None,
                "open_handle": f"doi:{doi}" if doi else "",
            }
        )
    if resolve_datacite and dc_rows:
        dc_rows = enrich_datacite_rows(repo_root, dc_rows, max_file_bytes=max_file_bytes)
    section = (
        {
            "id": "datacite_vault",
            "label": "DataCite vault & curated",
            "count": len(dc_rows),
            "rows": dc_rows,
        }
        if dc_rows
        else None
    )
    return dc_rows, section


def _build_hf_layer(q: str, *, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    from scripts.research_data_mcp import hf_catalog

    hf = hf_catalog.search_datasets(q, limit=min(limit, 8), timeout=8)
    hf_rows: list[dict[str, Any]] = []
    for row in hf.get("rows") or []:
        hf_rows.append(
            {
                "kind": "huggingface",
                "id": row.get("id"),
                "title": row.get("title"),
                "source": "huggingface",
                "url": row.get("url"),
                "load_hint": row.get("load_hint"),
                "tags": row.get("tags"),
                "procureability": hf_reference_procureability(row),
                "open_handle": f"hf:{row.get('id')}",
            }
        )
    section = (
        {
            "id": "huggingface",
            "label": "Hugging Face",
            "count": len(hf_rows),
            "rows": hf_rows,
        }
        if hf_rows
        else None
    )
    return hf_rows, section


def _build_scrape_layer(repo_root: Any, q: str, *, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    from scripts.research_data_mcp.datacite_vault_search import search_scrape_snippets_fts

    scrape_rows: list[dict[str, Any]] = []
    for hit in search_scrape_snippets_fts(repo_root, q, limit=min(limit, 8)):
        scrape_rows.append(
            {
                "kind": "web_scrape",
                "id": hit.get("dataset_id") or hit.get("doi"),
                "title": hit.get("title"),
                "source": hit.get("source") or "scrape_snippet",
                "url": hit.get("url"),
                "tags": hit.get("tags"),
                "score": hit.get("score"),
                "vault_backed": False,
                "procureability": {"status": "scraped", "can_collect": True},
            }
        )
    section = (
        {
            "id": "scrape_snippets",
            "label": "Web scrape index",
            "count": len(scrape_rows),
            "rows": scrape_rows,
        }
        if scrape_rows
        else None
    )
    return scrape_rows, section


def _run_remote_layers(
    *,
    repo_root: Any,
    q: str,
    limit: int,
    include_hf: bool,
    include_datacite: bool,
    resolve_datacite: bool,
    max_file_bytes: int,
    budget_seconds: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    """Run slow search layers in parallel with a wall-clock budget."""
    jobs: list[tuple[str, Callable[[], tuple[list[dict[str, Any]], dict[str, Any] | None]]]] = []
    if include_datacite:
        jobs.append(
            (
                "datacite",
                lambda b=budget_seconds: _build_datacite_layer(
                    repo_root,
                    q,
                    limit=limit,
                    resolve_datacite=resolve_datacite,
                    max_file_bytes=max_file_bytes,
                    budget_seconds=b,
                ),
            )
        )
    if include_hf:
        jobs.append(("huggingface", lambda: _build_hf_layer(q, limit=limit)))
    jobs.append(("scrape_snippets", lambda: _build_scrape_layer(repo_root, q, limit=limit)))

    merged: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    timed_out: list[str] = []
    errors: list[str] = []
    if not jobs:
        return merged, sections, timed_out, errors

    deadline = time.monotonic() + budget_seconds
    pool = ThreadPoolExecutor(max_workers=min(3, len(jobs)))
    try:
        future_map = {pool.submit(_collect_layer, layer_id, fn): layer_id for layer_id, fn in jobs}
        pending = set(future_map)
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out.extend(sorted(future_map[fut] for fut in pending))
                for fut in pending:
                    fut.cancel()
                break
            try:
                for fut in as_completed(pending, timeout=remaining):
                    pending.remove(fut)
                    layer_id, rows, section, err = fut.result()
                    if err:
                        errors.append(f"{layer_id}: {err}")
                    if rows:
                        merged.extend(rows)
                    if section:
                        sections.append(section)
                    if not pending:
                        break
            except TimeoutError:
                timed_out.extend(sorted(future_map[fut] for fut in pending))
                for fut in pending:
                    fut.cancel()
                break
    finally:
        pool.shutdown(wait=not timed_out, cancel_futures=bool(timed_out))

    return merged, sections, timed_out, errors


def unified_search(
    gateway: Any,
    query: str,
    *,
    limit: int = 12,
    include_hf: bool = True,
    include_datacite: bool = True,
    resolve_datacite: bool = False,
    max_file_bytes: int = 50_000_000,
    budget_seconds: float | None = None,
) -> dict[str, Any]:
    q = query.strip()
    if not q:
        return {"query": q, "sections": [], "rows": [], "total": 0}

    repo_root = gateway.repo_root
    sections: list[dict[str, Any]] = []
    merged: list[dict[str, Any]] = []
    budget = budget_seconds if budget_seconds is not None else search_budget_seconds()
    started = time.monotonic()

    local = gateway.list_datasets(q=q, limit=limit)
    local_rows = []
    for row in local.get("datasets") or []:
        proc = registry_procureability(row)
        item = {
            "kind": "local_registry",
            "id": row.get("dataset_id"),
            "title": row.get("name") or row.get("dataset_id"),
            "source": "registry",
            "dataset_id": row.get("dataset_id"),
            "domain": row.get("domain"),
            "analysis_readiness": row.get("analysis_readiness"),
            "procureability": proc,
            "open_handle": f"dataset:{row.get('dataset_id')}",
        }
        local_rows.append(item)
        merged.append(item)
    if local_rows:
        sections.append({"id": "local_registry", "label": "Local library", "count": len(local_rows), "rows": local_rows})

    try:
        catalog = gateway.search_catalog(q=q, limit=limit)
        cat_rows = []
        for row in catalog.get("rows") or []:
            item = {
                "kind": "catalog",
                "id": row.get("dataset_id") or row.get("id"),
                "title": row.get("title") or row.get("name"),
                "source": row.get("source") or "catalog",
                "access_mode": row.get("access_mode"),
                "procureability": {
                    "badges": ["catalog"],
                    "status": "catalog",
                    "can_collect": bool(row.get("launchable")),
                },
            }
            cat_rows.append(item)
            merged.append(item)
        if cat_rows:
            sections.append({"id": "catalog", "label": "Source catalog", "count": len(cat_rows), "rows": cat_rows})
    except Exception:
        pass

    layer_budget = max(1.0, budget - (time.monotonic() - started))
    remote_rows, remote_sections, timed_out_layers, layer_errors = _run_remote_layers(
        repo_root=repo_root,
        q=q,
        limit=limit,
        include_hf=include_hf,
        include_datacite=include_datacite,
        resolve_datacite=resolve_datacite,
        max_file_bytes=max_file_bytes,
        budget_seconds=layer_budget,
    )
    merged.extend(remote_rows)
    sections.extend(remote_sections)

    top_score = 0.0
    for row in merged:
        if row.get("kind") == "local_registry":
            continue
        top_score = max(top_score, float(row.get("score") or 0))
    local_count = sum(1 for r in merged if r.get("kind") == "local_registry")
    index_miss = top_score < 2.0 and local_count == 0

    vault_stats: dict[str, Any] = {}
    try:
        from scripts.research_data_mcp.datacite_vault_search import vault_index_stats

        vault_stats = vault_index_stats(repo_root)
    except Exception:
        vault_stats = {}

    elapsed = round(time.monotonic() - started, 3)
    return {
        "query": q,
        "sections": sections,
        "rows": merged,
        "total": len(merged),
        "resolve_mode": "full" if resolve_datacite else "fast",
        "index_miss": index_miss,
        "weak_match": index_miss,
        "vault_stats": vault_stats,
        "search_budget_seconds": budget,
        "search_elapsed_seconds": elapsed,
        "timed_out_layers": timed_out_layers,
        "layer_errors": layer_errors,
        "search_layers": [
            "curated FTS",
            "vault shard FTS (bulk USB when indexed)",
            "full_index FTS",
            "DataCite API",
            "web scrape (Spectator) on acquire miss",
        ],
    }
