#!/usr/bin/env python3
"""DataCite-first prefetch — primary catalog for our harvested vault + curated indexes."""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")
DOI_PREFIX_RE = re.compile(r"^doi:\s*", re.I)

DEFAULT_PREFETCH_BUDGET_SECONDS = float(os.environ.get("DESK_DATACITE_PREFETCH_BUDGET", "6"))


def prefetch_budget_seconds() -> float:
    from scripts.research_data_mcp.desk_scale import search_budget_multiplier

    return max(1.0, DEFAULT_PREFETCH_BUDGET_SECONDS * search_budget_multiplier())


def warm_search_indexes(repo_root: Path) -> dict[str, Any]:
    """Prepare NVMe indexes before serving traffic (replaces background-only warmup)."""
    from scripts.research_data_mcp.desk_runtime import prepare_desk_indexes

    return prepare_desk_indexes(Path(repo_root).resolve())

CURATED_SPECS = (
    ("curated_live", "curated_live"),
    ("curated", "curated"),
    ("curated_strict", "curated_strict"),
)


def _tokens(query: str) -> list[str]:
    return list(dict.fromkeys(TOKEN_RE.findall(query.lower())))


def _score_blob(tokens: list[str], *parts: str) -> float:
    if not tokens:
        return 0.0
    words: set[str] = set()
    for part in parts:
        words |= set(TOKEN_RE.findall(str(part).lower()))
    if not words:
        return 0.0
    score = sum(1.0 for tok in tokens if tok in words)
    if any(tok in words for tok in tokens if len(tok) >= 5):
        score += 0.35
    return score


def _normalize_doi(raw: str) -> str:
    text = DOI_PREFIX_RE.sub("", str(raw or "").strip())
    return text.removeprefix("https://doi.org/").strip()


@lru_cache(maxsize=4)
def _load_locator_dois(repo_root_s: str) -> frozenset[str]:
    path = Path(repo_root_s) / "data_lake/collection/_index/catalog/locators.json"
    if not path.is_file():
        return frozenset()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    dois: set[str] = set()
    for row in doc.get("locators") or []:
        doi = _normalize_doi(str(row.get("doi") or ""))
        if doi:
            dois.add(doi.lower())
    return frozenset(dois)


def vault_summary(repo_root: Path) -> dict[str, Any]:
    """Inventory line for chat — committed DataCite records in our vault."""
    repo_root = Path(repo_root).resolve()
    for rel in (
        "data_lake/collection/_index/chat_desk.json",
        "data_lake/collection/_index/collection_dictionary.json",
    ):
        path = repo_root / rel
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        inv = doc.get("inventory_summary") or doc.get("summary") or {}
        committed = inv.get("datacite_records_committed")
        if committed:
            return {
                "datacite_records_committed": int(committed),
                "registry_on_disk": inv.get("registry_on_disk"),
                "source": rel,
            }
    return {"datacite_records_committed": 0, "source": "unknown"}


