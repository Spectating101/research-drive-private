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
from scripts.research_data_mcp.discover_source_contract import finalize_discover_rows
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


# Meaningful geography / country codes retained as query terms (not generic filler).
_SOURCE_GEO_CODES = frozenset(
    {
        "us",
        "usa",
        "uk",
        "eu",
        "cn",
        "jp",
        "tw",
        "kr",
        "au",
        "ca",
        "nz",
        "de",
        "fr",
        "ie",
        "sg",
        "hk",
        "id",
        "vn",
        "ph",
        "my",
        "th",
    }
)
_SOURCE_GEO_ALIASES: dict[str, frozenset[str]] = {
    "us": frozenset({"us", "usa", "america", "american", "americans"}),
    "usa": frozenset({"us", "usa", "america", "american", "americans"}),
    "uk": frozenset({"uk", "britain", "british", "england", "english"}),
    "eu": frozenset({"eu", "europe", "european"}),
    "tw": frozenset({"tw", "taiwan", "taiwanese"}),
    "taiwan": frozenset({"tw", "taiwan", "taiwanese"}),
    "cn": frozenset({"cn", "china", "chinese"}),
    "jp": frozenset({"jp", "japan", "japanese"}),
    "ie": frozenset({"ie", "ireland", "irish"}),
}
_SOURCE_GEO_NAME_TOKENS = frozenset(
    a for aliases in _SOURCE_GEO_ALIASES.values() for a in aliases
) | frozenset(
    {
        "america",
        "american",
        "britain",
        "british",
        "europe",
        "european",
        "ireland",
        "irish",
        "china",
        "japan",
        "taiwan",
        "taiwanese",
        "korea",
        "australia",
        "canada",
    }
)

# Generic tokens that alone must not make a source look relevant (e.g. bare "data").
_SOURCE_GENERIC_TOKENS = frozenset(
    {
        "dataset",
        "datasets",
        "data",
        "panel",
        "research",
        "study",
        "metadata",
        "graph",
        "source",
        "sources",
        "catalog",
        "catalogue",
        "public",
        "open",
        "api",
        "feed",
        "feeds",
        "file",
        "files",
        "bulk",
        "instant",
        "live",
        "global",
        "world",
        "daily",
        "monthly",
        "annual",
        "year",
        "time",
        "series",
        "history",
        "historical",
        "index",
        "incident",
        "incidents",
    }
)

# Finance / market providers that must not satisfy non-finance topic queries (e.g. polling).
_FINANCE_PROVIDER_SOURCE_IDS = frozenset(
    {
        "lseg_edp",
        "lseg_desktop_rescue",
        "capital_iq_compustat",
        "wrds_crsp_compustat",
        "crsp_moveit",
        "yfinance_public",
    }
)
_FINANCE_CAPABILITIES = frozenset(
    {
        "daily_prices",
        "fundamentals",
        "estimates_revisions",
        "index_pit_survivorship",
        "risk_overlay",
    }
)
_NEWS_CAPABILITIES = frozenset(
    {"country_news_shocks", "entity_news_shocks", "entity_join_gdelt_ric"}
)
_POLLING_TOPIC_TOKENS = frozenset(
    {"poll", "polls", "polling", "pollster", "election", "elections", "opinion", "survey", "surveys"}
)

