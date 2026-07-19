#!/usr/bin/env python3
"""Fast collection search index for procurement chat — SQLite FTS5."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.collection_dictionary import (
    build_dictionary,
    dictionary_path,
    flatten_for_search_index,
)
from scripts.research_data_mcp.collection_catalog import (
    build_catalog,
    flatten_for_search_index as catalog_index_rows,
)
from scripts.research_data_mcp.collection_search_rank import filter_research_hits
from scripts.research_data_mcp.collection_resolve import load_partitions

TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")
INDEX_VERSION = 5


def index_path(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / "data_lake/collection/_index/search.sqlite3"


def chat_desk_path(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / "data_lake/collection/_index/chat_desk.json"


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
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def build_index(repo_root: Path, *, manifest_path: Path | None = None) -> dict[str, Any]:
    """Rebuild FTS index from collection_dictionary (single source of truth)."""
    repo_root = Path(repo_root).resolve()
    out = index_path(repo_root)
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = build_dictionary(repo_root)
    dict_out = dictionary_path(repo_root)
    dict_out.parent.mkdir(parents=True, exist_ok=True)
    dict_out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    catalog_stats = build_catalog(repo_root)

    items = flatten_for_search_index(doc)
    items.extend(catalog_index_rows(repo_root))
    cfg = load_partitions(repo_root)

    if out.is_file():
        out.unlink()

    conn = _connect(out)
    conn.execute(
        """CREATE VIRTUAL TABLE search_fts USING fts5(
            id UNINDEXED,
            kind UNINDEXED,
            domain UNINDEXED,
            title,
            body,
            chat_line UNINDEXED,
            action UNINDEXED,
            action_label UNINDEXED,
            partition_id UNINDEXED,
            partition_path UNINDEXED,
            handle UNINDEXED,
            score_boost UNINDEXED,
            payload_json UNINDEXED,
            tokenize='porter unicode61'
        )"""
    )
    for row in items:
        payload = dict(row.get("payload") or {})
        if row.get("availability"):
            payload.setdefault("availability", row["availability"])
        conn.execute(
            """INSERT INTO search_fts(
                id, kind, domain, title, body, chat_line, action, action_label,
                partition_id, partition_path, handle, score_boost, payload_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row["id"],
                row["kind"],
                row["domain"],
                row["title"],
                row["body"],
                row["chat_line"],
                row["action"],
                row["action_label"],
                row["partition_id"],
                row["partition_path"],
                row["handle"],
                float(row["score_boost"]),
                json.dumps(payload, default=str),
            ),
        )
    conn.commit()
    conn.close()

    summary = doc.get("summary") or {}
    desk = {
        "version": INDEX_VERSION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "item_count": len(items),
        "dictionary_path": str(dict_out.relative_to(repo_root)),
        "catalog_path": catalog_stats.get("index_path", "").replace(str(repo_root) + "/", ""),
        "index_path": str(out.relative_to(repo_root)),
        "domains": cfg.get("domains") or {},
        "inventory_summary": {
            "datacite_records_committed": summary.get("datacite_records_committed"),
            "datacite_local_jsonl_human": summary.get("datacite_local_jsonl_human"),
            "registry_on_disk": summary.get("registry_on_disk"),
            "registry_total": summary.get("registry_total"),
            "gap_count": summary.get("gap_count"),
            "catalog": catalog_stats.get("summary"),
        },
        "how_to_read_hits": [
            "Research questions: our registry + curated catalog + DataCite vault (170M+) first",
            "DataCite DOI hits are vault-backed catalog matches — collect #N or collect DOI",
            "Infra lanes (y2025_q2 shards) only appear for hydrate/ops queries",
            "query_now = bytes on disk — preview #N",
            "true miss = external browse and explicit YZU collection job",
        ],
        "sample_actions": {
            "query_now": "preview #1",
            "hydrate": "hydrate #1",
            "refresh": "refresh — then collect #N",
            "collect": "collect #1",
            "search_datacite": "collect DOI … or source this for me",
        },
    }
    chat_desk_path(repo_root).write_text(json.dumps(desk, indent=2), encoding="utf-8")

    return {
        "item_count": len(items),
        "index_path": str(out),
        "desk_path": str(chat_desk_path(repo_root)),
        "dictionary_path": str(dict_out),
        "catalog_path": catalog_stats.get("index_path"),
        "dictionary_summary": summary,
        "catalog_summary": catalog_stats.get("summary"),
    }


def index_is_stale(repo_root: Path) -> bool:
    path = index_path(repo_root)
    if not path.is_file():
        return True
    idx_mtime = path.stat().st_mtime
    for rel in (
        "config/collection_partitions.json",
        "config/research_query_registry.json",
        "config/data_collection_queue.json",
        "data_lake/collection/_index/manifest_latest.json",
        "scripts/data_catalog/datacite_y2025_parallel_shards.list",
        "data_lake/collection/_index/catalog/INDEX.json",
    ):
        p = Path(repo_root).resolve() / rel
        if p.is_file() and p.stat().st_mtime > idx_mtime:
            return True
    dict_p = dictionary_path(repo_root)
    if dict_p.is_file() and dict_p.stat().st_mtime > idx_mtime:
        return True
    # DataCite shard status files (complete/checkpoint) change independently
    v3 = Path(repo_root).resolve() / "data_lake/dataset_catalog/index_v3"
    if v3.is_dir():
        for status in v3.glob("**/datacite.complete.json"):
            if status.stat().st_mtime > idx_mtime:
                return True
    return False


