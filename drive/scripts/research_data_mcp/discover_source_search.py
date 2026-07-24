"""Discover Explore — normalized source/provider/connector search.

Library owns held registry assets. This contract surfaces known external /
sourceable providers and connectors from desk + databank configs. It does not
default to registry datasets and does not invent remote search success.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.access_scope import load_access_scope
from scripts.research_data_mcp.candidate_key import stamp_rows, with_candidate_key
from scripts.research_data_mcp.source_map import load_desk_connectors, load_source_map

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-]{1,}", re.I)

# Lab-only / non-Explore default kinds — never emit as registry datasets here.
_SKIP_SOURCE_IDS = frozenset({"derived_research_panels"})
_SKIP_ACCESS_MODES = frozenset({"derived_internal"})

_KIND_RANK = {"source": 0, "provider": 1, "connector": 2, "live_candidate": 3}

# Bounded live adapters already implemented in-tree.
_LIVE_ADAPTERS = frozenset({"huggingface", "datacite"})
_LIVE_PER_ADAPTER_CAP = 5
_LIVE_TIMEOUT_SEC = 8

# Query-domain cues for hybrid capability-aware semantic ranking.
_ONCHAIN_QUERY_TERMS = frozenset(
    {
        "blockchain",
        "onchain",
        "crypto",
        "cryptocurrency",
        "ethereum",
        "bitcoin",
        "btc",
        "eth",
        "stablecoin",
        "stablecoins",
        "usdc",
        "defi",
        "web3",
        "token",
        "tokens",
        "nft",
        "mempool",
        "wallet",
        "wallets",
    }
)
_ONCHAIN_CAPABILITIES = frozenset({"onchain_crypto"})
_GOVERNANCE_CAPABILITIES = frozenset({"governance_regulatory"})
_ONCHAIN_SOURCE_HINTS = frozenset(
    {
        "ethereum",
        "bigquery",
        "onchain",
        "on-chain",
        "crypto",
        "stablecoin",
        "blockchain",
        "nft",
    }
)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


def _expand_blob_tokens(text: str) -> set[str]:
    """Tokenize including underscore/hyphen splits so capabilities match natural wording."""
    raw = _tokens(text)
    expanded = set(raw)
    for tok in list(raw):
        for part in re.split(r"[_\-]+", tok):
            if len(part) > 1:
                expanded.add(part.lower())
    return expanded


def _detect_query_domains(query: str) -> set[str]:
    """Transparent domain tags from natural-language Explore queries."""
    q = str(query or "").strip().lower()
    if not q:
        return set()
    toks = _expand_blob_tokens(q)
    domains: set[str] = set()
    if toks & _ONCHAIN_QUERY_TERMS or "on-chain" in q or "stable coin" in q:
        domains.add("onchain")
    # "transaction history" alone is ambiguous; only tag onchain with crypto cues.
    if ("transaction" in toks or "transactions" in toks) and (
        toks & {"blockchain", "ethereum", "crypto", "cryptocurrency", "onchain", "stablecoin", "stablecoins", "web3", "defi", "token", "tokens"}
        or "on-chain" in q
    ):
        domains.add("onchain")
    if toks & {"edgar", "sec", "mops", "governance", "regulatory", "filing", "filings", "disclosure", "disclosures"}:
        domains.add("governance")
    return domains


def _row_caps(row: dict[str, Any]) -> set[str]:
    return {str(c).lower() for c in (row.get("capabilities") or []) if str(c).strip()}


def _domain_capability_affinity(
    query: str,
    row: dict[str, Any],
    domains: set[str],
) -> tuple[float, dict[str, Any]]:
    """Capability/domain boost from real source metadata — never LLM-invented scores."""
    signals: dict[str, Any] = {}
    if not domains:
        return 0.0, signals

    score = 0.0
    caps = _row_caps(row)
    blob = _blob(row)
    blob_toks = _expand_blob_tokens(blob)
    q_toks = _expand_blob_tokens(query)

    if "onchain" in domains:
        onchain_cap = bool(caps & _ONCHAIN_CAPABILITIES)
        onchain_meta = bool(blob_toks & _ONCHAIN_SOURCE_HINTS) or "on-chain" in blob
        if onchain_cap:
            score += 1.15
            signals["capability_match"] = sorted(caps & _ONCHAIN_CAPABILITIES)
        elif onchain_meta:
            score += 0.55
            signals["metadata_onchain_hint"] = True
        # Direct query-term hits in source identity/notes (ethereum, bigquery, …).
        identity_hits = sorted((q_toks | _ONCHAIN_QUERY_TERMS) & blob_toks & _ONCHAIN_SOURCE_HINTS)
        if identity_hits:
            score += min(0.55, 0.18 * len(identity_hits))
            signals["identity_term_hits"] = identity_hits
        # Pure governance/regulatory sources are the observed false-positive class.
        if (caps & _GOVERNANCE_CAPABILITIES) and not onchain_cap and not onchain_meta:
            score -= 1.05
            signals["domain_mismatch"] = "governance_regulatory"

    if "governance" in domains and not ("onchain" in domains):
        if caps & _GOVERNANCE_CAPABILITIES:
            score += 0.85
            signals["capability_match"] = sorted(caps & _GOVERNANCE_CAPABILITIES)

    return score, signals


def _normalize_score_map(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def _row_stable_id(row: dict[str, Any]) -> str:
    return str(
        row.get("candidate_key")
        or row.get("source_id")
        or row.get("external_id")
        or row.get("label")
        or id(row)
    )


def _hybrid_rerank_sources(
    base_scored: list[tuple[float, dict[str, Any]]],
    query: str,
    *,
    corpus: list[dict[str, Any]],
    base_mode: str,
) -> tuple[list[tuple[float, dict[str, Any]]], str]:
    """Blend embedding/lexical base scores with capability/domain + lexical signals.

    Ranking rule (transparent, non-LLM):
      hybrid = 0.30 * base_norm + 0.15 * lexical_norm + 0.55 * affinity_norm_signed
               + 0.12 * affinity_raw
               - 0.18 * domain_irrelevant_penalty
    where affinity comes from real capabilities/metadata (onchain_crypto vs governance).
    When the query has a clear domain tag, capability affinity dominates weak
    embedding/lexical coincidences (e.g. governance filings vs on-chain sources).
    """
    domains = _detect_query_domains(query)
    if not base_scored:
        return [], base_mode

    # Lexical scores over full corpus so sparse capability wording still contributes.
    lex_pairs = _lexical_capability_search(corpus, query, limit=max(len(corpus), 1))
    lex_by_id = {_row_stable_id(row): float(score) for score, row in lex_pairs}

    base_by_id = {_row_stable_id(row): float(score) for score, row in base_scored}
    # Ensure every base candidate has a lexical entry (0 if no token overlap).
    for rid in base_by_id:
        lex_by_id.setdefault(rid, 0.0)

    base_norm = _normalize_score_map(base_by_id)
    lex_norm = _normalize_score_map(lex_by_id) if any(lex_by_id.values()) else {k: 0.0 for k in base_by_id}

    affinity_raw: dict[str, float] = {}
    affinity_signals: dict[str, dict[str, Any]] = {}
    for score, row in base_scored:
        rid = _row_stable_id(row)
        aff, sig = _domain_capability_affinity(query, row, domains)
        affinity_raw[rid] = aff
        affinity_signals[rid] = sig

    # Signed normalization: keep mismatch penalties negative after scaling.
    if affinity_raw:
        mag = max(abs(v) for v in affinity_raw.values()) or 1.0
        affinity_norm = {k: v / mag for k, v in affinity_raw.items()}
    else:
        affinity_norm = {k: 0.0 for k in base_by_id}

    hybrid: list[tuple[float, dict[str, Any]]] = []
    for base_score, row in base_scored:
        rid = _row_stable_id(row)
        b = base_norm.get(rid, 0.0)
        lx = lex_norm.get(rid, 0.0)
        af = affinity_norm.get(rid, 0.0)
        final = (0.30 * b) + (0.15 * lx) + (0.55 * af)
        # Absolute affinity residual so strong capability matches break near-ties
        # even when base embedding scores are compressed.
        aff_raw = float(affinity_raw.get(rid, 0.0))
        final += 0.12 * aff_raw
        # Clear domain queries: demote domain-irrelevant catalog rows that only
        # matched via weak embedding/lexical coincidence.
        domain_penalty = 0.0
        if domains and abs(aff_raw) < 1e-12:
            domain_penalty = 0.18
            final -= domain_penalty

        annotated = dict(row)
        signals = {
            "domains": sorted(domains),
            "base_mode": base_mode,
            "base_score": round(float(base_score), 6),
            "base_norm": round(float(b), 6),
            "lexical_norm": round(float(lx), 6),
            "affinity_raw": round(aff_raw, 6),
            "affinity_norm": round(float(af), 6),
            "domain_irrelevant_penalty": round(domain_penalty, 6),
            "hybrid_score": round(float(final), 6),
            **(affinity_signals.get(rid) or {}),
        }
        annotated["rank_signals"] = signals
        parts = [f"base={base_mode}:{base_score:.3f}"]
        if domains:
            parts.append("domains=" + ",".join(sorted(domains)))
        if signals.get("capability_match"):
            parts.append("cap=" + ",".join(signals["capability_match"]))
        if signals.get("domain_mismatch"):
            parts.append("mismatch=" + str(signals["domain_mismatch"]))
        if signals.get("identity_term_hits"):
            parts.append("id_hits=" + ",".join(signals["identity_term_hits"]))
        parts.append(f"hybrid={final:.3f}")
        annotated["rank_explanation"] = "; ".join(parts)
        hybrid.append((final, annotated))

    hybrid.sort(key=lambda item: (-item[0], str(item[1].get("label") or "")))
    mode = "hybrid_capability" if domains else f"hybrid_{base_mode}"
    return hybrid, mode


def _provider_key(row: dict[str, Any]) -> str:
    connector = str(row.get("connector_id") or "").strip().lower()
    if connector in _LIVE_ADAPTERS:
        return connector
    provider = str(row.get("provider") or row.get("source") or "").strip().lower()
    if "hugging" in provider or provider in {"hf", "huggingface"}:
        return "huggingface"
    if "datacite" in provider:
        return "datacite"
    return provider or "unknown"


def _diversify_live_hits(
    hits: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Fair provider allocation for live candidates.

    Diversification rule (deterministic):
    1. Group hits by provider, preserving within-provider relevance order.
    2. Round-robin across providers that returned candidates until `limit`.
    3. This keeps both Hugging Face and DataCite in normal limits when both
       have hits, instead of letting the first adapter fill the entire window.
    """
    limit = max(0, int(limit or 0))
    if limit <= 0 or not hits:
        return []

    buckets: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for row in hits:
        key = _provider_key(row)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(row)

    if len(order) <= 1:
        return list(hits[:limit])

    # Soft per-provider cap: ceil(limit / n_providers), then fill remainder RR.
    n = len(order)
    soft_cap = max(1, (limit + n - 1) // n)
    taken = {k: 0 for k in order}
    indexes = {k: 0 for k in order}
    out: list[dict[str, Any]] = []

    def _take_one(provider: str) -> bool:
        idx = indexes[provider]
        bucket = buckets[provider]
        if idx >= len(bucket):
            return False
        if taken[provider] >= soft_cap and len(out) < limit:
            # Cap applies during first pass only; second pass ignores soft_cap.
            return False
        out.append(bucket[idx])
        indexes[provider] = idx + 1
        taken[provider] += 1
        return True

    # Pass 1: round-robin with soft cap.
    progress = True
    while len(out) < limit and progress:
        progress = False
        for provider in order:
            if len(out) >= limit:
                break
            if _take_one(provider):
                progress = True

    # Pass 2: fill remaining slots round-robin without soft cap.
    progress = True
    while len(out) < limit and progress:
        progress = False
        for provider in order:
            if len(out) >= limit:
                break
            idx = indexes[provider]
            bucket = buckets[provider]
            if idx >= len(bucket):
                continue
            out.append(bucket[idx])
            indexes[provider] = idx + 1
            progress = True

    return out


def _blob(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("source_id") or ""),
        str(row.get("id") or ""),
        str(row.get("label") or ""),
        str(row.get("provider") or ""),
        str(row.get("access_mode") or ""),
        str(row.get("status") or ""),
        str(row.get("endpoint") or ""),
        str(row.get("notes") or ""),
        " ".join(str(x) for x in (row.get("capabilities") or [])),
        " ".join(str(x) for x in (row.get("fetch_modes") or [])),
        " ".join(str(x) for x in (row.get("collect_via") or [])),
        " ".join(str(x) for x in (row.get("geographies") or [])),
    ]
    return " ".join(parts).lower()


