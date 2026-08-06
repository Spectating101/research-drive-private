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

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_]{1,}")
SUBSCRIPT_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")

# Minimum token overlap between query and top hit before we trust local_open / strong_local_hit.
MIN_TOP_RELEVANCE = 1.0


def min_relevance_threshold(query: str) -> float:
    """Compound queries need more than one accidental token hit."""
    n = len(query_topic_tokens(query))
    if n >= 2:
        return 2.0
    if n == 0 and _query_geography_rules(query):
        return 0.0
    return MIN_TOP_RELEVANCE


PROCUREMENT_QUERY_STOPWORDS = frozenset(
    {
        "dataset", "datasets", "data", "panel", "research", "study", "metadata", "graph",
        "what", "which", "where", "when", "why", "how", "can", "could", "should", "would",
        "does", "the", "and", "for", "from", "with", "use", "using", "need", "want", "find",
        "help", "illustrate", "measure", "measurement", "measurements", "public", "open",
        "daily", "weekly", "monthly", "quarterly", "annual", "yearly", "time", "series",
        "my", "our", "we", "me", "of", "to", "in", "on", "at", "by", "as", "it", "are", "is", "do", "or",
        # Conversational Ask wrappers — must not inflate compound-query thresholds.
        "hold", "holds", "held", "holding", "holdings", "have", "has", "any", "some",
        "please", "tell", "show", "give", "list", "available", "there",
        # Weak question fillers (keep distinctive stems like "speeding" / "slowing").
        "up", "down", "out", "over", "into", "about", "again", "still", "just",
        "rise", "rising", "fell", "falling",
    }
)
QUERY_STOPWORDS = PROCUREMENT_QUERY_STOPWORDS  # backward compat for probe_url_selection

# Weak topical tokens — alone they must not keep a row when the query also names
# distinctive anchors (e.g. "country"+"news" from a "not a country-level news panel"
# correction phrase matching an Asia/GDELT query).
GENERIC_TOPIC_TOKENS = frozenset(
    {
        "country",
        "countries",
        "news",
        "media",
        "market",
        "markets",
        "stock",
        "stocks",
        "equity",
        "equities",
        "price",
        "prices",
        "return",
        "returns",
        "firm",
        "firms",
        "company",
        "companies",
        "global",
        "level",
        "record",
        "records",
        "value",
        "values",
        "ratio",
        "ratios",
        "index",
        "indexes",
        "indices",
        "security",
        "securities",
        "snapshot",
        "export",
        "mapping",
        "layer",
        "crosswalk",
        "lookup",
        "reference",
        "join",
        "joins",
    }
)


def _tokens(text: str) -> set[str]:
    normalized = str(text or "").translate(SUBSCRIPT_DIGITS).lower()
    return {t for t in TOKEN_RE.findall(normalized) if len(t) > 1 and t not in PROCUREMENT_QUERY_STOPWORDS}


GeographyRule = tuple[
    re.Pattern[str],
    re.Pattern[str] | None,
    re.Pattern[str],
    re.Pattern[str] | None,
    frozenset[str],
]

GEOGRAPHY_RULES: tuple[GeographyRule, ...] = (
    (
        re.compile(r"\b(?:united states|america|american)\b", re.I),
        re.compile(r"\b(?:US|USA)\b"),
        re.compile(r"\b(?:united states|america|american)\b", re.I),
        re.compile(r"\b(?:US|USA)\b"),
        frozenset({"us", "usa", "united", "states", "america", "american"}),
    ),
    (
        re.compile(r"\b(?:united kingdom|great britain|british|england|english)\b", re.I),
        re.compile(r"\bUK\b"),
        re.compile(r"\b(?:united kingdom|great britain|british|england|english)\b", re.I),
        re.compile(r"\bUK\b"),
        frozenset({"uk", "united", "kingdom", "great", "britain", "british", "england", "english"}),
    ),
    (
        re.compile(r"\b(?:taiwan|taiwanese|taipei)\b", re.I),
        re.compile(r"\bTW\b"),
        re.compile(r"\b(?:taiwan|taiwanese|taipei)\b", re.I),
        re.compile(r"\bTW\b"),
        frozenset({"tw", "taiwan", "taiwanese", "taipei"}),
    ),
    (
        re.compile(r"\b(?:indonesia|indonesian)\b", re.I),
        None,
        re.compile(r"\b(?:indonesia|indonesian)\b", re.I),
        None,
        frozenset({"indonesia", "indonesian"}),
    ),
    (
        re.compile(r"\b(?:china|chinese)\b", re.I),
        re.compile(r"\bCN\b"),
        re.compile(r"\b(?:china|chinese)\b", re.I),
        re.compile(r"\bCN\b"),
        frozenset({"cn", "china", "chinese"}),
    ),
    (
        re.compile(r"\b(?:japan|japanese)\b", re.I),
        re.compile(r"\bJP\b"),
        re.compile(r"\b(?:japan|japanese)\b", re.I),
        re.compile(r"\bJP\b"),
        frozenset({"jp", "japan", "japanese"}),
    ),
    (
        re.compile(r"\b(?:south korea|korea|korean)\b", re.I),
        re.compile(r"\bKR\b"),
        re.compile(r"\b(?:south korea|korea|korean)\b", re.I),
        re.compile(r"\bKR\b"),
        frozenset({"kr", "south", "korea", "korean"}),
    ),
    (
        re.compile(r"\b(?:european union|europe|european)\b", re.I),
        re.compile(r"\bEU\b"),
        re.compile(r"\b(?:european union|europe|european)\b", re.I),
        re.compile(r"\bEU\b"),
        frozenset({"eu", "european", "union", "europe"}),
    ),
)


