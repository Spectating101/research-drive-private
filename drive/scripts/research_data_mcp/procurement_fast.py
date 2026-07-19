#!/usr/bin/env python3
"""Fast procurement paths — unified local index, sync-wait policy."""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.magic_config import _runtime_minutes, load_magic_config
from scripts.research_data_mcp.procurement_constants import DOWNLOADABLE_VIA

STRONG_LOCAL_SCORE = 3.0

_REFRESH_RE = re.compile(r"\b(refresh|update|re-?collect|latest|re-?fetch|re-?run)\b", re.I)


def local_path_has_data(repo_root: Path, pattern: str) -> bool:
    """True when a registry local_path glob resolves to non-empty files or dirs."""
    pattern = str(pattern or "").strip()
    if not pattern:
        return False
    root = Path(repo_root).resolve()
    if "*" in pattern:
        matches = list(root.glob(pattern))[:24]
        if not matches:
            return False
        for path in matches:
            if path.is_file() and path.stat().st_size > 0:
                return True
            if path.is_dir():
                try:
                    if any(path.iterdir()):
                        return True
                except OSError:
                    continue
        return False
    path = root / pattern
    if path.is_file():
        return path.stat().st_size > 0
    if path.is_dir():
        try:
            return any(path.iterdir())
        except OSError:
            return False
    return False


def queue_output_on_disk(repo_root: Path, task: dict[str, Any]) -> bool:
    hint = str(task.get("output_hint") or "").strip().rstrip("/")
    if not hint:
        return False
    if local_path_has_data(repo_root, hint):
        return True
    return local_path_has_data(repo_root, f"{hint}/*")


def wants_refresh(message: str) -> bool:
    return bool(_REFRESH_RE.search(message or ""))