def _score(query_tokens: set[str], row: dict[str, Any]) -> float:
    if not query_tokens:
        return 1.0
    blob = _blob(row)
    expanded = _expand_blob_tokens(blob)
    # Prefer whole-token hits in expanded set; keep substring fallback for short ids.
    hits = 0.0
    for t in query_tokens:
        if t in expanded:
            hits += 1.0
        elif t in blob:
            hits += 0.5
    return float(hits)


def _scope_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    doc = load_access_scope(repo_root)
    out: dict[str, dict[str, Any]] = {}
    for src in doc.get("sources") or []:
        sid = str(src.get("source_id") or "").strip()
        if sid:
            out[sid] = src
    return out


def _slug(value: str) -> str:
    from scripts.research_data_mcp.candidate_key import slugify_provider

    return slugify_provider(value)


def _normalize_source_row(
    src: dict[str, Any],
    *,
    desk: dict[str, dict[str, Any]],
    scope: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    source_id = str(src.get("id") or "").strip()
    if not source_id or source_id in _SKIP_SOURCE_IDS:
        return None
    access_mode = str(src.get("access_mode") or "").strip()
    if access_mode in _SKIP_ACCESS_MODES:
        return None

    desk_id = str(src.get("desk_connector_id") or "").strip()
    desk_row = desk.get(desk_id) or desk.get(source_id) or {}
    scope_row = scope.get(source_id) or {}

    provider = str(src.get("provider") or desk_row.get("label") or source_id).strip()
    label = str(src.get("label") or desk_row.get("label") or source_id).strip()
    connector_id = desk_id or (str(desk_row.get("id") or "").strip())

    row = {
        "kind": "source",
        "result_type": "source",
        "source_id": source_id,
        "provider": provider,
        "label": label,
        "title": label,
        "connector_id": connector_id or None,
        "desk_connector_id": connector_id or None,
        "access_mode": access_mode,
        "status": str(src.get("status") or "").strip() or None,
        "subscription_status": scope_row.get("subscription_status"),
        "license_holder": scope_row.get("license_holder"),
        "fetch_modes": list(scope_row.get("fetch_modes") or src.get("fetch_modes") or [])[:12],
        "capabilities": list(src.get("capabilities") or [])[:16],
        "geographies": list(src.get("geographies") or [])[:12],
        "collect_via": list(desk_row.get("collect_via") or [])[:8],
        "endpoint": str(desk_row.get("endpoint") or "").strip() or None,
        "mcp_routes": list(src.get("mcp_routes") or [])[:8],
        "known_gaps": list(src.get("known_gaps") or [])[:8],
        "notes": str(src.get("notes") or scope_row.get("notes") or "").strip()[:400] or None,
        "preview_supported": bool(
            connector_id or access_mode in {"live_connector", "materialized_bulk", "materialized_instant"}
        ),
        "live_search_supported": source_id in _LIVE_ADAPTERS or connector_id in _LIVE_ADAPTERS,
        "external_id": source_id,
        "source": provider,
        "availability": str(scope_row.get("subscription_status") or src.get("status") or "").strip() or None,
    }
    # Stable Explore identity — typed source:provider:id (never bare registry dataset ids).
    row["candidate_key"] = f"source:{_slug(provider)}:{source_id}"
    return {k: v for k, v in row.items() if v not in (None, "", [], {})}


def _normalize_connector_row(conn: dict[str, Any], *, matched_source_id: str = "") -> dict[str, Any]:
    cid = str(conn.get("id") or "").strip()
    label = str(conn.get("label") or cid).strip()
    row = {
        "kind": "connector",
        "result_type": "connector",
        "source_id": matched_source_id or cid,
        "connector_id": cid,
        "provider": label,
        "label": label,
        "title": label,
        "endpoint": str(conn.get("endpoint") or "").strip() or None,
        "collect_via": list(conn.get("collect_via") or [])[:8],
        "routes": str(conn.get("routes") or "").strip()[:240] or None,
        "layers": list(conn.get("layers") or [])[:8],
        "preview_supported": True,
        "live_search_supported": cid in _LIVE_ADAPTERS,
        "external_id": cid,
        "source": label,
    }
    row["candidate_key"] = f"source:{_slug(label)}:{cid}"
    return {k: v for k, v in row.items() if v not in (None, "", [], {})}


def _known_adapter_facts() -> list[dict[str, Any]]:
    """Catalog facts for adapters that already exist in-tree — not live search hits."""
    facts = [
        {
            "kind": "provider",
            "result_type": "provider",
            "source_id": "datacite",
            "provider": "DataCite",
            "label": "DataCite metadata + repository resolve",
            "title": "DataCite",
            "connector_id": "datacite",
            "access_mode": "live_connector",
            "status": "active",
            "subscription_status": "public",
            "fetch_modes": ["datacite_rest", "repository_resolve"],
            "capabilities": ["doi_metadata", "repository_files"],
            "mcp_routes": ["datacite_search", "datacite_resolve_repository"],
            "preview_supported": True,
            "live_search_supported": True,
            "adapter": "datacite_client",
            "external_id": "datacite",
            "source": "DataCite",
            "notes": (
                "Live search available via existing DataCite client; "
                "Explore catalog lists capability only unless live=1."
            ),
        },
        {
            "kind": "provider",
            "result_type": "provider",
            "source_id": "zenodo",
            "provider": "Zenodo",
            "label": "Zenodo repository adapter",
            "title": "Zenodo",
            "access_mode": "live_connector",
            "status": "active",
            "subscription_status": "public",
            "fetch_modes": ["zenodo_api"],
            "capabilities": ["repository_files"],
            "preview_supported": True,
            "live_search_supported": False,
            "adapter": "repository_adapters.zenodo_files",
            "external_id": "zenodo",
            "source": "Zenodo",
            "notes": "File resolve supported for landing URLs; not a registry dataset listing.",
        },
        {
            "kind": "provider",
            "result_type": "provider",
            "source_id": "huggingface",
            "provider": "Hugging Face",
            "label": "Hugging Face Hub datasets",
            "title": "Hugging Face",
            "connector_id": "huggingface",
            "access_mode": "live_connector",
            "status": "active",
            "subscription_status": "public",
            "fetch_modes": ["hf_hub_search"],
            "capabilities": ["dataset_cards"],
            "mcp_routes": ["huggingface_search"],
            "preview_supported": True,
            "live_search_supported": True,
            "adapter": "hf_loader",
            "external_id": "huggingface",
            "source": "Hugging Face",
        },
        {
            "kind": "provider",
            "result_type": "provider",
            "source_id": "openalex",
            "provider": "OpenAlex",
            "label": "OpenAlex works search",
            "title": "OpenAlex",
            "access_mode": "live_connector",
            "status": "active",
            "subscription_status": "public",
            "fetch_modes": ["openalex_api"],
            "capabilities": ["scholarly_works"],
            "preview_supported": False,
            "live_search_supported": False,
            "adapter": "web_search._search_openalex_api",
            "external_id": "openalex",
            "source": "OpenAlex",
            "notes": "Catalog fact only on Explore; not part of the bounded live=1 adapter set.",
        },
    ]
    for row in facts:
        row["candidate_key"] = f"source:{_slug(row['provider'])}:{row['source_id']}"
    return facts


def _explicit_connector_request(query: str, *, prefer: str = "") -> bool:
    """True only for connector-oriented requests — not merely matching a connector id."""
    prefer_l = str(prefer or "").strip().lower()
    if prefer_l in {"connector", "connectors", "desk_connector"}:
        return True
    q = str(query or "").strip().lower()
    if not q:
        return False
    if "connector" in q or "desk connector" in q:
        return True
    return False


def _capability_key(row: dict[str, Any]) -> str:
    """Collapse connector + source + provider representations of one capability."""
    cid = str(row.get("connector_id") or row.get("desk_connector_id") or "").strip().lower()
    if cid:
        return f"connector:{cid}"
    sid = str(row.get("source_id") or row.get("external_id") or "").strip().lower()
    if sid:
        return f"source:{sid}"
    return f"key:{row.get('candidate_key') or row.get('label') or id(row)}"


def _dedupe_best_per_capability(
    scored: list[tuple[float, dict[str, Any]]],
    *,
    keep_connectors: bool,
) -> list[tuple[float, dict[str, Any]]]:
    """Keep one best result per connector/provider capability.

    Default: prefer source > provider > connector (orphan connectors only).
    Explicit connector request: prefer connector for that capability.
    """
    kind_rank = (
        {"connector": 0, "source": 1, "provider": 2, "live_candidate": 3}
        if keep_connectors
        else _KIND_RANK
    )
    best: dict[str, tuple[float, dict[str, Any]]] = {}

    def _consider(score: float, row: dict[str, Any]) -> None:
        kind = str(row.get("kind") or "")
        key = _capability_key(row)
        prev = best.get(key)
        if prev is None:
            best[key] = (score, row)
            return
        prev_score, prev_row = prev
        prev_rank = kind_rank.get(str(prev_row.get("kind") or ""), 9)
        cur_rank = kind_rank.get(kind, 9)
        if cur_rank < prev_rank or (cur_rank == prev_rank and score > prev_score):
            best[key] = (score, row)
        elif cur_rank == prev_rank and score == prev_score:
            if str(row.get("source_id") or "") < str(prev_row.get("source_id") or ""):
                best[key] = (score, row)

    for score, row in scored:
        kind = str(row.get("kind") or "")
        if kind == "connector" and not keep_connectors:
            continue
        _consider(score, row)

    if not keep_connectors:
        occupied = set(best.keys())
        for score, row in scored:
            if str(row.get("kind") or "") != "connector":
                continue
            key = _capability_key(row)
            if key not in occupied:
                best[key] = (score, row)
                occupied.add(key)

    return list(best.values())


def _catalog_corpus(
    repo_root: Path,
    *,
    include_providers: bool = True,
) -> list[dict[str, Any]]:
    """All normalized source (+ optional provider) rows for catalog/semantic search."""
    source_map = load_source_map(repo_root)
    desk = load_desk_connectors(repo_root)
    scope = _scope_index(repo_root)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in source_map.get("sources") or []:
        if not isinstance(src, dict):
            continue
        row = _normalize_source_row(src, desk=desk, scope=scope)
        if not row:
            continue
        key = str(row.get("candidate_key") or "")
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    if include_providers:
        for row in _known_adapter_facts():
            key = str(row.get("candidate_key") or "")
            # Skip provider facts already covered by a source with same source_id/connector.
            if any(
                str(r.get("source_id") or "") == str(row.get("source_id") or "")
                or (
                    row.get("connector_id")
                    and str(r.get("connector_id") or "") == str(row.get("connector_id") or "")
                )
                for r in rows
            ):
                continue
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def _lexical_capability_search(
    corpus: list[dict[str, Any]],
    query: str,
    *,
    limit: int,
) -> list[tuple[float, dict[str, Any]]]:
    q_tokens = _expand_blob_tokens(query)
    if not q_tokens:
        return [(1.0, row) for row in corpus[:limit]]

    df: Counter[str] = Counter()
    docs_tokens: list[set[str]] = []
    for row in corpus:
        toks = _expand_blob_tokens(_blob(row))
        docs_tokens.append(toks)
        df.update(toks)

    n = max(len(corpus), 1)
    scored: list[tuple[float, dict[str, Any]]] = []
    for row, toks in zip(corpus, docs_tokens):
        score = 0.0
        for t in q_tokens:
            if t not in toks:
                continue
            idf = math.log(1.0 + n / (1.0 + df.get(t, 0)))
            # Capability / notes tokens weigh slightly higher when present as fields.
            cap_blob = " ".join(str(x) for x in (row.get("capabilities") or [])).lower()
            weight = 1.35 if t in _expand_blob_tokens(cap_blob) else 1.0
            score += idf * weight
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("label") or "")))
    return scored[:limit]


