#!/usr/bin/env python3
"""Topic search over local DataCite catalogs — curated FTS + optional shard indexes."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from scripts.data_catalog.topic_index_paths import shard_index_candidates, topic_index_root

TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")

DEFAULT_MAX_SHARD_SCANS = int(os.environ.get("DESK_DATACITE_MAX_SHARD_SCANS", "4"))


def max_shard_scans() -> int:
    return max(0, DEFAULT_MAX_SHARD_SCANS)


def _tokens(query: str) -> list[str]:
    return list(dict.fromkeys(TOKEN_RE.findall(query.lower())))


def _fts_query(tokens: list[str]) -> str:
    if not tokens:
        return ""
    parts = []
    for tok in tokens[:12]:
        safe = tok.replace('"', "")
        parts.append(f'"{safe}"' if len(safe) > 4 else safe)
    return " OR ".join(parts)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=1.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=500")
        conn.execute("PRAGMA query_only=ON")
    except sqlite3.Error:
        pass
    return conn


def _candidate_from_row(row: dict[str, Any], *, score: float, source: str) -> dict[str, Any]:
    from scripts.research_data_mcp.datacite_prefetch import _datacite_candidate

    doi = str(row.get("doi") or "").strip()
    if doi.lower().startswith("doi:"):
        doi = doi[4:]
    title = str(row.get("title") or doi or row.get("dataset_id") or "")
    url = str(row.get("url") or (f"https://doi.org/{doi}" if doi.startswith("10.") else ""))
    return _datacite_candidate(
        doi=doi or str(row.get("dataset_id") or ""),
        title=title,
        url=url,
        source=source,
        score=score,
        vault_backed=True,
        in_locator=bool(row.get("local_path")),
        extra={
            "domain": row.get("domain"),
            "tags": row.get("tags"),
            "promotion_tier": row.get("promotion_tier"),
            "local_path": row.get("local_path"),
            "procurement": row.get("procurement"),
        },
    )


def shard_index_dir(repo_root: Path) -> Path:
    return topic_index_root(repo_root) / "shards"


_PREPARED_CURATED_INDEX: Path | None = None


def set_prepared_curated_index(path: Path) -> None:
    global _PREPARED_CURATED_INDEX
    _PREPARED_CURATED_INDEX = Path(path).resolve()


def search_curated_fts(repo_root: Path, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """FTS over curated_live + curated + curated_strict JSONL promotions."""
    query = query.strip()
    if not query:
        return []
    global _PREPARED_CURATED_INDEX
    if _PREPARED_CURATED_INDEX and _PREPARED_CURATED_INDEX.is_file():
        path = _PREPARED_CURATED_INDEX
    else:
        try:
            from scripts.data_catalog.build_curated_topic_fts import ensure_curated_topic_fts

            path = ensure_curated_topic_fts(repo_root)
        except Exception:
            return []

    tokens = _tokens(query)
    fts_q = _fts_query(tokens)
    if not fts_q:
        return []

    conn = _connect(path)
    try:
        rows = conn.execute(
            """SELECT doi, dataset_id, source_dir, title, body, payload_json, bm25(curated_fts) AS rank
               FROM curated_fts WHERE curated_fts MATCH ? ORDER BY rank LIMIT ?""",
            (fts_q, max(limit * 3, 12)),
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []
    conn.close()

    hits: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {"title": row["title"], "doi": row["doi"]}
        rank = float(row["rank"] or 0.0)
        score = round(5.5 - abs(rank) * 0.08, 2)
        token_bonus = sum(0.4 for t in tokens if t in str(row["title"]).lower() or t in str(row["body"]).lower())
        score = round(score + token_bonus, 2)
        if str(payload.get("promotion_tier") or "").startswith("tier_4"):
            score += 0.8
        cand = _candidate_from_row(payload, score=score, source=f"curated_fts:{row['source_dir']}")
        hits.append(cand)

    hits.sort(key=lambda h: float(h.get("score") or 0), reverse=True)
    return hits[:limit]


def search_full_index_fts(repo_root: Path, query: str, *, limit: int = 6) -> list[dict[str, Any]]:
    """Search optional full_index topic sqlite if built."""
    path = Path(repo_root).resolve() / "data_lake/dataset_catalog/_topic_index/full_index.sqlite3"
    return _search_single_vault_fts(path, query, limit=limit, source="vault_full_index")


def _search_single_vault_fts(
    path: Path,
    query: str,
    *,
    limit: int,
    source: str,
    shard: str = "",
) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    tokens = _tokens(query)
    fts_q = _fts_query(tokens)
    if not fts_q:
        return []
    conn = _connect(path)
    try:
        rows = conn.execute(
            """SELECT doi, title, body, payload_json, bm25(vault_fts) AS rank
               FROM vault_fts WHERE vault_fts MATCH ? ORDER BY rank LIMIT ?""",
            (fts_q, max(limit * 2, 8)),
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []
    conn.close()
    hits: list[dict[str, Any]] = []
    src = f"{source}:{shard}" if shard else source
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {"doi": row["doi"], "title": row["title"]}
        if not payload.get("doi") and row["doi"]:
            payload["doi"] = str(row["doi"])
        rank = float(row["rank"] or 0.0)
        score = round(4.8 - abs(rank) * 0.06, 2)
        if shard:
            score += 0.15
        token_bonus = sum(0.35 for t in tokens if t in str(row["title"]).lower() or t in str(row["body"]).lower())
        score = round(score + token_bonus, 2)
        hits.append(_candidate_from_row(payload, score=score, source=src))
    hits.sort(key=lambda h: float(h.get("score") or 0), reverse=True)
    return hits[:limit]


def list_shard_indexes(repo_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_shards: set[str] = set()
    for shard_dir in shard_index_candidates(repo_root):
        manifest = shard_dir / "INDEX.json"
        if manifest.is_file():
            try:
                doc = json.loads(manifest.read_text(encoding="utf-8"))
                for s in doc.get("shards") or []:
                    shard = str(s.get("shard") or "")
                    if not shard or shard in seen_shards:
                        continue
                    if (shard_dir / f"{shard}.sqlite3").is_file():
                        seen_shards.add(shard)
                        entries.append(s)
                continue
            except (OSError, json.JSONDecodeError):
                pass
        for path in sorted(shard_dir.glob("*.sqlite3")):
            if not path.is_file():
                continue
            shard = path.stem
            if shard in seen_shards:
                continue
            seen_shards.add(shard)
            entries.append({"shard": shard, "index_path": str(path)})
    return entries


def search_shard_indexes(
    repo_root: Path,
    query: str,
    *,
    limit: int = 10,
    max_shards: int = 0,
    deadline: float | None = None,
    interactive: bool = True,
) -> list[dict[str, Any]]:
    """Search per-shard vault FTS indexes — bounded for interactive search."""
    repo_root = Path(repo_root).resolve()
    shard_dirs = shard_index_candidates(repo_root, interactive=interactive)
    if not shard_dirs:
        return []
    merged: list[dict[str, Any]] = []
    per_shard = max(2, limit // 2)
    shard_cap = max_shards if max_shards > 0 else max_shard_scans()
    if shard_cap <= 0:
        shard_cap = 9999
    scanned = 0
    for entry in list_shard_indexes(repo_root):
        if deadline is not None and time.monotonic() >= deadline:
            break
        if scanned >= shard_cap:
            break
        shard = str(entry.get("shard") or "")
        if not shard:
            continue
        path = None
        for shard_dir in shard_dirs:
            candidate = shard_dir / f"{shard}.sqlite3"
            if candidate.is_file():
                path = candidate
                break
        if path is None:
            continue
        scanned += 1
        merged.extend(_search_single_vault_fts(path, query, limit=per_shard, source="vault_shard", shard=shard))
        if len(merged) >= limit * 2:
            break
    merged.sort(key=lambda h: float(h.get("score") or 0), reverse=True)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in merged:
        key = str(row.get("doi") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def vault_index_stats(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    root = topic_index_root(repo_root)
    repo_root_nvme = repo_root / "data_lake/dataset_catalog/_topic_index"
    curated = repo_root_nvme / "curated.sqlite3"
    full = repo_root_nvme / "full_index.sqlite3"
    if not curated.is_file():
        curated = root / "curated.sqlite3"
    if not full.is_file():
        full = root / "full_index.sqlite3"
    stats: dict[str, Any] = {
        "curated_index": curated.is_file(),
        "full_index": full.is_file(),
        "shard_index_root": str(root / "shards"),
        "shard_indexes": 0,
        "total_indexed_rows": 0,
        "shards": [],
    }
    for entry in list_shard_indexes(repo_root):
        stats["shards"].append(entry)
    stats["shard_indexes"] = len(stats["shards"])
    stats["total_indexed_rows"] = sum(int(s.get("row_count") or 0) for s in stats["shards"])
    for shard_dir in shard_index_candidates(repo_root):
        manifest = shard_dir / "INDEX.json"
        if manifest.is_file():
            try:
                doc = json.loads(manifest.read_text(encoding="utf-8"))
                if int(doc.get("total_rows") or 0) > stats["total_indexed_rows"]:
                    stats["total_indexed_rows"] = int(doc.get("total_rows") or 0)
                    stats["shard_indexes"] = int(doc.get("shard_count") or stats["shard_indexes"])
            except (OSError, json.JSONDecodeError):
                pass
    return stats


def search_scrape_snippets_fts(repo_root: Path, query: str, *, limit: int = 6) -> list[dict[str, Any]]:
    from scripts.data_catalog.build_scrape_snippet_fts import snippet_index_path

    path = snippet_index_path(repo_root)
    return _search_single_vault_fts(path, query, limit=limit, source="scrape_snippet")


def search_vault_topics_fast(repo_root: Path, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """NVMe-fast vault layers only — curated FTS + scrape snippets."""
    repo_root = Path(repo_root).resolve()
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fn in (search_curated_fts, search_scrape_snippets_fts):
        try:
            rows = fn(repo_root, query, limit=limit)
        except Exception:
            rows = []
        for row in rows:
            key = str(row.get("doi") or row.get("title") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(row)
            if len(merged) >= limit:
                return merged
    return merged


def search_vault_topics_deep(
    repo_root: Path,
    query: str,
    *,
    limit: int = 10,
    deadline: float | None = None,
    max_shards: int = 0,
    interactive: bool = False,
) -> list[dict[str, Any]]:
    """Bulk/USB vault layers — bounded shard scans + optional full index."""
    repo_root = Path(repo_root).resolve()
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    def absorb(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            key = str(row.get("doi") or row.get("title") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(row)

    absorb(
        search_shard_indexes(
            repo_root,
            query,
            limit=limit,
            max_shards=max_shards,
            deadline=deadline,
            interactive=interactive,
        )
    )
    if len(merged) < limit and (deadline is None or time.monotonic() < deadline):
        try:
            absorb(search_full_index_fts(repo_root, query, limit=limit))
        except Exception:
            pass
    merged.sort(key=lambda h: float(h.get("score") or 0), reverse=True)
    return merged[:limit]


def search_vault_topics(
    repo_root: Path,
    query: str,
    *,
    limit: int = 10,
    budget_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """Curated FTS → scrape → shard FTS → full_index FTS → linear curated scan."""
    repo_root = Path(repo_root).resolve()
    deadline = None if budget_seconds is None else time.monotonic() + max(0.25, budget_seconds)
    merged = search_vault_topics_fast(repo_root, query, limit=limit)
    if len(merged) >= limit:
        return merged
    if deadline is not None and time.monotonic() >= deadline:
        return merged
    merged.extend(
        search_vault_topics_deep(
            repo_root,
            query,
            limit=max(0, limit - len(merged)),
            deadline=deadline,
        )
    )
    if merged:
        return _dedupe_vault_rows(merged, limit=limit)

    from scripts.research_data_mcp.datacite_prefetch import search_curated_datasets

    return search_curated_datasets(repo_root, query, limit=limit)


def _dedupe_vault_rows(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("doi") or row.get("title") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _search_vault_topics_legacy(repo_root: Path, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Full sequential scan — batch/offline callers only."""
    repo_root = Path(repo_root).resolve()
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for fn in (search_curated_fts, search_scrape_snippets_fts, search_shard_indexes, search_full_index_fts):
        try:
            rows = fn(repo_root, query, limit=limit)
        except Exception:
            rows = []
        for row in rows:
            key = str(row.get("doi") or row.get("title") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(row)
            if len(merged) >= limit:
                return merged

    if merged:
        return merged

    from scripts.research_data_mcp.datacite_prefetch import search_curated_datasets

    return search_curated_datasets(repo_root, query, limit=limit)