def catalog_plan_first(planner: Any, message: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Match queue/http/datacite plans from local catalog only (<10ms)."""
    context = context or {}
    try:
        plan = planner.plan_immediate_collect(message, context)
        if plan and plan.get("launchable"):
            return plan
    except Exception:
        if context.get("doi") or context.get("add_to_collection"):
            raise
    if not planner.wants_procurement(message):
        return None
    stub_advice = {"recommended": [], "verdict": "weak", "message": ""}
    return planner.plan_from_catalog(message, stub_advice, context)


def should_sync_wait(
    plan: dict[str, Any],
    config: dict[str, Any],
    *,
    queue_tasks: list[dict[str, Any]] | None = None,
) -> bool:
    """Only block the caller until jobs that finish in ~minutes or less."""
    if not plan:
        return False
    execute_cfg = config.get("execute") or {}
    sync_max = int(execute_cfg.get("sync_wait_max_minutes", 2))
    job_type = str(plan.get("job_type") or "")

    if job_type == "http_manifest":
        return True
    if job_type == "source_probe":
        return True
    if job_type == "scraper_run":
        return sync_max >= 1
    if job_type == "harvest_shard" and str(plan.get("action") or "") == "status":
        return True

    if job_type == "collection_hydrate" and str(plan.get("scope") or "") == "metadata":
        return True

    if job_type == "collection_queue_task":
        task_id = str(plan.get("task_id") or "")
        task = next((row for row in (queue_tasks or []) if row.get("id") == task_id), None)
        if not task:
            return False
        minutes = _runtime_minutes(str(task.get("estimated_runtime") or ""))
        if minutes is None:
            return False
        return minutes <= sync_max

    return False


def plan_runtime_note(
    plan: dict[str, Any],
    *,
    queue_tasks: list[dict[str, Any]] | None = None,
) -> str:
    """Human estimate for chat/CLI replies."""
    job_type = str(plan.get("job_type") or "")
    if job_type == "http_manifest":
        return "Usually finishes in under a minute."
    if job_type == "collection_queue_task":
        task_id = str(plan.get("task_id") or "")
        task = next((row for row in (queue_tasks or []) if row.get("id") == task_id), None)
        if task:
            est = str(task.get("estimated_runtime") or "").strip()
            if est:
                return f"Estimated runtime: {est}."
    return "Running in background — say **status** to check progress."


def _collect_score_boost(card: dict[str, Any]) -> float:
    """Prefer data already on disk; queue is for refresh, not default procurement."""
    via = str(card.get("collect_via") or "")
    readiness = str(card.get("analysis_readiness") or "")
    if card.get("local_ready") and via == "local_open":
        return 3.0
    if via == "queue":
        if card.get("refresh_only"):
            return 0.5
        return 1.1
    if readiness == "instant":
        return 2.2
    if via in {"http_manifest", "datacite", "local_open"}:
        return 1.8
    if via == "huggingface":
        return 1.2
    if via in {"spectator", "pipeline", "magic"}:
        return 1.0
    if card.get("can_collect") is False:
        return 0.4
    return 0.8


def _dedupe_key(cand: dict[str, Any]) -> str:
    return str(
        cand.get("handle")
        or cand.get("doi")
        or cand.get("dataset_id")
        or cand.get("task_id")
        or cand.get("title")
        or ""
    ).lower().strip()


def _scan_harvest_metadata(repo_root: Path, query: str, *, limit: int = 4) -> list[dict[str, Any]]:
    """Light scan of local DataCite harvest JSONL shards (when present on disk)."""
    from scripts.research_data_mcp.catalog_index import ProcurementCatalogIndex

    tokens = ProcurementCatalogIndex.tokens(query)
    if not tokens:
        return []
    root = repo_root / "data_lake/dataset_catalog/index_v3"
    if not root.is_dir():
        return []
    hits: list[tuple[float, dict[str, Any]]] = []
    files = sorted(root.glob("**/datacite_*.jsonl*"))[:6]
    for path in files:
        try:
            if path.suffix == ".gz":
                with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as fh:
                    lines = [fh.readline() for _ in range(40)]
            else:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[:40]
        except Exception:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            title = str(row.get("title") or row.get("attributes", {}).get("titles", [{}])[0].get("title", ""))
            doi = str(row.get("doi") or row.get("id") or "").strip()
            blob = f"{title} {doi}".lower()
            score = sum(1.0 for t in tokens if t in blob)
            if score <= 0:
                continue
            hits.append(
                (
                    score,
                    {
                        "kind": "datacite",
                        "doi": doi,
                        "title": title or doi,
                        "url": row.get("url") or (f"https://doi.org/{doi}" if doi else ""),
                        "source": "datacite_harvest_local",
                        "open_handle": f"doi:{doi}" if doi else "",
                        "procureability": {
                            "badges": ["datacite_harvest"],
                            "badge_labels": ["DataCite (local harvest)"],
                            "status": "downloadable",
                            "can_collect": True,
                        },
                    },
                )
            )
            if len(hits) >= limit * 3:
                break
    hits.sort(key=lambda x: (-x[0], x[1].get("doi", "")))
    return [row for _, row in hits[:limit]]


def local_search(
    gateway: Any,
    query: str,
    *,
    limit: int = 8,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Unified local index: registry + dictionary. Composer judges fit."""
    _ = profile
    from scripts.research_data_mcp.candidate_card import procureability_label
    from scripts.research_data_mcp.catalog_index import ProcurementCatalogIndex
    from scripts.research_data_mcp.collection_search_rank import (
        candidates_to_chat_hits,
        is_infra_candidate,
        is_ops_query,
        research_rank_multiplier,
    )
    from scripts.research_data_mcp.procureability import registry_procureability
    from scripts.research_data_mcp.procurement_search import (
        acquisition_route_rows,
        candidate_from_acquisition_route,
        candidate_from_row,
        score_row,
    )

    query = query.strip()
    if not query:
        return {
            "query": query,
            "candidates": [],
            "sources": ["local"],
            "top_score": 0.0,
            "index_miss": True,
            "weak_match": False,
            "fast_path": True,
        }

    cat = ProcurementCatalogIndex(gateway.repo_root, gateway.orchestrator)
    raw: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def _add(cand: dict[str, Any]) -> None:
        if is_infra_candidate(cand) and not is_ops_query(query):
            return
        mult = research_rank_multiplier(
            kind=str(cand.get("kind") or ""),
            partition_id=str(cand.get("partition_id") or ""),
            dataset_id=str(cand.get("dataset_id") or ""),
            query=query,
        )
        cand = dict(cand)
        cand["score"] = round(float(cand.get("score") or 0) * mult, 2)
        if mult <= 0.1 and float(cand["score"]) < 0.5:
            return
        key = _dedupe_key(cand)
        if key and key not in seen_keys:
            seen_keys.add(key)
            raw.append(cand)

    try:
        catalog = gateway.procurement_catalog(q=query, limit=max(20, limit * 2))
    except Exception:
        catalog = {}

    on_disk_ids: set[str] = set()

    for row in catalog.get("registry") or []:
        dataset_id = str(row.get("dataset_id") or "")
        if not dataset_id:
            continue
        local_path = str(row.get("local_path") or "")
        on_disk = local_path_has_data(gateway.repo_root, local_path) if local_path else False
        if on_disk:
            on_disk_ids.add(dataset_id)
        proc = row.get("procureability") or registry_procureability(row)
        if on_disk:
            badges = list(proc.get("badges") or [])
            if "promoted" not in badges:
                badges.append("promoted")
            proc = {**proc, "badges": badges, "can_collect": True, "status": "ready"}
        item = {
            "kind": "local_registry",
            "dataset_id": dataset_id,
            "title": row.get("name") or dataset_id,
            "source": "registry",
            "local_path": local_path,
            "local_ready": on_disk,
            "analysis_readiness": row.get("analysis_readiness"),
            "procureability": proc,
            "tags": row.get("tags") or row.get("keywords") or [],
            "description": row.get("recommended_use") or row.get("description") or "",
        }
        sc = score_row(item, query)
        if sc <= 0:
            continue
        cand = candidate_from_row(item, 0, score=sc)
        cand["score"] = round(sc * _collect_score_boost(cand), 2)
        cand["kind"] = "registry_dataset"
        _add(cand)

    try:
        curated = gateway.search_catalog(q=query, limit=max(8, limit))
        for row in curated.get("rows") or []:
            item = {
                "kind": "catalog",
                "dataset_id": row.get("dataset_id") or row.get("id"),
                "title": row.get("title") or row.get("name"),
                "source": row.get("source") or "catalog",
                "description": row.get("description"),
                "url": row.get("url"),
                "procureability": row.get("procureability")
                or {"status": "catalog", "can_collect": bool(row.get("launchable"))},
            }
            sc = score_row(item, query)
            if sc <= 0:
                continue
            cand = candidate_from_row(item, 0, score=sc)
            cand["score"] = round(sc * _collect_score_boost(cand), 2)
            _add(cand)
    except Exception:
        pass

    for score, row in acquisition_route_rows(gateway, query, limit=max(limit, 8)):
        cand = candidate_from_acquisition_route(row, 0, score=score)
        cand["score"] = round(float(cand.get("score") or 0) * _collect_score_boost(cand), 2)
        _add(cand)

    datacite_sources: list[str] = []
    from scripts.research_data_mcp.procurement_search import _tokens, relevance_score

    query_tokens = _tokens(query)
    for cand in raw:
        cand.setdefault("query_relevance", round(relevance_score(cand, query_tokens), 2))

    index_hits: list[dict[str, Any]] = []
    try:
        from scripts.research_data_mcp.collection_index import hit_to_candidate, search_index

        index_hits = search_index(gateway.repo_root, query, limit=max(limit, 10))
        for i, hit in enumerate(index_hits, 1):
            cand = hit_to_candidate(hit, i)
            cand["score"] = round(float(cand.get("score") or 0) * _collect_score_boost(cand), 2)
            _add(cand)
    except Exception:
        index_hits = []

    for task in catalog.get("queue_tasks") or []:
        task_id = str(task.get("id") or "")
        if not task_id:
            continue
        sc = cat.score_blob(query, task_id, task.get("title", ""), task.get("output_hint", ""))
        if sc <= 0:
            continue
        route = {
            "kind": "queue_task",
            "id": task_id,
            "task_id": task_id,
            "title": task.get("title") or task_id,
            "source": "queue",
            "badges": ["Collection queue"],
            "estimated_runtime": task.get("estimated_runtime"),
        }
        cand = candidate_from_acquisition_route(route, 0, score=sc)
        if task_id in on_disk_ids or queue_output_on_disk(gateway.repo_root, task):
            cand["refresh_only"] = True
            cand["local_ready"] = True
            sc *= 0.55
        cand["score"] = round(sc * _collect_score_boost(cand), 2)
        _add(cand)

    skip_harvest = bool(raw) and float(raw[0].get("score") or 0) >= 3.5
    if not skip_harvest:
        for row in _scan_harvest_metadata(gateway.repo_root, query, limit=4):
            sc = score_row(row, query, profile=profile)
            if sc <= 0:
                continue
            cand = candidate_from_row(row, 0, score=sc)
            cand["score"] = round(sc * _collect_score_boost(cand), 2)
            _add(cand)

    raw.sort(key=lambda c: float(c.get("score") or 0), reverse=True)

    from scripts.research_data_mcp.procurement_search import (
        _tokens,
        looks_like_index_miss,
        relevance_score,
    )

    query_tokens = _tokens(query)
    for cand in raw:
        cand["query_relevance"] = round(relevance_score(cand, query_tokens), 2)

    raw.sort(key=lambda c: float(c.get("score") or 0), reverse=True)
    candidates: list[dict[str, Any]] = []
    for i, cand in enumerate(raw[:limit], 1):
        cand = dict(cand)
        cand["index"] = i
        cand["procureability_label"] = procureability_label(cand)
        candidates.append(cand)

    chat_hits = candidates_to_chat_hits(candidates)

    top = float(candidates[0].get("score") or 0) if candidates else 0.0
    downloadable = [c for c in candidates if str(c.get("collect_via") or "") in DOWNLOADABLE_VIA]
    from scripts.research_data_mcp.procurement_search import looks_like_index_miss

    top_dl = max((float(c.get("score") or 0) for c in downloadable), default=0.0)
    index_miss = looks_like_index_miss(query, candidates, top_dl=top_dl)
    top_rel = float(candidates[0].get("query_relevance") or 0) if candidates else 0.0
    top_cand = candidates[0] if candidates else None

    return {
        "query": query,
        "candidates": candidates,
        "sources": ["registry", "curated", "collection_index", "local"],
        "top_score": top,
        "top_query_relevance": top_rel,
        "index_miss": index_miss,
        "weak_match": index_miss,
        "fast_path": True,
        "strong_local_hit": bool(
            top >= STRONG_LOCAL_SCORE
            and top_cand
            and top_cand.get("local_ready")
            and str(top_cand.get("collect_via") or "") == "local_open"
        ),
        "relevance_miss": False,
        "chat_hits": chat_hits,
        "research_first": not is_ops_query(query),
    }


def catalog_search(gateway: Any, query: str, *, limit: int = 6) -> dict[str, Any]:
    """Backward-compatible alias for local_search."""
    return local_search(gateway, query, limit=limit)


def advice_from_local_search(local: dict[str, Any], message: str) -> dict[str, Any]:
    """Lightweight advisor payload without legacy LLM calls — for chat / catalog-fast paths."""
    candidates = local.get("candidates") or []
    recommended = []
    for cand in candidates[:5]:
        kind = "queue_task" if cand.get("collect_via") == "queue" else "registry_dataset"
        if cand.get("kind") == "datacite":
            kind = "datacite"
        recommended.append(
            {
                "id": cand.get("dataset_id") or cand.get("doi") or cand.get("task_id") or cand.get("title"),
                "kind": kind,
                "reason": str(cand.get("procureability_label") or cand.get("collect_via") or ""),
            }
        )
    if local.get("strong_local_hit"):
        verdict = "good_fit"
        message_out = f"Local catalog match for: {message[:120]}"
    elif candidates and not local.get("index_miss"):
        verdict = "partial_fit"
        message_out = f"Local leads found; may need external supplement for: {message[:120]}"
    else:
        verdict = "weak"
        message_out = f"Weak local match for: {message[:120]}"
    return {
        "verdict": verdict,
        "message": message_out,
        "recommended": recommended,
        "not_recommended": [],
        "next_steps": ["download #1", "source this for me"] if local.get("index_miss") else ["download #1", "preview #1"],
        "engine": "local_search",
    }


def load_sync_config(repo_root: Any) -> dict[str, Any]:
    return load_magic_config(repo_root)