def _try_embedding_source_search(
    corpus: list[dict[str, Any]],
    query: str,
    *,
    limit: int,
) -> list[tuple[float, dict[str, Any]]] | None:
    """Reuse sentence-transformers when safely importable; else return None."""
    q = str(query or "").strip()
    if not q or not corpus:
        return None
    try:
        from scripts.research_data_mcp.semantic_index import (
            DEFAULT_EMBEDDING_MODEL,
            SemanticCatalogIndex,
        )
    except Exception:
        return None
    try:
        model = SemanticCatalogIndex._embedding_model_instance(DEFAULT_EMBEDDING_MODEL)
        texts = [_blob(row) for row in corpus]
        doc_vecs = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        q_vec = model.encode(
            q,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
    except Exception:
        return None

    ranked: list[tuple[float, dict[str, Any]]] = []
    for idx, row in enumerate(corpus):
        emb = doc_vecs[idx]
        score = float(sum(float(a) * float(b) for a, b in zip(q_vec, emb)))
        if score > 0.05:
            ranked.append((score, row))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("label") or "")))
    return ranked[:limit]


def semantic_search_discover_sources(
    repo_root: Path | str,
    query: str,
    *,
    limit: int = 24,
    prefer_embeddings: bool = True,
) -> dict[str, Any]:
    """Meaning-aware search over source/provider metadata — never registry datasets."""
    root = Path(repo_root).resolve()
    limit = max(1, min(int(limit or 24), 100))
    q = str(query or "").strip()
    corpus = _catalog_corpus(root, include_providers=True)
    mode = "lexical_capability_fallback"
    model_name = None
    scored: list[tuple[float, dict[str, Any]]] = []

    if prefer_embeddings:
        emb = _try_embedding_source_search(corpus, q, limit=limit * 2)
        if emb is not None:
            scored = emb
            mode = "semantic_embedding"
            try:
                from scripts.research_data_mcp.semantic_index import DEFAULT_EMBEDDING_MODEL

                model_name = DEFAULT_EMBEDDING_MODEL
            except Exception:
                model_name = "sentence-transformers"

    if not scored:
        scored = _lexical_capability_search(corpus, q, limit=limit * 2)
        mode = "lexical_capability_fallback"

    # Capability recall: domain-tagged queries must include matching catalog sources
    # even when base embedding/lexical retrieval missed them (e.g. blockchain ≠ onchain_crypto).
    domains = _detect_query_domains(q)
    if domains:
        by_id = {_row_stable_id(row): (float(score), row) for score, row in scored}
        for row in corpus:
            aff, _sig = _domain_capability_affinity(q, row, domains)
            if aff <= 0:
                continue
            rid = _row_stable_id(row)
            if rid not in by_id:
                # Neutral base score; hybrid affinity lifts true capability matches.
                by_id[rid] = (0.0, row)
        scored = list(by_id.values())

    # Hybrid rerank: blend base similarity with lexical + capability/domain signals.
    base_mode = mode
    hybrid_scored, hybrid_mode = _hybrid_rerank_sources(
        scored,
        q,
        corpus=corpus,
        base_mode=base_mode,
    )
    mode = hybrid_mode if hybrid_scored else mode
    scored = hybrid_scored or scored

    # Dedupe to source-level capability winners (no connector spam).
    deduped = _dedupe_best_per_capability(scored, keep_connectors=False)
    deduped.sort(key=lambda item: (-item[0], str(item[1].get("label") or "")))
    results = [with_candidate_key(dict(row)) or row for _, row in deduped[:limit]]
    results = stamp_rows(results)
    for row in results:
        row["match_mode"] = mode
        if str(row.get("kind") or "") in {"local_registry", "registry_dataset", "dataset"}:
            row["kind"] = "source"
            row["result_type"] = "source"

    return {
        "query": q,
        "result_kind": "source",
        "search_mode": mode,
        "ranking": {
            "rule": "hybrid_capability",
            "formula": "0.30*base_norm + 0.15*lexical_norm + 0.55*affinity_norm + 0.12*affinity_raw - 0.18*domain_irrelevant",
            "domains": sorted(_detect_query_domains(q)),
            "base_mode": base_mode,
        },
        "embedding_model": model_name,
        "results": results,
        "total": len(results),
        "sources_tried": ["databank_source_map", "desk_sources", "access_scope", "known_adapters"],
        "remote_search": {
            "attempted": False,
            "reason": "Semantic/lexical source search uses local source metadata only.",
        },
        "excludes": {
            "registry_datasets": True,
            "derived_internal": True,
            "local_scrape_artifacts": True,
        },
    }


