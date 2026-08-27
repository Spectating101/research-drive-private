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
    from scripts.research_data_mcp.semantic_index import warm_embedding_model

    root = Path(repo_root).resolve()
    status = prepare_desk_indexes(root)
    status["embedding_model"] = warm_embedding_model()
    # The curated vector matrix lives on the bulk drive; paging it in costs
    # ~11s there and ~0.1s once resident. Never on a user's first search.
    try:
        from scripts.research_data_mcp.datacite_vault_search import search_curated_semantic

        search_curated_semantic(root, "warmup", limit=1, require_resident_model=False)
        status["semantic_vectors"] = True
    except Exception:
        status["semantic_vectors"] = False
    return status

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
                        "version_of": row.get("version_of") or [],
                    },
                )
            )
    return rows[:limit]


def _merge_datacite_rows(*groups: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Dedupe by DOI, then fold versions of one work onto the best-ranked member.

    Rows arrive ranked, so the kept row is the one that already ranked highest;
    the DOIs folded into it are listed on it rather than dropped.
    """
    merged: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for group in groups:
        for row in group:
            key = _normalize_doi(str(row.get("doi") or "")).lower()
            if not key:
                continue
            family = [str(d).lower() for d in (row.get("version_of") or []) if str(d).strip()]
            hit = seen.get(key)
            if hit is None:
                hit = next((seen[d] for d in family if d in seen), None)
            if hit is not None:
                kept = merged[hit]
                if key != _normalize_doi(str(kept.get("doi") or "")).lower():
                    siblings = kept.setdefault("version_siblings", [])
                    if key not in siblings:
                        siblings.append(key)
                continue
            index = len(merged)
            seen[key] = index
            for doi in family:
                seen.setdefault(doi, index)
            merged.append(row)
            if len(merged) >= limit:
                return merged
    return merged


def _held_reserve() -> int:
    raw = (os.environ.get("RESEARCH_HELD_RESERVE") or "").strip()
    try:
        return max(0, int(raw)) if raw else 3
    except ValueError:
        return 3


def _held_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for r in rows if r.get("dataset_id"))


def _has_dataset(rows: list[dict[str, Any]], dataset_id: str) -> bool:
    return any(str(r.get("dataset_id") or "") == str(dataset_id) for r in rows)


# Keyword rows already in hand rank first; semantic only ever fills what the
# authoritative layers left empty.
_LAYER_AUTHORITY = ("datacite_api", "scrape_fts", "vault_shards", "curated_semantic")


def semantic_fill_enabled() -> bool:
    return (os.environ.get("RESEARCH_SEMANTIC_FILL") or "1").strip().lower() not in {"0", "false", "off"}


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
    if len(fast_rows) >= limit and _held_count(fast_rows) >= _held_reserve():
        return fast_rows

    api_limit = max(4, limit - len(fast_rows))
    pool = ThreadPoolExecutor(max_workers=3)
    futures: dict[Any, str] = {
        pool.submit(search_datacite_api, query, limit=api_limit, locator_dois=locator_dois): "datacite_api",
        pool.submit(search_scrape_snippets_fts, repo_root, query, limit=min(6, limit)): "scrape_fts",
    }
    # Keyword recall is the binding constraint on this corpus, not ranking, so a
    # thin FTS pass is widened by meaning. Rows stay labelled match_type=semantic.
    if semantic_fill_enabled():
        from scripts.research_data_mcp.datacite_vault_search import search_curated_semantic

        futures[
            # Fetch wider than the reserve: only held rows are kept, and a held
            # dataset can rank below the top few by cosine. Scoring is ~0.06s warm.
            pool.submit(search_curated_semantic, repo_root, query, limit=max(limit, 16))
        ] = "curated_semantic"
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
    # Buffer per source, then merge in authority order. Merging in completion
    # order let whichever layer finished first fill `limit` and cancel the rest —
    # and semantic is the fastest layer once its matrix is resident, so the
    # supplementary layer would routinely displace keyword and API results.
    collected: dict[str, list[dict[str, Any]]] = {}
    try:
        while futures:
            rem = deadline - time.monotonic()
            if rem <= 0:
                break
            try:
                for fut in as_completed(futures, timeout=rem):
                    label = futures.pop(fut)
                    try:
                        collected[label] = list(fut.result() or [])
                    except Exception:
                        collected[label] = []
                    if not futures:
                        break
            except TimeoutError:
                break
    finally:
        pool.shutdown(wait=False, cancel_futures=bool(futures))

    authoritative = fast_rows
    for label in _LAYER_AUTHORITY:
        rows = collected.get(label)
        if not rows:
            continue
        if label == "curated_semantic":
            continue
        authoritative = _merge_datacite_rows(authoritative, rows, limit=limit)

    # Keyword layers index text, so they rank external DOI references highly and
    # routinely return nothing the desk actually holds. A held dataset can be
    # queried today; a reference has to be acquired first. Semantic rows that
    # resolve to held datasets therefore get a bounded reserve — they never
    # cancel or outrank the authoritative head, they occupy the tail.
    reserve = _held_reserve()
    held_new = [
        row
        for row in (collected.get("curated_semantic") or [])
        if row.get("dataset_id") and not _has_dataset(authoritative, row["dataset_id"])
    ][:reserve]
    if held_new:
        head = authoritative[: max(0, limit - len(held_new))]
        fast_rows = _merge_datacite_rows(head, held_new, limit=limit)
        fast_rows = _merge_datacite_rows(fast_rows, authoritative, limit=limit)
    else:
        fast_rows = authoritative

    # Held rows earn a reserve; the rest of the semantic pass is still ordinary
    # fill for space the authoritative layers genuinely left empty.
    if len(fast_rows) < limit:
        remaining = collected.get("curated_semantic") or []
        if remaining:
            fast_rows = _merge_datacite_rows(fast_rows, remaining, limit=limit)

    if fast_rows:
        return fast_rows[:limit]
    return search_curated_datasets(repo_root, query, limit=limit)[:limit]