def ensure_index(repo_root: Path) -> Path:
    path = index_path(repo_root)
    if index_is_stale(repo_root):
        build_index(repo_root)
    return path


def search_index(
    repo_root: Path,
    query: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """FTS search — returns chat-friendly hit dicts with score + availability."""
    query = query.strip()
    if not query:
        return []
    path = ensure_index(repo_root)
    tokens = _tokens(query)
    if not tokens:
        return []

    fts_q = _fts_query(tokens)
    conn = _connect(path)
    try:
        rows = conn.execute(
            """SELECT id, kind, domain, title, body, chat_line, action, action_label,
                      partition_id, partition_path, handle, score_boost, payload_json,
                      bm25(search_fts) AS rank
               FROM search_fts
               WHERE search_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (fts_q, max(limit * 4, 16)),
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []
    conn.close()

    hits: list[dict[str, Any]] = []
    for row in rows:
        boost = float(row["score_boost"] or 1.0)
        rank = float(row["rank"] or 0.0)
        score = round(boost + max(0.0, 1.5 - abs(rank) * 0.05), 2)
        token_bonus = sum(0.35 for t in tokens if t in str(row["title"]).lower() or t in str(row["body"]).lower())
        score = round(score + token_bonus, 2)
        payload = json.loads(row["payload_json"] or "{}")
        availability = payload.get("availability") or {}
        hits.append(
            {
                "id": row["id"],
                "kind": row["kind"],
                "domain": row["domain"],
                "title": row["title"],
                "chat_line": row["chat_line"],
                "action": row["action"],
                "action_label": row["action_label"],
                "partition_id": row["partition_id"],
                "partition_path": row["partition_path"],
                "handle": row["handle"],
                "score": score,
                "availability": availability,
                "missing": list(availability.get("missing") or []),
                "payload": payload,
            }
        )

    hits.sort(key=lambda h: float(h.get("score") or 0), reverse=True)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        key = str(hit.get("id") or hit.get("title"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)

    return filter_research_hits(deduped, query, limit=limit)


def hits_to_chat_context(hits: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Minimal structured list for LLM tool results."""
    out: list[dict[str, str]] = []
    for i, hit in enumerate(hits, 1):
        action = str(hit.get("action") or "")
        say = {
            "query_now": f"preview #{i}",
            "hydrate": f"hydrate partition {hit.get('partition_id') or i}",
            "refresh": f"refresh then collect #{i}",
            "collect": f"collect #{i}",
            "search_datacite": "source this for me",
        }.get(action, f"describe #{i}")
        missing = hit.get("missing") or []
        if missing and action in {"hydrate", "search_datacite", "collect"}:
            say = f"{say} (gap: {missing[0]})"
        out.append(
            {
                "n": str(i),
                "title": str(hit.get("title") or ""),
                "line": str(hit.get("chat_line") or ""),
                "action": action,
                "say": say,
                "missing": ",".join(str(m) for m in missing),
            }
        )
    return out


def hit_to_candidate(hit: dict[str, Any], index: int, *, score: float | None = None) -> dict[str, Any]:
    """Map index hit → procurement candidate card."""
    from scripts.research_data_mcp.candidate_card import procureability_label

    action = str(hit.get("action") or "")
    kind = str(hit.get("kind") or "")
    payload = hit.get("payload") or {}
    availability = hit.get("availability") or payload.get("availability") or {}

    via = "none"
    if action == "query_now":
        via = "local_open"
    elif action == "hydrate":
        via = "hydrate"
    elif action == "refresh":
        via = "queue"
    elif action == "collect":
        via = "queue" if kind == "queue_task" else "datacite"
    elif action == "search_datacite":
        via = "datacite"

    dataset_id = str(payload.get("dataset_id") or "")
    task_id = str(payload.get("task_id") or "")
    handle = str(hit.get("handle") or payload.get("handle") or "")
    if kind == "registry_dataset" and dataset_id and not handle:
        handle = f"dataset:{dataset_id}"
    elif kind == "partition":
        for rid in payload.get("registry_dataset_ids") or []:
            dataset_id = str(rid)
            handle = f"dataset:{dataset_id}"
            via = "local_open" if action == "query_now" else via
            break
    elif kind == "queue_task" and payload.get("task"):
        task_id = str(payload.get("task", {}).get("id") or task_id)

    swarm_shard = ""
    if kind == "datacite_swarm":
        swarm_shard = str((payload.get("swarm") or {}).get("shard") or "")

    local_ready = action == "query_now" or bool(availability.get("on_local") and availability.get("have"))

    card: dict[str, Any] = {
        "index": index,
        "kind": kind,
        "title": hit.get("title"),
        "dataset_id": dataset_id,
        "task_id": task_id,
        "handle": handle,
        "source": "collection_index",
        "collect_via": via,
        "action": action,
        "action_label": hit.get("action_label"),
        "chat_line": hit.get("chat_line"),
        "partition_id": hit.get("partition_id"),
        "partition_path": hit.get("partition_path"),
        "score": score if score is not None else hit.get("score"),
        "local_ready": local_ready,
        "refresh_only": action == "refresh",
        "availability": availability,
        "missing": list(hit.get("missing") or availability.get("missing") or []),
    }
    if kind == "queue_task" and payload.get("task"):
        card["estimated_runtime"] = payload.get("task", {}).get("estimated_runtime")
    if swarm_shard:
        card["shard"] = swarm_shard
        card["payload"] = payload
    card["procureability_label"] = hit.get("action_label") or procureability_label(card)
    return card