def _normalize_live_candidate(
    *,
    provider: str,
    title: str,
    url: str = "",
    doi: str = "",
    external_id: str = "",
    capabilities: list[str] | None = None,
    availability: str = "",
    notes: str = "",
) -> dict[str, Any]:
    provider = str(provider or "").strip() or "unknown"
    title = str(title or external_id or doi or url or "untitled").strip()
    external_id = str(external_id or doi or "").strip()
    doi_n = str(doi or "").strip()
    url_n = str(url or "").strip()
    if doi_n:
        ck = f"doi:{doi_n.lower()}"
    elif external_id:
        ck = f"source:{_slug(provider)}:{external_id}"
    elif url_n:
        from scripts.research_data_mcp.candidate_key import canonicalize_url

        ck = f"url:{canonicalize_url(url_n)}"
    else:
        ck = f"title:{_slug(provider)}:{_slug(title)}"
    row = {
        "kind": "live_candidate",
        "result_type": "source",
        "provider": provider,
        "label": title,
        "title": title,
        "url": url_n or None,
        "doi": doi_n or None,
        "external_id": external_id or None,
        "source_id": None,
        "connector_id": _slug(provider) if _slug(provider) in _LIVE_ADAPTERS else None,
        "capabilities": list(capabilities or [])[:12],
        "availability": availability or "remote_live",
        "preview_supported": bool(url_n or doi_n),
        "live_search_supported": True,
        "live_hit": True,
        "notes": (notes or "")[:400] or None,
        "candidate_key": ck,
        "source": provider,
    }
    return {k: v for k, v in row.items() if v not in (None, "", [], {})}


