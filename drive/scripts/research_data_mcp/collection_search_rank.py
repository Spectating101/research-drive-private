#!/usr/bin/env python3
"""Research vs ops ranking — kind-based only (no regex judgment)."""

from __future__ import annotations

from typing import Any

INFRA_KINDS = frozenset({"datacite_shard", "datacite_swarm", "tracker"})
OPS_PARTITIONS = frozenset({"catalog.datacite-harvest"})
OPS_REGISTRY_IDS = frozenset({"datacite_local_harvest_status"})

_OPS_WORDS = frozenset(
    {
        "hydrate",
        "shard",
        "swarm",
        "rclone",
        "backfill",
        "vault",
    }
)


def _words(text: str) -> set[str]:
    return {w for w in text.lower().replace("-", " ").split() if w}


def is_ops_query(query: str) -> bool:
    """Explicit hydrate/ops intent — not topic research."""
    q = str(query or "").strip().lower()
    if not q:
        return False
    words = _words(q)
    if words & _OPS_WORDS:
        return True
    if "harvest status" in q or "on drive" in q:
        return True
    if "datacite harvest" in q or "datacite shard" in q:
        return True
    for word in words:
        if word.startswith("y20") and "_q" in word:
            return True
    return False


def is_infra_candidate(cand: dict[str, Any]) -> bool:
    kind = str(cand.get("kind") or "")
    if kind in INFRA_KINDS:
        return True
    if kind == "partition" and str(cand.get("partition_id") or "") in OPS_PARTITIONS:
        return True
    if str(cand.get("dataset_id") or "") in OPS_REGISTRY_IDS:
        return True
    if kind == "registry_dataset" and str(cand.get("id") or "").endswith("datacite_local_harvest_status"):
        return True
    return False


def research_rank_multiplier(
    *,
    kind: str = "",
    partition_id: str = "",
    dataset_id: str = "",
    query: str,
) -> float:
    """Kind-based scale only — Composer judges relevance."""
    if is_ops_query(query):
        if kind in INFRA_KINDS:
            return 1.4
        if partition_id in OPS_PARTITIONS:
            return 1.2
        return 1.0

    if kind in INFRA_KINDS:
        return 0.05
    if kind == "partition" and partition_id in OPS_PARTITIONS:
        return 0.08
    if dataset_id in OPS_REGISTRY_IDS:
        return 0.1
    if kind == "registry_dataset":
        return 1.45
    if kind in {"curated_catalog", "doi_locator", "local_registry", "catalog"}:
        return 1.35
    if kind == "datacite":
        return 1.42
    if kind == "queue_task":
        return 1.05
    return 1.0


def apply_research_rank(hit: dict[str, Any], query: str) -> dict[str, Any]:
    payload = hit.get("payload") or {}
    mult = research_rank_multiplier(
        kind=str(hit.get("kind") or ""),
        partition_id=str(hit.get("partition_id") or ""),
        dataset_id=str(payload.get("dataset_id") or ""),
        query=query,
    )
    out = dict(hit)
    out["score"] = round(float(hit.get("score") or 0) * mult, 2)
    out["infra_hit"] = mult <= 0.1
    return out


def filter_research_hits(hits: list[dict[str, Any]], query: str, *, limit: int) -> list[dict[str, Any]]:
    if is_ops_query(query):
        return hits[:limit]

    ranked = [apply_research_rank(h, query) for h in hits]
    ranked.sort(key=lambda h: float(h.get("score") or 0), reverse=True)
    out: list[dict[str, Any]] = []
    for hit in ranked:
        if hit.get("infra_hit") and float(hit.get("score") or 0) < 0.5:
            continue
        out.append(hit)
        if len(out) >= limit:
            break
    return out


def candidates_to_chat_hits(candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for cand in candidates:
        action = str(cand.get("action") or "")
        if not action:
            via = str(cand.get("collect_via") or "")
            if cand.get("local_ready") and via == "local_open":
                action = "query_now"
            elif via == "hydrate":
                action = "hydrate"
            elif via == "datacite":
                action = "collect"
            elif via == "queue":
                action = "refresh" if cand.get("refresh_only") else "collect"

        idx = int(cand.get("index") or len(out) + 1)
        say = {
            "query_now": f"preview #{idx}",
            "hydrate": f"hydrate #{idx}",
            "refresh": f"refresh then collect #{idx}",
            "collect": f"collect #{idx}",
            "search_datacite": "source this for me",
        }.get(action, f"describe #{idx}")

        missing = list(cand.get("missing") or [])
        if missing and action in {"hydrate", "search_datacite", "collect"}:
            say = f"{say} (gap: {missing[0]})"

        title = str(cand.get("title") or "")
        if cand.get("chat_line"):
            line = str(cand["chat_line"])
        else:
            label = cand.get("procureability_label") or cand.get("collect_via") or "dataset"
            line = f"{title} — {label}"

        out.append(
            {
                "n": str(idx),
                "title": title,
                "line": line,
                "action": action,
                "say": say,
                "missing": ",".join(str(m) for m in missing),
            }
        )
    return out
