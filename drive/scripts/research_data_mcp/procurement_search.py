#!/usr/bin/env python3
"""Ranked multi-source dataset discovery for conversational procurement."""

from __future__ import annotations

import re
from typing import Any

from scripts.research_data_mcp.candidate_card import enrich_candidate_card, normalize_candidate_scores
from scripts.research_data_mcp.scrape_plan import candidate_from_url, extract_urls

NOISE_REGISTRY_IDS = (
    "coingecko",
    "collection_queue",
    "catalogue",
    "catalog",
    "external_dataset",
    "curated_external",
    "metadata_catalog",
)

TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")

# Minimum token overlap between query and top hit before we trust local_open / strong_local_hit.
MIN_TOP_RELEVANCE = 1.0


def min_relevance_threshold(query: str) -> float:
    """Long compound queries need more than one accidental token hit."""
    n = len(_tokens(query))
    if n >= 6:
        return 2.0
    if n >= 4:
        return 1.5
    return MIN_TOP_RELEVANCE


PROCUREMENT_QUERY_STOPWORDS = frozenset({"dataset", "data", "panel", "research", "study", "metadata", "graph"})
QUERY_STOPWORDS = PROCUREMENT_QUERY_STOPWORDS  # backward compat for probe_url_selection

# When query contains domain anchor tokens, top hit must match same domain in blob.
def _tokens(text: str) -> set[str]:
    return {t for t in TOKEN_RE.findall(text.lower()) if len(t) > 2 and t not in PROCUREMENT_QUERY_STOPWORDS}


def _row_blob(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("title") or row.get("name") or ""),
        str(row.get("dataset_id") or row.get("id") or ""),
        str(row.get("doi") or ""),
        str(row.get("publisher") or ""),
        str(row.get("domain") or ""),
        str(row.get("url") or ""),
        str(row.get("description") or ""),
        " ".join(str(x) for x in (row.get("tags") or row.get("keywords") or [])),
    ]
    return " ".join(parts).lower()


def _token_in_blob(token: str, blob: str) -> bool:
    return token in blob


def relevance_score(row: dict[str, Any], query_tokens: set[str]) -> float:
    blob = _row_blob(row)
    if not query_tokens:
        return 0.0
    return float(sum(1.0 for t in query_tokens if _token_in_blob(t, blob)))


def top_query_relevance(query: str, candidate: dict[str, Any] | None) -> float:
    if not candidate:
        return 0.0
    return relevance_score(candidate, _tokens(query))


def relevance_weak_miss(query: str, candidates: list[dict[str, Any]]) -> bool:
    """True when the top hit lacks enough token overlap to trust follow-through."""
    if not candidates:
        return True
    top = candidates[0]
    rel = float(top.get("query_relevance") or top_query_relevance(query, top))
    return rel < min_relevance_threshold(query)


def domain_anchor_ok(query: str, candidate: dict[str, Any] | None) -> bool:
    """Vault/dictionary ranking only — no domain keyword gates."""
    _ = query, candidate
    return True