def _datacite_candidate(
    *,
    doi: str,
    title: str,
    url: str = "",
    source: str,
    score: float,
    vault_backed: bool = True,
    in_locator: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean = _normalize_doi(doi)
    badges = ["datacite_vault" if vault_backed else "datacite_doi"]
    labels = ["DataCite vault" if vault_backed else "DataCite DOI"]
    if in_locator:
        badges.append("vault_locator")
        labels.append("Pinned in collection")
    item: dict[str, Any] = {
        "kind": "datacite",
        "doi": clean,
        "title": title or clean,
        "url": url or (f"https://doi.org/{clean}" if clean else ""),
        "source": source,
        "open_handle": f"doi:{clean}" if clean else "",
        "vault_backed": vault_backed,
        "in_vault_locator": in_locator,
        "score": round(score, 2),
        "procureability": {
            "badges": badges,
            "badge_labels": labels,
            "status": "downloadable",
            "can_collect": True,
        },
    }
    if extra:
        item.update(extra)
    return item


def search_curated_datasets(repo_root: Path, query: str, *, limit: int = 6, max_lines_per_file: int = 4000) -> list[dict[str, Any]]:
    """Token scan of curated_dataset_index.jsonl — our promoted DataCite-facing catalog."""
    tokens = _tokens(query)
    if not tokens:
        return []

    root = Path(repo_root).resolve() / "data_lake/dataset_catalog"
    hits: list[tuple[float, dict[str, Any]]] = []
    seen: set[str] = set()

    for subdir, source_tag in CURATED_SPECS:
        jsonl = root / subdir / "curated_dataset_index.jsonl"
        if not jsonl.is_file():
            continue
        try:
            line_count = 0
            with jsonl.open(encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line_count += 1
                    if line_count > max_lines_per_file:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    title = str(row.get("title") or "")
                    desc = str(row.get("description") or "")[:800]
                    domain = str(row.get("domain") or "")
                    dataset_id = str(row.get("dataset_id") or "")
                    url = str(row.get("url") or "")
                    tags = " ".join(str(t) for t in (row.get("tags") or []))
                    proc = row.get("procurement") or {}
                    goal = str(proc.get("search_goal") or "")
                    doi = _normalize_doi(dataset_id if dataset_id.lower().startswith("doi:") else row.get("doi") or "")
                    if not doi and "doi.org/" in url:
                        doi = _normalize_doi(url.split("doi.org/", 1)[-1])
                    blob_id = doi or dataset_id
                    if blob_id.lower() in seen:
                        continue
                    sc = _score_blob(tokens, title, desc, domain, dataset_id, doi, tags, goal)
                    if str(row.get("promotion_tier") or "").startswith("tier_3"):
                        sc += 0.75
                    if str(row.get("promotion_tier") or "").startswith("tier_4"):
                        sc += 1.25
                    if proc.get("search_goal"):
                        sc += min(2.0, _score_blob(tokens, goal) * 0.6)
                    if sc < 1.5:
                        continue
                    seen.add(blob_id.lower())
                    hits.append(
                        (
                            sc + (0.5 if subdir == "curated_live" else 0.0),
                            _datacite_candidate(
                                doi=doi or dataset_id,
                                title=title,
                                url=url,
                                source=source_tag,
                                score=sc + 2.5,
                                vault_backed=True,
                                extra={
                                    "domain": domain,
                                    "curated_tier": row.get("promotion_tier"),
                                    "analysis_readiness": row.get("analysis_readiness"),
                                },
                            ),
                        )
                    )
                    if len(hits) >= limit * 8:
                        break
        except OSError:
            continue
        if len(hits) >= limit * 4:
            break

    hits.sort(key=lambda x: (-x[0], x[1].get("doi", "")))
    return [row for _, row in hits[:limit]]


def search_datacite_api(
    query: str,
    *,
    limit: int = 8,
    locator_dois: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """DataCite REST search — index into our committed vault corpus."""
    from scripts.research_data_mcp import datacite_client
    from scripts.research_data_mcp.procurement_search import datacite_supplement_queries

    locator_dois = locator_dois or frozenset()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dc_query in datacite_supplement_queries(query):
        try:
            payload = datacite_client.search(dc_query, page_size=limit, timeout=12)
        except Exception:
            continue
        for i, row in enumerate(payload.get("rows") or []):
            doi = _normalize_doi(str(row.get("doi") or ""))
            if not doi or doi.lower() in seen:
                continue
            seen.add(doi.lower())
            in_loc = doi.lower() in locator_dois
            rows.append(
                _datacite_candidate(
                    doi=doi,
                    title=str(row.get("title") or doi),
                    url=str(row.get("url") or ""),
                    source="datacite_api",
                    score=4.0 - i * 0.15 + (0.4 if in_loc else 0.0),
                    vault_backed=True,
                    in_locator=in_loc,
                    extra={
                        "publisher": row.get("publisher"),
                        "publication_year": row.get("publication_year"),
                        "subjects": row.get("subjects"),
                    },
                )
            )
    return rows[:limit]


def _merge_datacite_rows(*groups: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for row in group:
            key = _normalize_doi(str(row.get("doi") or "")).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(row)
            if len(merged) >= limit:
                return merged
    return merged


def prefetch_datacite_layer(
    repo_root: Path,
    query: str,
    *,
    limit: int = 10,
    budget_seconds: float | None = None,
    deep_vault: bool = False,
) -> list[dict[str, Any]]:
    """Interactive prefetch — NVMe curated FTS + DataCite API. USB shards only when deep_vault=True."""
    repo_root = Path(repo_root).resolve()
    budget = budget_seconds if budget_seconds is not None else prefetch_budget_seconds()
    deadline = time.monotonic() + max(0.5, budget)
    locator_dois = _load_locator_dois(str(repo_root))

    from scripts.research_data_mcp.datacite_vault_search import (
        search_curated_fts,
        search_scrape_snippets_fts,
    )

    fast_rows = _merge_datacite_rows(
        search_curated_fts(repo_root, query, limit=min(8, limit)),
        search_curated_datasets(repo_root, query, limit=min(6, limit)),
        limit=limit,
    )
    if len(fast_rows) >= limit:
        return fast_rows

    api_limit = max(4, limit - len(fast_rows))
    pool = ThreadPoolExecutor(max_workers=2)
    futures: dict[Any, str] = {
        pool.submit(search_datacite_api, query, limit=api_limit, locator_dois=locator_dois): "datacite_api",
        pool.submit(search_scrape_snippets_fts, repo_root, query, limit=min(6, limit)): "scrape_fts",
    }
    if deep_vault:
        from scripts.research_data_mcp.datacite_vault_search import search_vault_topics_deep

        futures[
            pool.submit(
                search_vault_topics_deep,
                repo_root,
                query,
                limit=limit,
                deadline=deadline,
                interactive=False,
            )
        ] = "vault_shards"
    try:
        while futures and len(fast_rows) < limit:
            rem = deadline - time.monotonic()
            if rem <= 0:
                break
            try:
                for fut in as_completed(futures, timeout=rem):
                    futures.pop(fut)
                    try:
                        rows = fut.result()
                        if rows:
                            fast_rows = _merge_datacite_rows(fast_rows, rows, limit=limit)
                    except Exception:
                        pass
                    if len(fast_rows) >= limit or not futures:
                        break
            except TimeoutError:
                break
    finally:
        pool.shutdown(wait=False, cancel_futures=bool(futures))

    if fast_rows:
        return fast_rows[:limit]
    return search_curated_datasets(repo_root, query, limit=limit)[:limit]