def _live_search_huggingface(query: str, *, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"adapter": "huggingface", "ok": False, "error": None, "returned": 0}
    try:
        from scripts.research_data_mcp.hf_catalog import search_datasets

        payload = search_datasets(query, limit=limit, timeout=_LIVE_TIMEOUT_SEC)
    except Exception as exc:  # noqa: BLE001 — non-fatal live adapter failure
        meta["error"] = str(exc)[:300]
        return [], meta
    if not isinstance(payload, dict):
        meta["error"] = "huggingface returned non-object"
        return [], meta
    if payload.get("error"):
        meta["error"] = str(payload.get("error"))[:300]
        # Still accept any rows if present.
    rows_out: list[dict[str, Any]] = []
    for raw in payload.get("rows") or []:
        if not isinstance(raw, dict):
            continue
        rows_out.append(
            _normalize_live_candidate(
                provider="Hugging Face",
                title=str(raw.get("title") or raw.get("id") or ""),
                url=str(raw.get("url") or ""),
                external_id=str(raw.get("id") or ""),
                capabilities=["dataset_cards"] + [str(t) for t in (raw.get("tags") or [])[:6]],
                availability="public_hub",
                notes=str(raw.get("load_hint") or "")[:200],
            )
        )
    meta["ok"] = meta.get("error") is None
    meta["returned"] = len(rows_out)
    return rows_out, meta