def _rerank_by_query_relevance(candidates: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    for cand in candidates:
        cand["query_relevance"] = round(top_query_relevance(query, cand), 2)
    return candidates


FIXTURE_DOIS = frozenset({"10.7910/DVN/SIMTW1", "10.7910/dvn/simtw1"})
FIXTURE_TITLE_MARKERS = ("(simulated)", "[simulated]", "simulated)")


def is_fixture_candidate(cand: dict[str, Any]) -> bool:
    doi = str(cand.get("doi") or "").upper()
    if "SIMTW1" in doi or doi in {d.upper() for d in FIXTURE_DOIS}:
        return True
    title = str(cand.get("title") or "").lower()
    return any(marker in title for marker in FIXTURE_TITLE_MARKERS)


def _demote_fixture_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for cand in candidates:
        if is_fixture_candidate(cand):
            cand["score"] = round(float(cand.get("score") or 0) * 0.02, 2)
            cand["fixture_row"] = True
    candidates.sort(key=lambda row: float(row.get("score") or 0), reverse=True)
    for i, cand in enumerate(candidates, 1):
        cand["index"] = i
    return candidates


def datacite_supplement_queries(query: str) -> list[str]:
    q = (query or "").strip()
    return [q] if q else []


def looks_like_index_miss(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    top_dl: float,
    judgment: dict[str, Any] | None = None,
) -> bool:
    """Soft catalog signal — Composer decides whether hits are on-topic."""
    _ = query, judgment
    if not candidates:
        return True
    top = candidates[0]
    if bool(top.get("local_ready")) and float(top.get("score") or 0) >= 3.0:
        return False
    return top_dl < 2.0


def _demote_consumer_web(candidates: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    _ = query
    return candidates


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for cand in candidates:
        key = str(cand.get("handle") or cand.get("doi") or cand.get("title") or "").lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(cand)
    for i, cand in enumerate(unique, 1):
        cand["index"] = i
    return unique


def kind_bonus(row: dict[str, Any], query_tokens: set[str]) -> float:
    kind = str(row.get("kind") or "")
    proc = row.get("procureability") or {}
    can_collect = proc.get("can_collect")
    status = str(proc.get("status") or "")

    if kind == "datacite":
        if can_collect is True or status == "downloadable":
            return 3.0
        if status == "error" or "404" in str(proc.get("reason") or "").lower():
            return -6.0
        if can_collect is False or status in {"metadata_only"}:
            return -2.0
        if "zenodo" in str(row.get("url") or "").lower():
            return 2.0
        return 1.0
    if kind == "huggingface":
        return 2.5
    if kind == "catalog":
        return 1.2
    if kind == "partition":
        rel = relevance_score(row, query_tokens)
        pid = str(row.get("partition_id") or "").lower()
        path_boost = sum(1.0 for t in query_tokens if t in pid.replace("-", "_").replace(".", "_"))
        return 3.5 + rel + path_boost
    if kind in {"local_registry", "registry_dataset"}:
        did = str(row.get("dataset_id") or row.get("id") or "").lower()
        if any(n in did for n in NOISE_REGISTRY_IDS):
            if not query_tokens & set(did.split("_")):
                return -2.5
        rel = relevance_score(row, query_tokens)
        if row.get("local_ready"):
            return 3.5 if rel >= 1.0 else 0.25
        readiness = str(row.get("analysis_readiness") or "")
        if readiness == "instant":
            return 2.0
        if "promoted" in str(proc.get("badges") or []):
            return 1.5
        if status == "metadata_only" or "metadata" in str(proc.get("badge_labels") or []).lower():
            return -0.5
        return 0.5
    return 0.0


def is_noise_registry(row: dict[str, Any], query: str) -> bool:
    if str(row.get("kind") or "") not in {"local_registry", "registry_dataset"}:
        return False
    did = str(row.get("dataset_id") or row.get("id") or "").lower()
    if not any(n in did for n in NOISE_REGISTRY_IDS):
        return False
    qtok = _tokens(query)
    did_tok = _tokens(did.replace("_", " "))
    return not (qtok & did_tok)


def score_row(row: dict[str, Any], query: str, *, profile: dict[str, Any] | None = None) -> float:
    _ = profile  # faculty context is for desk brief / Composer — not catalog ranking
    if is_noise_registry(row, query):
        return -5.0
    qtok = _tokens(query)
    return relevance_score(row, qtok) + kind_bonus(row, qtok)


def candidate_from_row(row: dict[str, Any], index: int, *, score: float = 0.0) -> dict[str, Any]:
    kind = str(row.get("kind") or "")
    doi = str(row.get("doi") or "")
    hf_id = str(row.get("id") or "") if kind == "huggingface" else ""
    dataset_id = str(row.get("dataset_id") or row.get("id") or "")
    handle = str(row.get("open_handle") or "")
    resolved = row.get("resolved") or {}
    files = resolved.get("files") or []
    if doi and files:
        primary_name = str(files[0].get("key") or files[0].get("filename") or "")
        if primary_name:
            handle = f"doi:{doi}@file:{primary_name}"
    if not handle and doi:
        handle = f"doi:{doi}"
    if not handle and hf_id and kind == "huggingface":
        handle = f"hf:{hf_id}"
    if not handle and kind == "local_registry" and dataset_id:
        handle = f"dataset:{dataset_id}"

    proc = row.get("procureability") or {}
    can_collect = proc.get("can_collect")
    status = str(proc.get("status") or "")
    collect_via = "none"
    if kind == "datacite" and doi and can_collect is not False and status not in {"error", "metadata_only"}:
        collect_via = "datacite"
    elif kind == "huggingface" and hf_id:
        collect_via = "huggingface"
    elif kind in {"local_registry", "registry_dataset"}:
        reg_id = dataset_id or str(row.get("dataset_id") or row.get("id") or "")
        if reg_id:
            dataset_id = reg_id
        if row.get("local_ready") or str(row.get("analysis_readiness") or "") == "instant" or "promoted" in str(
            proc.get("badges") or []
        ):
            collect_via = "local_open"
        elif doi:
            collect_via = "datacite"

    local_ready = row.get("local_ready")
    if collect_via == "local_open" and not local_ready:
        local_ready = True

    card = {
        "index": index,
        "kind": kind,
        "title": row.get("title") or row.get("name") or doi or hf_id or dataset_id,
        "doi": doi,
        "dataset_id": dataset_id if kind in {"local_registry", "registry_dataset"} else "",
        "url": row.get("url"),
        "handle": handle,
        "source": row.get("source") or kind,
        "can_collect": True if collect_via not in {"", "none"} and can_collect is not False else can_collect,
        "collect_via": collect_via,
        "badges": proc.get("badge_labels") or proc.get("badges") or [],
        "status": proc.get("status"),
        "score": round(score, 2),
        "analysis_readiness": row.get("analysis_readiness"),
        "local_ready": local_ready,
        "local_path": row.get("local_path"),
    }
    return enrich_candidate_card(card, row)


def candidate_from_acquisition_route(row: dict[str, Any], index: int, *, score: float = 0.0) -> dict[str, Any]:
    kind = str(row.get("kind") or "")
    via_map = {
        "spectator_script": "spectator",
        "queue_task": "queue",
        "registered_pipeline": "pipeline",
        "acquisition_plan": "magic",
    }
    collect_via = via_map.get(kind, "job")
    badges = list(row.get("badges") or [])
    if kind == "spectator_script":
        badges = badges or ["Cluster scrape", "Puppeteer"]
    elif kind == "queue_task":
        badges = badges or ["Collection queue"]
    elif kind == "registered_pipeline":
        badges = badges or ["Registered pipeline"]
    elif kind == "acquisition_plan":
        badges = badges or ["Magic procure", "Probe + scrape"]

    card = {
        "index": index,
        "kind": kind,
        "title": row.get("title") or row.get("id") or "Acquisition route",
        "doi": "",
        "dataset_id": str(row.get("task_id") or row.get("pipeline_id") or row.get("script_key") or ""),
        "url": row.get("url"),
        "handle": "",
        "source": row.get("source") or kind,
        "can_collect": True,
        "collect_via": collect_via,
        "script_key": row.get("script_key"),
        "task_id": row.get("task_id"),
        "pipeline_id": row.get("pipeline_id"),
        "badges": badges,
        "status": row.get("status") or "runnable",
        "score": round(score, 2),
        "refresh_only": row.get("refresh_only"),
        "local_ready": row.get("local_ready"),
        "estimated_runtime": row.get("estimated_runtime"),
    }
    return enrich_candidate_card(card, row)


def acquisition_route_rows(gateway: Any, query: str, *, limit: int = 3) -> list[tuple[float, dict[str, Any]]]:
    """Spectator scrapers, queue tasks, and pipelines matched to the query."""
    from scripts.research_data_mcp.catalog_index import ProcurementCatalogIndex

    cat = ProcurementCatalogIndex(gateway.repo_root, gateway.orchestrator)
    scored: list[tuple[float, dict[str, Any]]] = []

    for script in cat.spectator_scripts():
        sc = cat.score_blob(query, script.get("id", ""), script.get("script", ""))
        if sc > 0:
            scored.append(
                (
                    sc + 1.5,
                    {
                        "kind": "spectator_script",
                        "id": script["id"],
                        "script_key": script["id"],
                        "title": f"Cluster scrape: {script['id'].replace('_', ' ')}",
                        "source": "cluster_scrape",
                        "badges": ["windows_lab", "JS scrape"],
                    },
                )
            )

    for task in cat.match_queue_tasks(query, runnable_only=True, limit=3):
        sc = cat.score_blob(query, task.get("id", ""), task.get("title", ""), task.get("output_hint", ""))
        if sc > 0:
            scored.append(
                (
                    sc + 1.0,
                    {
                        "kind": "queue_task",
                        "task_id": task["id"],
                        "title": task.get("title") or task["id"],
                        "source": "collection_queue",
                        "badges": ["Queue task", "Runnable" if task.get("runnable") else "Queued"],
                        "status": "runnable" if task.get("runnable") else "blocked",
                    },
                )
            )

    for pipeline in cat.match_pipelines(query, limit=2):
        sc = cat.score_blob(query, pipeline.get("id", ""), pipeline.get("label", ""))
        if sc > 0:
            scored.append(
                (
                    sc + 0.8,
                    {
                        "kind": "registered_pipeline",
                        "pipeline_id": pipeline["id"],
                        "title": pipeline.get("label") or pipeline["id"],
                        "source": "pipeline",
                        "badges": ["Pipeline", str(pipeline.get("pool") or "cluster")],
                    },
                )
            )

    scored.sort(key=lambda x: (-x[0], str(x[1].get("title") or "")))
    return scored[:limit]


def smart_search(
    gateway: Any,
    query: str,
    *,
    limit: int = 6,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Catalog search — local registry + dictionary only. Composer judges fit and next tools."""
    _ = profile
    query = query.strip()
    if not query:
        return {"query": query, "candidates": [], "sources": [], "index_miss": True}

    from scripts.research_data_mcp.candidate_card import procureability_label
    from scripts.research_data_mcp.collection_search_rank import candidates_to_chat_hits
    from scripts.research_data_mcp.procurement_fast import local_search

    local = local_search(gateway, query, limit=limit)
    candidates = _dedupe_candidates(list(local.get("candidates") or []))
    candidates = _demote_fixture_rows(candidates)
    candidates = normalize_candidate_scores(candidates)
    for cand in candidates:
        cand.setdefault("procureability_label", procureability_label(cand))

    top_score = float(candidates[0].get("score") or 0) if candidates else 0.0
    top = candidates[0] if candidates else {}
    index_miss = not candidates or top_score < 2.0
    strong_local = bool(
        top.get("local_ready")
        and str(top.get("collect_via") or "") == "local_open"
        and top_score >= 3.0
    )

    return {
        "query": query,
        "candidates": candidates[:limit],
        "sources": sorted(set(local.get("sources") or [])),
        "top_score": top_score,
        "index_miss": index_miss,
        "weak_match": index_miss,
        "strong_local_hit": strong_local,
        "relevance_miss": False,
        "chat_hits": candidates_to_chat_hits(candidates[:limit]),
        "judgment": {
            "verdict": "composer_decides",
            "message": "Catalog rows only — Composer chooses describe/sample/collect via MCP.",
            "engine": "local_catalog",
            "not_recommended": [],
        },
    }