# Deterministic concept → catalog evidence. Never invents access or collection success.
_SUPPORTED_CONCEPTS: tuple[dict[str, Any], ...] = (
    {
        "id": "mops_taiwan_governance",
        "label": "MOPS Taiwan governance / disclosures",
        "match_any": frozenset({"mops"}),
        "match_all_groups": (
            frozenset({"taiwan", "taiwanese", "tw"}),
            frozenset({"governance", "regulatory", "disclosure", "disclosures", "filing", "filings"}),
        ),
        "capabilities": _GOVERNANCE_CAPABILITIES,
        "source_ids": frozenset({"mops_taiwan", "twse_official"}),
        "cue_tokens": frozenset({"mops", "taiwan", "twse", "governance", "regulatory", "disclosure"}),
        "conflict_tokens": frozenset(),
        "domains": frozenset({"governance"}),
    },
    {
        "id": "gdelt_news",
        "label": "GDELT news shocks",
        "match_any": frozenset({"gdelt"}),
        "match_all_groups": (
            frozenset({"gdelt"}),
            frozenset({"news", "gkg", "shock", "shocks"}),
        ),
        "capabilities": _NEWS_CAPABILITIES,
        "source_ids": frozenset({"gdelt"}),
        "cue_tokens": frozenset({"gdelt", "news", "gkg", "shock", "shocks"}),
        "conflict_tokens": frozenset(),
        "domains": frozenset({"news"}),
    },
    {
        "id": "stablecoin_onchain_transactions",
        "label": "Historical stablecoin / on-chain transactions",
        "match_any": frozenset({"stablecoin", "stablecoins", "usdt", "usdc"}),
        "match_all_groups": (
            frozenset({"onchain", "on-chain", "blockchain", "ethereum", "crypto", "cryptocurrency"}),
            frozenset({"transaction", "transactions", "transfer", "transfers", "stablecoin", "stablecoins"}),
        ),
        "capabilities": _ONCHAIN_CAPABILITIES,
        "source_ids": frozenset({"ethereum_onchain", "bigquery_public", "coingecko"}),
        "cue_tokens": frozenset(
            {"stablecoin", "stablecoins", "usdt", "usdc", "ethereum", "bigquery", "onchain", "crypto", "coingecko"}
        ),
        "conflict_tokens": frozenset({"nft", "opensea"}),
        "domains": frozenset({"onchain"}),
    },
    {
        "id": "sec_edgar_governance",
        "label": "SEC EDGAR filings / US governance disclosures",
        "match_any": frozenset({"edgar"}),
        "match_all_groups": (
            frozenset({"sec"}),
            frozenset({"edgar", "filing", "filings", "disclosure", "disclosures", "governance"}),
        ),
        "capabilities": _GOVERNANCE_CAPABILITIES,
        "source_ids": frozenset({"sec_edgar"}),
        "cue_tokens": frozenset({"sec", "edgar", "filing", "filings", "governance"}),
        "conflict_tokens": frozenset(),
        "domains": frozenset({"governance"}),
    },
)


def _distinctive_query_tokens(query: str) -> set[str]:
    """Query tokens that can establish credible source relevance."""
    return {
        t
        for t in _expand_blob_tokens(query)
        if t not in _SOURCE_GENERIC_TOKENS and (len(t) > 2 or t in _SOURCE_GEO_CODES)
    }


def _source_query_aspects(query: str) -> dict[str, set[str]]:
    distinctive = _distinctive_query_tokens(query)
    geography: set[str] = set()
    topic: set[str] = set()
    for tok in distinctive:
        if tok in _SOURCE_GEO_CODES or tok in _SOURCE_GEO_NAME_TOKENS:
            geography |= set(_SOURCE_GEO_ALIASES.get(tok, {tok}))
            geography.add(tok)
        else:
            topic.add(tok)
    return {"geography": geography, "topic": topic}


def detect_supported_concepts(query: str) -> list[dict[str, Any]]:
    """Map a query onto catalog-backed concepts (capability/source evidence only)."""
    q = str(query or "").strip().lower()
    if not q:
        return []
    toks = _expand_blob_tokens(q)
    if "on-chain" in q:
        toks = set(toks) | {"onchain", "on-chain"}
    if "stable coin" in q or "stable coins" in q:
        toks = set(toks) | {"stablecoin", "stablecoins"}
    matched: list[dict[str, Any]] = []
    for concept in _SUPPORTED_CONCEPTS:
        if toks & set(concept["match_any"]):
            matched.append(concept)
            continue
        groups = concept.get("match_all_groups") or ()
        if groups and all(toks & set(group) for group in groups):
            matched.append(concept)
    return matched