def _live_search_datacite(query: str, *, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"adapter": "datacite", "ok": False, "error": None, "returned": 0}
    try:
        from scripts.research_data_mcp.datacite_client import search as datacite_search

        payload = datacite_search(query=query, page_size=limit, timeout=_LIVE_TIMEOUT_SEC)
    except Exception as exc:  # noqa: BLE001
        meta["error"] = str(exc)[:300]
        return [], meta
    if not isinstance(payload, dict):
        meta["error"] = "datacite returned non-object"
        return [], meta
    rows_out: list[dict[str, Any]] = []
    for raw in payload.get("rows") or []:
        if not isinstance(raw, dict):
            continue
        doi = str(raw.get("doi") or "").strip()
        rows_out.append(
            _normalize_live_candidate(
                provider="DataCite",
                title=str(raw.get("title") or doi or ""),
                url=str(raw.get("url") or (f"https://doi.org/{doi}" if doi else "")),
                doi=doi,
                external_id=doi,
                capabilities=["doi_metadata"]
                + ([str(raw.get("resource_type"))] if raw.get("resource_type") else []),
                availability="public_datacite",
                notes=str(raw.get("description") or raw.get("publisher") or "")[:200],
            )
        )
    meta["ok"] = True
    meta["returned"] = len(rows_out)
    return rows_out, meta