def _query_geography_rules(query: str) -> list[GeographyRule]:
    return [rule for rule in GEOGRAPHY_RULES if rule[0].search(query) or (rule[1] and rule[1].search(query))]


def query_topic_tokens(query: str) -> set[str]:
    """Distinctive need terms, excluding geography enforced separately."""
    geography = {token for rule in _query_geography_rules(query) for token in rule[4]}
    return _tokens(query) - geography


def distinctive_topic_tokens(query: str) -> set[str]:
    """Topic tokens strong enough to establish on-topic vault relevance."""
    return {
        t
        for t in query_topic_tokens(query)
        if t not in GENERIC_TOPIC_TOKENS and len(t) > 2
    }


def query_geography_ok(row: dict[str, Any], query: str) -> bool:
    """A named geography is a requirement, but naming two is not a demand for both.

    This stays a filter rather than a ranking boost: a Korea question should not
    return Taiwan panels.  It requires *any* named geography rather than all of
    them, because requiring all made every multi-country question unanswerable.

    Measured against the live registry, ``all()`` returned zero rows for "Taiwan
    and Japan" -- each country matches datasets on its own, but no single row
    mentions both -- and zero was the answer for five of ten realistic faculty
    questions.  A dataset covering Taiwan is a legitimate partial answer to a
    Taiwan-and-Japan question; reporting which part is missing is the coverage
    assessment's job, and it can say nothing about rows retrieval already threw
    away.
    """
    required = _query_geography_rules(query)
    if not required:
        return True
    blob = _row_blob_raw(row).translate(SUBSCRIPT_DIGITS)
    return any(bool(rule[2].search(blob) or (rule[3] and rule[3].search(blob))) for rule in required)


def query_geography_match_count(row: dict[str, Any], query: str) -> int:
    """How many named geographies a row satisfies, for ranking above the filter.

    Preserves the precision intent of demanding geography evidence: a row
    matching both Taiwan and Japan should outrank one matching only Taiwan,
    without the single-match row being deleted from the results entirely.
    """
    required = _query_geography_rules(query)
    if not required:
        return 0
    blob = _row_blob_raw(row).translate(SUBSCRIPT_DIGITS)
    return sum(bool(rule[2].search(blob) or (rule[3] and rule[3].search(blob))) for rule in required)


def _row_blob_raw(row: dict[str, Any]) -> str:
    """Match blob for relevance — includes vault meaning Store fields (aliases/keywords)."""
    parts = [
        str(row.get("display_name") or ""),
        str(row.get("title") or row.get("name") or ""),
        str(row.get("dataset_id") or row.get("id") or ""),
        str(row.get("doi") or ""),
        str(row.get("publisher") or ""),
        str(row.get("domain") or ""),
        str(row.get("url") or ""),
        str(row.get("local_path") or ""),
        str(row.get("description") or ""),
        str(row.get("one_line") or ""),
        str(row.get("meaning_about") or ""),
        str(row.get("recommended_use") or ""),
        " ".join(str(x) for x in (row.get("aliases") or [])),
        " ".join(str(x) for x in (row.get("keywords") or [])),
        " ".join(str(x) for x in (row.get("tags") or [])),
    ]
    return " ".join(parts)


def _row_blob(row: dict[str, Any]) -> str:
    return _row_blob_raw(row).lower()


def _token_in_blob(token: str, blob: str) -> bool:
    return token in blob


def relevance_score(row: dict[str, Any], query_tokens: set[str]) -> float:
    """Lexical overlap; ignore generic-only coincidence when distinctive tokens exist.

    If the query names distinctive anchors (gdelt, keeling, shock, …) and the row
    matches none of them, return 0 even when weak tokens like country/news hit —
    including hits inside “not a … news panel” correction prose.
    """
    blob = _row_blob(row)
    if not query_tokens:
        return 0.0
    hits = {t for t in query_tokens if _token_in_blob(t, blob)}
    if not hits:
        return 0.0
    distinctive = {t for t in query_tokens if t not in GENERIC_TOPIC_TOKENS and len(t) > 2}
    if distinctive and not (hits & distinctive):
        return 0.0
    return float(len(hits))


def top_query_relevance(query: str, candidate: dict[str, Any] | None) -> float:
    if not candidate:
        return 0.0
    return relevance_score(candidate, query_topic_tokens(query))


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
    for key in (
        "tags",
        "keywords",
        "aliases",
        "description",
        "one_line",
        "meaning_about",
        "recommended_use",
        "display_name",
    ):
        value = row.get(key)
        if value:
            card.setdefault(key, value)
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