def source_query_relevance(row: dict[str, Any], query: str) -> float:
    """Distinctive aspect/token overlap between query and source metadata (deterministic)."""
    aspects = _source_query_aspects(query)
    geography = aspects.get("geography") or set()
    topic = aspects.get("topic") or set()
    if not geography and not topic:
        return 0.0
    blob = _expand_blob_tokens(_blob(row))
    score = 0.0
    if geography:
        if geography & blob:
            score += 1.0
        else:
            return 0.0
    topic_hits = float(sum(1.0 for t in topic if t in blob))
    if topic and topic_hits <= 0:
        return 0.0
    score += topic_hits
    return float(score)


def source_evidence_score(row: dict[str, Any], query: str) -> tuple[float, dict[str, Any]]:
    """Evidence for presenting a catalog/live row as a Discover candidate.

    Accepts only:
      - explicit capability/concept matches from databank_source_map, or
      - distinctive non-generic token overlap (geo+topic when both present).
    Rejects weak lexical coincidences (e.g. US geography alone → LSEG for polling).
    Never invents coverage, access, or collection capability.
    """
    q = str(query or "").strip()
    if not q:
        return 0.0, {"evidence": [], "reject_reason": "empty_query"}

    concepts = detect_supported_concepts(q)
    aspects = _source_query_aspects(q)
    topic = aspects.get("topic") or set()
    caps = _row_caps(row)
    blob = _expand_blob_tokens(_blob(row))
    sid = str(row.get("source_id") or row.get("external_id") or "").strip().lower()
    kind = str(row.get("kind") or "").strip().lower()
    evidence: list[dict[str, Any]] = []
    score = 0.0

    # Live / unknown external hits are inspect-only; keep only with distinctive overlap.
    if kind == "live_candidate" or bool(row.get("live_hit")):
        lex = source_query_relevance(row, q)
        if lex <= 0:
            return 0.0, {
                "evidence": [],
                "reject_reason": "live_without_distinctive_overlap",
                "inspect_only": True,
            }
        return lex, {
            "evidence": [{"type": "distinctive_token_overlap", "score": round(lex, 2)}],
            "inspect_only": True,
            "trust_tier": "inspect_only",
        }

    for concept in concepts:
        cap_hit = caps & set(concept["capabilities"])
        preferred = sid in set(concept["source_ids"])
        cue_hits = sorted(set(concept["cue_tokens"]) & blob)
        conflicts = sorted(set(concept.get("conflict_tokens") or set()) & blob)
        # Specialty conflict without cue/preferred (e.g. NFT source for stablecoin query).
        if conflicts and not preferred and not (
            set(concept["cue_tokens"])
            & blob
            & {"stablecoin", "stablecoins", "usdt", "usdc", "ethereum", "bigquery"}
        ):
            continue
        # Geography-bound concepts (Taiwan MOPS) must not promote other governance seats.
        if concept["id"] == "mops_taiwan_governance" and not preferred:
            if not (blob & {"taiwan", "taiwanese", "tw", "mops", "twse"}):
                continue
        if concept["id"] == "sec_edgar_governance" and not preferred:
            if not (blob & {"sec", "edgar"}):
                continue
        if preferred and cap_hit:
            score += 2.0
            evidence.append(
                {
                    "type": "preferred_source_capability",
                    "concept": concept["id"],
                    "capabilities": sorted(cap_hit),
                }
            )
        elif cap_hit and cue_hits:
            score += 1.75
            evidence.append(
                {
                    "type": "capability_cue_match",
                    "concept": concept["id"],
                    "capabilities": sorted(cap_hit),
                    "cues": cue_hits,
                }
            )
        elif preferred:
            score += 1.25
            evidence.append({"type": "preferred_source", "concept": concept["id"]})
        elif cap_hit and not conflicts:
            # Capability alone is enough for broad concept queries (stablecoin → onchain_crypto).
            score += 1.5
            evidence.append(
                {
                    "type": "capability_match",
                    "concept": concept["id"],
                    "capabilities": sorted(cap_hit),
                }
            )

    lex = source_query_relevance(row, q)
    if lex > 0:
        score += lex
        evidence.append({"type": "distinctive_token_overlap", "score": round(lex, 2)})

    # Polling / opinion queries: finance providers are never direct candidates.
    if topic & _POLLING_TOPIC_TOKENS:
        finance_row = sid in _FINANCE_PROVIDER_SOURCE_IDS or bool(caps & _FINANCE_CAPABILITIES)
        if finance_row and not (caps & (_GOVERNANCE_CAPABILITIES | _NEWS_CAPABILITIES | _ONCHAIN_CAPABILITIES)):
            return 0.0, {
                "evidence": [],
                "reject_reason": "finance_provider_for_polling_query",
            }
        # Even governance/news rows need polling topic evidence — catalog has none today.
        if not any(t in blob for t in (topic & _POLLING_TOPIC_TOKENS)):
            if not evidence or all(e.get("type") == "distinctive_token_overlap" for e in evidence):
                # Geography-only or generic finance/news coincidence.
                if lex < 2.0:
                    return 0.0, {
                        "evidence": [],
                        "reject_reason": "no_polling_capability_or_topic_evidence",
                    }

    if score <= 0:
        return 0.0, {"evidence": [], "reject_reason": "no_capability_or_distinctive_evidence"}

    return float(score), {"evidence": evidence, "inspect_only": False}