def _run_live_adapters(query: str, *, per_adapter: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Bounded live search via already-implemented HF + DataCite adapters only."""
    q = str(query or "").strip()
    if not q:
        return [], [
            {
                "adapter": "huggingface",
                "ok": False,
                "error": "empty query",
                "returned": 0,
            },
            {
                "adapter": "datacite",
                "ok": False,
                "error": "empty query",
                "returned": 0,
            },
        ]
    per_adapter = max(1, min(int(per_adapter or _LIVE_PER_ADAPTER_CAP), _LIVE_PER_ADAPTER_CAP))
    hits: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for fn in (_live_search_huggingface, _live_search_datacite):
        rows, meta = fn(q, limit=per_adapter)
        reports.append(meta)
        hits.extend(rows)
    return hits, reports


def search_discover_sources(
    repo_root: Path | str,
    query: str = "",
    *,
    limit: int = 24,
    include_providers: bool = True,
    include_connectors: bool = True,
    live: bool = False,
    semantic: bool = False,
    prefer: str = "",
    prefer_embeddings: bool = True,
) -> dict[str, Any]:
    """Return normalized Explore results from known source/provider/connector facts.

    Default is fast catalog-only with source-level capability dedupe.
    Optional live=1 federates Hugging Face + DataCite only.
    Optional semantic=1 runs embedding/lexical meaning search over source metadata.
    """
    if semantic:
        out = semantic_search_discover_sources(
            repo_root,
            query,
            limit=limit,
            prefer_embeddings=prefer_embeddings,
        )
        if live:
            live_hits, live_reports = _run_live_adapters(query, per_adapter=_LIVE_PER_ADAPTER_CAP)
            # Append live candidates without displacing catalog semantic hits.
            lim = max(1, min(int(limit or 24), 100))
            existing = {str(r.get("candidate_key") or "") for r in out["results"]}
            merged = list(out["results"])
            remaining = max(0, lim - len(merged))
            diversified = _diversify_live_hits(live_hits, limit=remaining or lim)
            for row in diversified:
                key = str(row.get("candidate_key") or "")
                if key and key in existing:
                    continue
                merged.append(with_candidate_key(row) or row)
                if key:
                    existing.add(key)
                if len(merged) >= lim:
                    break
            out["results"] = stamp_rows(merged[:lim])
            out["total"] = len(out["results"])
            out["remote_search"] = {
                "attempted": True,
                "adapters": live_reports,
                "reason": None,
                "diversification": {
                    "rule": "round_robin_provider_soft_cap",
                    "soft_cap": "ceil(limit / n_providers_with_hits)",
                },
            }
            out["sources_tried"] = list(out.get("sources_tried") or []) + ["live:huggingface", "live:datacite"]
        return out

    root = Path(repo_root).resolve()
    limit = max(1, min(int(limit or 24), 100))
    q = str(query or "").strip()
    q_tokens = _tokens(q)
    keep_connectors = _explicit_connector_request(q, prefer=prefer)
    # "connector" is a request modifier, not a catalog term (avoids matching live_connector).
    score_tokens = set(q_tokens)
    if keep_connectors:
        score_tokens -= {"connector", "connectors", "desk"}

    source_map = load_source_map(root)
    desk = load_desk_connectors(root)
    scope = _scope_index(root)

    sources_tried = ["databank_source_map", "desk_sources", "access_scope"]
    if include_providers:
        sources_tried.append("known_adapters")

    scored: list[tuple[float, dict[str, Any]]] = []
    seen_keys: set[str] = set()

    for src in source_map.get("sources") or []:
        if not isinstance(src, dict):
            continue
        row = _normalize_source_row(src, desk=desk, scope=scope)
        if not row:
            continue
        score = _score(score_tokens, {**src, **row})
        if score_tokens and score <= 0:
            continue
        key = str(row.get("candidate_key") or "")
        if key in seen_keys:
            continue
        seen_keys.add(key)
        scored.append((score, row))

    if include_connectors:
        linked_ids = {
            str(s.get("desk_connector_id") or "").strip()
            for s in (source_map.get("sources") or [])
            if isinstance(s, dict) and str(s.get("desk_connector_id") or "").strip()
        }
        for cid, conn in desk.items():
            if cid in linked_ids and not keep_connectors:
                # Linked connectors are represented by their source row by default.
                continue
            score = _score(score_tokens, conn)
            if score_tokens and score <= 0:
                continue
            matched = ""
            for s in source_map.get("sources") or []:
                if str(s.get("desk_connector_id") or "") == cid:
                    matched = str(s.get("id") or "")
                    break
            row = _normalize_connector_row(conn, matched_source_id=matched)
            key = str(row.get("candidate_key") or "")
            if key in seen_keys:
                continue
            seen_keys.add(key)
            scored.append((score + 0.05, row))

    if include_providers:
        for row in _known_adapter_facts():
            score = _score(score_tokens, row)
            if score_tokens and score <= 0:
                continue
            key = str(row.get("candidate_key") or "")
            if key in seen_keys:
                continue
            # Skip provider catalog facts already covered by a source with same ids.
            covered = any(
                (
                    str(srow.get("source_id") or "") == str(row.get("source_id") or "")
                    or (
                        row.get("connector_id")
                        and str(srow.get("connector_id") or "") == str(row.get("connector_id") or "")
                    )
                )
                and str(srow.get("kind") or "") == "source"
                for _, srow in scored
            )
            if covered:
                continue
            seen_keys.add(key)
            scored.append((score + 0.02, row))

    deduped = _dedupe_best_per_capability(scored, keep_connectors=keep_connectors)
    deduped.sort(key=lambda item: (-item[0], str(item[1].get("label") or "")))
    results = [with_candidate_key(row) or row for _, row in deduped[:limit]]

    remote_search: dict[str, Any] = {
        "attempted": False,
        "reason": (
            "Explore source-search returns known provider/connector/catalog facts only; "
            "pass live=1 for bounded Hugging Face + DataCite adapters."
        ),
    }
    if live:
        live_hits, live_reports = _run_live_adapters(q, per_adapter=_LIVE_PER_ADAPTER_CAP)
        sources_tried.extend(["live:huggingface", "live:datacite"])
        remote_search = {
            "attempted": True,
            "adapters": live_reports,
            "reason": None,
            "diversification": {
                "rule": "round_robin_provider_soft_cap",
                "soft_cap": "ceil(limit / n_providers_with_hits)",
            },
        }
        existing = {str(r.get("candidate_key") or "") for r in results}
        remaining = max(0, limit - len(results))
        # When catalog is empty, diversify across the full limit; otherwise fill remainder fairly.
        diversified = _diversify_live_hits(live_hits, limit=remaining if remaining > 0 else limit)
        for row in diversified:
            key = str(row.get("candidate_key") or "")
            if key and key in existing:
                continue
            results.append(with_candidate_key(row) or row)
            if key:
                existing.add(key)
            if len(results) >= limit:
                break

    results = stamp_rows(results[:limit])

    # Guard: never return registry dataset default kind.
    for row in results:
        if str(row.get("kind") or "") in {"local_registry", "registry_dataset", "dataset"}:
            row["kind"] = "source"
            row["result_type"] = "source"

    return {
        "query": q,
        "result_kind": "source",
        "search_mode": "catalog",
        "results": results,
        "total": len(results),
        "sources_tried": sources_tried,
        "remote_search": remote_search,
        "excludes": {
            "registry_datasets": True,
            "derived_internal": True,
            "local_scrape_artifacts": True,
        },
        "dedupe": {
            "per_capability": True,
            "prefer_kind": "source",
            "connectors_only_when_orphan_or_explicit": True,
            "explicit_connector_request": keep_connectors,
        },
    }