def min_source_evidence(query: str) -> float:
    """Minimum evidence score before a row may be presented as a direct candidate."""
    if detect_supported_concepts(query):
        return 1.25
    aspects = _source_query_aspects(query)
    n = int(bool(aspects.get("geography"))) + int(bool(aspects.get("topic")))
    if n >= 2:
        return 2.0
    if n >= 1:
        return 1.0
    return 1.0


def build_source_groups(
    query: str,
    *,
    corpus: list[dict[str, Any]] | None = None,
    kept_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Honest concept groups from catalog evidence — not invented coverage claims."""
    qtoks = _expand_blob_tokens(query)
    concepts = list(detect_supported_concepts(query))
    concept_ids = {c["id"] for c in concepts}
    # Event-like stablecoin queries: offer GDELT as a related news alternative only.
    if (
        qtoks & {"incident", "incidents"}
        and qtoks & {"stablecoin", "stablecoins", "crypto", "onchain"}
        and "gdelt_news" not in concept_ids
    ):
        for c in _SUPPORTED_CONCEPTS:
            if c["id"] == "gdelt_news":
                concepts.append(c)
                break
    if not concepts:
        return []

    by_id = {
        str(r.get("source_id") or "").strip().lower(): r
        for r in (corpus or [])
        if str(r.get("source_id") or "").strip()
    }
    kept_ids = {
        str(r.get("source_id") or "").strip().lower()
        for r in (kept_rows or [])
        if str(r.get("source_id") or "").strip()
    }
    groups: list[dict[str, Any]] = []
    for concept in concepts:
        member_ids = sorted(set(concept["source_ids"]) & set(by_id))
        if not member_ids and concept["id"] == "gdelt_news" and "gdelt" in by_id:
            member_ids = ["gdelt"]
        if not member_ids:
            continue
        role = "direct"
        notes = (
            f"Catalog capabilities {sorted(concept['capabilities'])}; "
            "does not assert live access or successful collection."
        )
        if concept["id"] == "gdelt_news" and (qtoks & {"incident", "incidents"}) and (
            qtoks & {"stablecoin", "stablecoins", "crypto", "onchain"}
        ):
            role = "alternative"
            notes = (
                "GDELT news-shock panels are a related alternative for event-like queries; "
                "not a curated stablecoin incident ledger."
            )
        if concept["id"] == "stablecoin_onchain_transactions" and (qtoks & {"incident", "incidents"}):
            notes = (
                "onchain_crypto covers stablecoin/on-chain transfers telemetry. "
                "No dedicated incidents capability is declared on these sources."
            )
        groups.append(
            {
                "concept_id": concept["id"],
                "label": concept["label"],
                "role": role,
                "supported": True,
                "capabilities": sorted(concept["capabilities"]),
                "source_ids": member_ids,
                "candidate_keys": [
                    str((by_id[sid] or {}).get("candidate_key") or "")
                    for sid in member_ids
                    if (by_id.get(sid) or {}).get("candidate_key")
                ],
                "in_results": sorted(sid for sid in member_ids if sid in kept_ids),
                "notes": notes,
            }
        )
    return groups


def apply_source_relevance_gate(
    rows: list[dict[str, Any]],
    query: str,
    *,
    limit: int | None = None,
    corpus: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filter weak matches; annotate evidence; emit concept groups / no-supported-route."""
    q = str(query or "").strip()
    threshold = min_source_evidence(q)
    distinctive = sorted(_distinctive_query_tokens(q))
    concepts = detect_supported_concepts(q)
    annotated: list[dict[str, Any]] = []
    rejected = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        out = dict(row)
        rel, meta = source_evidence_score(out, q)
        out["query_relevance"] = round(float(rel), 2)
        out["relevance_evidence"] = list(meta.get("evidence") or [])
        if meta.get("inspect_only"):
            out["inspect_only"] = True
            out["trust_tier"] = "inspect_only"
            # Search hits must not imply desk access/collection readiness.
            out.pop("access_mode", None)
            out.pop("subscription_status", None)
        if rel >= threshold:
            annotated.append(out)
        else:
            rejected += 1

    annotated.sort(
        key=lambda r: (
            -float(r.get("query_relevance") or 0),
            -float((r.get("rank_signals") or {}).get("hybrid_score") or r.get("score") or 0),
            str(r.get("label") or r.get("source_id") or ""),
        )
    )
    if not distinctive and not concepts:
        kept: list[dict[str, Any]] = []
    else:
        kept = list(annotated)

    if limit is not None:
        kept = kept[: max(1, int(limit))] if kept else []

    groups = build_source_groups(q, corpus=corpus, kept_rows=kept)
    # Related alternatives when direct candidates empty but concept family exists.
    alternatives: list[dict[str, Any]] = []
    if not kept:
        for group in groups:
            alternatives.append(
                {
                    "concept_id": group["concept_id"],
                    "label": group["label"],
                    "source_ids": group["source_ids"],
                    "role": group.get("role") or "alternative",
                    "notes": group.get("notes"),
                }
            )
        # If polling-like with no catalog concept, do not invent finance alternatives.
        qtoks = _expand_blob_tokens(q)
        if (qtoks & _POLLING_TOPIC_TOKENS) and not concepts:
            groups = []
            alternatives = []

    no_supported_route = bool(q) and not kept
    # When we have empty direct results but catalog concept alternatives, still flag miss.
    if no_supported_route and alternatives:
        # Stablecoin incidents: prefer surfacing evidence-backed onchain rows when present in corpus.
        # Rehydrate preferred concept members as candidates when evidence exists in corpus.
        rehydrated: list[dict[str, Any]] = []
        for group in groups:
            if group.get("role") == "alternative":
                continue
            for sid in group.get("source_ids") or []:
                row = next(
                    (
                        r
                        for r in (corpus or [])
                        if str(r.get("source_id") or "").strip().lower() == sid
                    ),
                    None,
                )
                if not row:
                    continue
                rel, meta = source_evidence_score(row, q)
                if rel < threshold:
                    continue
                item = dict(row)
                item["query_relevance"] = round(float(rel), 2)
                item["relevance_evidence"] = list(meta.get("evidence") or [])
                rehydrated.append(item)
        if rehydrated:
            rehydrated.sort(
                key=lambda r: (
                    -float(r.get("query_relevance") or 0),
                    str(r.get("source_id") or ""),
                )
            )
            kept = rehydrated[: max(1, int(limit or len(rehydrated)))]
            no_supported_route = False
            alternatives = [g for g in groups if g.get("role") == "alternative"]
            groups = build_source_groups(q, corpus=corpus, kept_rows=kept)

    meta = {
        "relevance_gate": "capability_or_distinctive_evidence",
        "distinctive_tokens": distinctive,
        "concepts": [c["id"] for c in concepts],
        "min_query_relevance": threshold,
        "candidates_before_gate": len(rows),
        "candidates_after_gate": len(kept),
        "rejected_weak_matches": rejected,
        "source_groups": groups,
        "no_supported_route": no_supported_route,
        "alternatives": alternatives if no_supported_route else [g for g in groups if g.get("role") == "alternative"],
    }
    return kept, meta


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
        toks
        & {
            "blockchain",
            "ethereum",
            "crypto",
            "cryptocurrency",
            "onchain",
            "stablecoin",
            "stablecoins",
            "web3",
            "defi",
            "token",
            "tokens",
        }
        or "on-chain" in q
    ):
        domains.add("onchain")
    if toks & {
        "edgar",
        "sec",
        "mops",
        "governance",
        "regulatory",
        "filing",
        "filings",
        "disclosure",
        "disclosures",
    }:
        domains.add("governance")
    if toks & {"gdelt", "news", "gkg"} or "news shock" in q:
        domains.add("news")
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
        stablecoin_query = bool(q_toks & {"stablecoin", "stablecoins", "usdt", "usdc"})
        nft_specialty = bool(blob_toks & {"nft", "opensea"}) and not bool(
            blob_toks & {"stablecoin", "stablecoins", "usdt", "usdc", "ethereum", "bigquery"}
        )
        if onchain_cap and not (stablecoin_query and nft_specialty):
            score += 1.15
            signals["capability_match"] = sorted(caps & _ONCHAIN_CAPABILITIES)
        elif onchain_meta and not (stablecoin_query and nft_specialty):
            score += 0.55
            signals["metadata_onchain_hint"] = True
        if stablecoin_query and nft_specialty:
            score -= 0.85
            signals["domain_mismatch"] = "nft_specialty_for_stablecoin_query"
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

    if "news" in domains and not ("onchain" in domains):
        if caps & _NEWS_CAPABILITIES:
            score += 0.9
            signals["capability_match"] = sorted(caps & _NEWS_CAPABILITIES)

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
    # Wider pool before relevance gate so weak embedding heads can be dropped.
    pre_gate = [with_candidate_key(dict(row)) or row for _, row in deduped[: max(limit * 3, limit)]]
    results, gate_meta = apply_source_relevance_gate(pre_gate, q, limit=limit, corpus=corpus)
    results = finalize_discover_rows(stamp_rows(results))
    for row in results:
        row["match_mode"] = mode
        if str(row.get("kind") or "") in {"local_registry", "registry_dataset", "dataset"}:
            row["kind"] = "source"
            row["result_type"] = "source"

    relevance_miss = bool(q) and not results
    return {
        "query": q,
        "result_kind": "source",
        "search_mode": mode,
        "ranking": {
            "rule": "hybrid_capability",
            "formula": "0.30*base_norm + 0.15*lexical_norm + 0.55*affinity_norm + 0.12*affinity_raw - 0.18*domain_irrelevant",
            "domains": sorted(_detect_query_domains(q)),
            "base_mode": base_mode,
            **gate_meta,
        },
        "embedding_model": model_name,
        "results": results,
        "total": len(results),
        "index_miss": relevance_miss,
        "relevance_miss": relevance_miss,
        "weak_match": relevance_miss,
        "no_supported_route": bool(gate_meta.get("no_supported_route")),
        "source_groups": list(gate_meta.get("source_groups") or []),
        "alternatives": list(gate_meta.get("alternatives") or []),
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
            # Inspect-only live hits; pool then relevance-gate (do not invent access).
            lim = max(1, min(int(limit or 24), 100))
            existing = {str(r.get("candidate_key") or "") for r in out["results"]}
            merged = list(out["results"])
            diversified = _diversify_live_hits(live_hits, limit=max(lim, 1))
            for row in diversified:
                key = str(row.get("candidate_key") or "")
                if key and key in existing:
                    continue
                live_row = with_candidate_key(row) or row
                live_row["inspect_only"] = True
                live_row["trust_tier"] = "inspect_only"
                merged.append(live_row)
                if key:
                    existing.add(key)
            corpus = _catalog_corpus(Path(repo_root).resolve(), include_providers=True)
            gated, gate_meta = apply_source_relevance_gate(merged, query, limit=lim, corpus=corpus)
            out["results"] = finalize_discover_rows(stamp_rows(gated))
            out["total"] = len(out["results"])
            relevance_miss = bool(str(query or "").strip()) and not out["results"]
            out["index_miss"] = relevance_miss
            out["relevance_miss"] = relevance_miss
            out["weak_match"] = relevance_miss
            out["no_supported_route"] = bool(gate_meta.get("no_supported_route"))
            out["source_groups"] = list(gate_meta.get("source_groups") or [])
            out["alternatives"] = list(gate_meta.get("alternatives") or [])
            ranking = dict(out.get("ranking") or {})
            ranking.update(gate_meta)
            out["ranking"] = ranking
            out["remote_search"] = {
                "attempted": True,
                "adapters": live_reports,
                "reason": None,
                "diversification": {
                    "rule": "round_robin_provider_soft_cap",
                    "soft_cap": "ceil(limit / n_providers_with_hits)",
                },
                "live_hits_are_inspect_only": True,
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
    results = [with_candidate_key(row) or row for _, row in deduped[: max(limit * 3, limit)]]
    corpus = _catalog_corpus(root, include_providers=include_providers)

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
            "live_hits_are_inspect_only": True,
        }
        existing = {str(r.get("candidate_key") or "") for r in results}
        diversified = _diversify_live_hits(live_hits, limit=max(limit, 1))
        for row in diversified:
            key = str(row.get("candidate_key") or "")
            if key and key in existing:
                continue
            live_row = with_candidate_key(row) or row
            live_row["inspect_only"] = True
            live_row["trust_tier"] = "inspect_only"
            results.append(live_row)
            if key:
                existing.add(key)

    gate_meta: dict[str, Any] = {}
    if q:
        results, gate_meta = apply_source_relevance_gate(results, q, limit=limit, corpus=corpus)
    else:
        results = results[:limit]

    results = finalize_discover_rows(stamp_rows(results))

    # Guard: never return registry dataset default kind.
    for row in results:
        if str(row.get("kind") or "") in {"local_registry", "registry_dataset", "dataset"}:
            row["kind"] = "source"
            row["result_type"] = "source"

    relevance_miss = bool(q) and not results
    return {
        "query": q,
        "result_kind": "source",
        "search_mode": "catalog",
        "results": results,
        "total": len(results),
        "index_miss": relevance_miss,
        "relevance_miss": relevance_miss,
        "weak_match": relevance_miss,
        "no_supported_route": bool(gate_meta.get("no_supported_route")) if gate_meta else relevance_miss,
        "source_groups": list(gate_meta.get("source_groups") or []),
        "alternatives": list(gate_meta.get("alternatives") or []),
        "ranking": {"rule": "catalog_lexical", **gate_meta} if gate_meta else {"rule": "catalog_lexical"},
        "sources_tried": sources_tried,
        "remote_search": remote_search,
        "excludes": {
            "registry_datasets": True,
            "derived_internal": True,
            "local_scrape_artifacts": True,
        },
        "dedupe": {
            "per_capability": True,
            "exact_candidate_key": True,
            "prefer_kind": "source",
            "connectors_only_when_orphan_or_explicit": True,
            "explicit_connector_request": keep_connectors,
        },
    }
