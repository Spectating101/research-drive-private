#!/usr/bin/env python3
"""YZU CM faculty profiles — honor-system email login and procure personalization.

Registry schema (per faculty row) — see docs/PROFESSOR_PROFILING.md:
  research_tracks, research_grants, ssrn_papers, working_papers, external_profiles
  lab_fintech_stack, datacite_scopes, bigquery_interests
  registry_dataset_ids, recommended_datasets (Lane B procure intents)
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from sharpe_kernel.paths import repo_root_from_file

TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")

# Registry rows / local datasets to down-rank when the professor profile is unrelated.
DOMAIN_DEMOTE_WHEN_ABSENT: dict[str, tuple[str, ...]] = {
    "social_media": ("coingecko", "gdelt", "fair", "climate"),
    "marketing_consumer": ("gdelt", "fair", "climate", "patent"),
    "org_behavior": ("coingecko", "gdelt", "crypto", "bitcoin", "opensea"),
    "psychology_survey": ("coingecko", "gdelt", "crypto", "equities"),
    "patents": ("coingecko", "gdelt", "consumer", "brand"),
    "accounting": ("gdelt", "opensea", "nft"),
    "green_marketing": ("gdelt", "crypto", "bitcoin"),
}

DOMAIN_BOOST_TOKENS: dict[str, tuple[str, ...]] = {
    "fintech": ("fintech", "crypto", "bitcoin", "ethereum", "coingecko", "blockchain", "defi", "usdt", "stablecoin", "bigquery"),
    "equities": ("equity", "stock", "return", "twse", "crsp", "factor"),
    "econometrics": ("panel", "time series", "econometric", "regression"),
    "machine_learning": ("machine learning", "ml", "neural", "prediction"),
    "social_media": ("social", "influencer", "youtube", "instagram", "brand", "community"),
    "marketing_consumer": ("consumer", "retail", "survey", "brand", "purchase"),
    "patents": ("patent", "uspto", "citation", "invention"),
    "forecasting": ("forecast", "diffusion", "foresight"),
    "org_behavior": ("survey", "leadership", "team", "workplace", "hrm"),
    "psychology_survey": ("scale", "psycholog", "stress", "personality"),
    "accounting": ("accounting", "audit", "earnings", "financial statement", "esg"),
    "international_business": ("fdi", "international", "trade", "diversification"),
    "taiwan_market": ("taiwan", "twse", "mops"),
    "nft": ("nft", "non-fungible", "opensea", "cryptopunk", "rarity", "blockchain"),
    "on_chain": ("on-chain", "onchain", "ethereum", "token transfer", "erc20", "usdt", "stablecoin"),
}

GENERIC_COLD_START = [
    "Find replication datasets for my research area",
    "Search DataCite for recent panels in my field",
    "source this for me — data not in our library yet",
]

# Lane B only — vault inventory is not a procurement recommendation.
PROCUREMENT_SKIP_FAMILIES = frozenset({"lab_vault"})

KEYWORD_STOP = frozenset({
    "https",
    "ssci",
    "the",
    "and",
    "for",
    "from",
    "with",
    "work",
    "research",
    "data",
    "dataset",
    "datasets",
    "a-tier",
    "applied",
})


def _repo_root() -> Path:
    return repo_root_from_file(__file__)


def registry_path() -> Path:
    return _repo_root() / "config" / "yzu_cm_faculty_registry.json"


@lru_cache(maxsize=1)
def _registry_mtime() -> float:
    path = registry_path()
    return path.stat().st_mtime if path.is_file() else 0.0


_REGISTRY_CACHE: dict[str, Any] = {"mtime": -1.0, "data": {"faculty": []}}


def load_registry() -> dict[str, Any]:
    path = registry_path()
    if not path.is_file():
        return {"faculty": []}
    mtime = path.stat().st_mtime
    if _REGISTRY_CACHE["mtime"] != mtime:
        _REGISTRY_CACHE["data"] = json.loads(path.read_text(encoding="utf-8"))
        _REGISTRY_CACHE["mtime"] = mtime
        _registry_mtime.cache_clear()
    return _REGISTRY_CACHE["data"]


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


YZU_EMAIL_RE = re.compile(r"^[^@\s]+@((saturn|staff|student)\.)?yzu\.edu\.tw$", re.IGNORECASE)


def is_valid_yzu_email(email: str) -> bool:
    return bool(YZU_EMAIL_RE.match(normalize_email(email)))


def resolve_profile(*, email: str = "", slug: str = "") -> dict[str, Any] | None:
    data = load_registry()
    faculty = data.get("faculty") or []
    email_n = normalize_email(email)
    slug_n = (slug or "").strip().lower()
    for row in faculty:
        if email_n and normalize_email(str(row.get("email") or "")) == email_n:
            return dict(row)
        if slug_n and str(row.get("slug") or "").lower() == slug_n:
            return dict(row)
    if email_n and is_valid_yzu_email(email_n):
        local = email_n.split("@", 1)[0]
        return {
            "email": email_n,
            "slug": local.replace(".", "-"),
            "name_en": local.replace(".", " ").title(),
            "discipline": "Management",
            "domain_tags": [],
            "starter_prompts": GENERIC_COLD_START,
            "unknown": True,
            "profile_schema": "v2_intel_fallback",
        }
    return None


def cold_start_prompts(profile: dict[str, Any] | None, *, limit: int = 5) -> list[str]:
    if not profile:
        return GENERIC_COLD_START[:limit]
    starters = [str(s).strip() for s in (profile.get("starter_prompts") or []) if str(s).strip()]
    if starters:
        return starters[:limit]
    from_recs = [str(r.get("prompt") or "").strip() for r in procurement_recommendations(profile, limit=limit)]
    if from_recs:
        return from_recs[:limit]
    return GENERIC_COLD_START[:limit]


def _rec_score(rec: dict[str, Any]) -> float:
    try:
        return float(rec.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _infer_source_route(rec: dict[str, Any], profile: dict[str, Any]) -> str:
    explicit = str(rec.get("source_route") or rec.get("route") or "").strip().lower()
    if explicit:
        return explicit
    family = str(rec.get("family") or "")
    prompt = str(rec.get("prompt") or "").lower()
    preferred = {str(s).lower() for s in (profile.get("preferred_sources") or [])}
    if family in {"lab_fintech_stack", "lab_stack"}:
        return "vault"
    if any(t in prompt for t in ("opensea", "nft", "coingecko", "skynet", "crypto landscape")):
        return "vault"
    if "datacite" in prompt or family in {"replication", "governance", "datacite_scope", "nft"}:
        return "datacite"
    if any(t in prompt for t in ("twse", "mops", "taiwan")):
        return "twse_openapi"
    if any(t in prompt for t in ("usdt", "stablecoin", "ethereum", "on-chain", "onchain", "bigquery")):
        return "bigquery"
    if family in {"ml_fintech_alt", "fintech"} and "bigquery" in preferred:
        return "bigquery"
    if "datacite" in preferred:
        return "datacite"
    return "procure"


def lab_fintech_stack_recommendations(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Lab-built FinTech pipelines (vault/registry) tied to grants or papers."""
    out: list[dict[str, Any]] = []
    for item in profile.get("lab_fintech_stack") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        ids = item.get("registry_dataset_ids") or []
        dataset_id = ids[0] if ids else item.get("registry_dataset_id")
        try:
            priority = float(item.get("priority") or 4.5)
        except (TypeError, ValueError):
            priority = 4.5
        prompt = str(item.get("prompt") or "").strip() or (
            f"Extend or analyze {label} for token taxonomy and on/off-chain risk research"
        )
        out.append(
            {
                "family": "lab_fintech_stack",
                "dataset": label,
                "prompt": prompt,
                "dataset_id": dataset_id,
                "partition_id": item.get("partition_id"),
                "vault_path": item.get("vault_path"),
                "score": priority,
                "source_route": str(item.get("route") or "vault"),
                "paper_link": item.get("paper_link"),
                "grant_track": item.get("grant_track"),
            }
        )
    return out


def procurement_recommendations(profile: dict[str, Any], *, limit: int = 12) -> list[dict[str, Any]]:
    """Lane B procurement intents — vault stack + search/source when not in lab."""
    out: list[dict[str, Any]] = list(lab_fintech_stack_recommendations(profile))
    for rec in profile.get("recommended_datasets") or []:
        if not isinstance(rec, dict):
            continue
        if str(rec.get("family") or "") in PROCUREMENT_SKIP_FAMILIES:
            continue
        if rec.get("drive_path"):
            continue
        prompt = str(rec.get("prompt") or "").strip()
        if not prompt:
            continue
        out.append(
            {
                "family": rec.get("family"),
                "dataset": rec.get("dataset"),
                "prompt": prompt,
                "dataset_id": rec.get("dataset_id"),
                "score": _rec_score(rec),
                "source_route": _infer_source_route(rec, profile),
            }
        )
    out.sort(key=lambda row: row["score"], reverse=True)
    return out[:limit]


def recommendation_route_clusters(profile: dict[str, Any], *, limit: int = 12) -> dict[str, list[dict[str, Any]]]:
    """Group procurement recommendations by source_route for Discover UI."""
    clusters: dict[str, list[dict[str, Any]]] = {}
    for rec in procurement_recommendations(profile, limit=limit):
        route = str(rec.get("source_route") or "procure")
        clusters.setdefault(route, []).append(rec)
    return clusters


def primary_research_track(profile: dict[str, Any]) -> dict[str, Any] | None:
    tracks = [t for t in (profile.get("research_tracks") or []) if isinstance(t, dict)]
    if not tracks:
        for grant in profile.get("research_grants") or []:
            if isinstance(grant, dict) and grant.get("primary_direction"):
                return {"id": "grant", "title": grant.get("title"), "phase": grant.get("phase") or "active_grant"}
        return None
    tracks.sort(key=lambda t: float(t.get("weight") or 0), reverse=True)
    return tracks[0]


def profile_research_phrases(profile: dict[str, Any], *, limit: int = 12) -> list[str]:
    """Keywords + grants + SSRN/WP + specialties for query expansion and ranking."""
    phrases: list[str] = []
    for kw in profile.get("research_keywords") or []:
        k = str(kw).strip().lower()
        if len(k) >= 4 and k not in KEYWORD_STOP and not k.startswith("http"):
            phrases.append(k)
    for spec in profile.get("specialties") or []:
        s = str(spec).strip().lower()
        if len(s) >= 5:
            phrases.append(s)
    for paper in profile.get("ssrn_papers") or []:
        if not isinstance(paper, dict):
            continue
        for kw in paper.get("keywords") or []:
            k = str(kw).strip().lower()
            if len(k) >= 3 and k not in KEYWORD_STOP:
                phrases.append(k)
    for paper in profile.get("working_papers") or []:
        if not isinstance(paper, dict):
            continue
        for kw in paper.get("keywords") or []:
            k = str(kw).strip().lower()
            if len(k) >= 3 and k not in KEYWORD_STOP:
                phrases.append(k)
    primary = primary_research_track(profile)
    if primary and primary.get("title"):
        title = str(primary["title"]).lower()
        for needle in ("token", "on-chain", "off-chain", "nft", "taxonomy", "risk", "return"):
            if needle in title:
                phrases.append(needle)
    for paper in (profile.get("publication_highlights") or profile.get("journal_papers") or [])[:3]:
        text = str(paper).lower()
        for needle in (
            "momentum",
            "machine learning",
            "taiwan",
            "trust",
            "misconduct",
            "corporate governance",
            "stablecoin",
            "fintech",
            "pacific-basin",
            "reputation",
            "non-fungible",
            "nft",
        ):
            if needle in text and needle not in phrases:
                phrases.append(needle)
    return list(dict.fromkeys(phrases))[:limit]


def datacite_scope_queries(profile: dict[str, Any]) -> list[str]:
    """Short DataCite seeds from profile scopes — avoids long zero-hit prompts."""
    seeds: list[str] = []
    for scope in profile.get("datacite_scopes") or []:
        if not isinstance(scope, dict):
            continue
        for q in scope.get("seed_queries") or []:
            q = str(q).strip()
            if q:
                seeds.append(q)
    return list(dict.fromkeys(seeds))


def datacite_scope_score_adjustment(row: dict[str, Any], profile: dict[str, Any]) -> float:
    blob = _row_blob(row)
    delta = 0.0
    for scope in profile.get("datacite_scopes") or []:
        if not isinstance(scope, dict):
            continue
        require = [str(x).lower() for x in (scope.get("require_any") or []) if x]
        demote = [str(x).lower() for x in (scope.get("demote_any") or []) if x]
        if require and any(r in blob for r in require):
            delta += 0.55
        if demote and any(d in blob for d in demote):
            delta -= 0.85
    return delta


def default_search_query(profile: dict[str, Any] | None) -> str:
    if not profile:
        return "finance panel dataset"
    dc_seeds = datacite_scope_queries(profile)
    if dc_seeds:
        return f"{dc_seeds[0]} dataset"
    primary = primary_research_track(profile)
    if primary and primary.get("title"):
        title = str(primary["title"])
        if "token" in title.lower():
            return "NFT token taxonomy on-chain off-chain dataset"
    phrases = profile_research_phrases(profile, limit=4)
    if phrases:
        return f"{' '.join(phrases[:3])} dataset"
    tags = [str(t) for t in (profile.get("domain_tags") or [])[:4] if t]
    if tags:
        return f"{' '.join(tags)} dataset"
    discipline = str(profile.get("discipline") or "research").strip()
    return f"{discipline.lower()} panel dataset"


def bigquery_route_hints(profile: dict[str, Any] | None, query: str = "") -> list[dict[str, str]]:
    if not profile:
        return []
    tags = _profile_tags(profile)
    preferred = {str(s).lower() for s in (profile.get("preferred_sources") or [])}
    if "bigquery" not in preferred and "fintech" not in tags and not profile.get("bigquery_interests"):
        return []
    combined = f"{query} {' '.join(profile_research_phrases(profile))}".lower()
    q_only = (query or "").lower().strip()
    hints: list[dict[str, str]] = []
    seen: set[str] = set()
    for interest in profile.get("bigquery_interests") or []:
        if not isinstance(interest, dict):
            continue
        rid = str(interest.get("registry_id") or "").strip()
        if not rid or rid in seen:
            continue
        triggers = [str(t).lower() for t in (interest.get("trigger_keywords") or []) if t]
        if not triggers:
            continue
        # User query wins: do not route BQ on profile keywords alone when the ask is unrelated.
        if q_only:
            if not any(t in q_only for t in triggers):
                continue
        elif not any(t in combined for t in triggers):
            continue
        seen.add(rid)
        hints.append(
            {
                "registry_id": rid,
                "label": str(interest.get("label") or rid),
                "note": str(interest.get("note") or "BigQuery — dry-run before export"),
                "grant_track": interest.get("grant_track"),
            }
        )
    if not hints and q_only and any(
        t in q_only for t in ("usdt", "stablecoin", "ethereum", "on-chain", "onchain", "token transfer", "taxonomy")
    ):
        hints.append(
            {
                "registry_id": "ethereum_usdt_transfers",
                "label": "Ethereum USDT on-chain transfers",
                "note": "BigQuery public crypto dataset — dry-run before export",
            }
        )
    return hints


def expand_datacite_queries(query: str, profile: dict[str, Any] | None = None) -> list[str]:
    """Profile-aware DataCite query expansion (live API — no bulk harvest)."""
    from scripts.research_data_mcp.procurement_search import datacite_supplement_queries

    base = datacite_supplement_queries(query)
    q = query.strip()
    if not profile:
        return base

    extra: list[str] = list(datacite_scope_queries(profile))
    qtok = set(TOKEN_RE.findall(q.lower()))

    if len(qtok) <= 2:
        for rec in procurement_recommendations(profile, limit=4):
            if rec.get("source_route") != "datacite":
                continue
            seed = re.sub(
                r"^(search datacite for|find|source|search for)\s+",
                "",
                str(rec.get("prompt") or ""),
                flags=re.I,
            ).strip()
            if seed:
                extra.append(seed)

    for phrase in profile_research_phrases(profile, limit=5):
        if len(phrase) < 5:
            continue
        if phrase in q.lower():
            continue
        if qtok:
            extra.append(f"{q} {phrase}".strip())
        else:
            extra.append(phrase)

    tags = _profile_tags(profile)
    if "taiwan_market" in tags and "taiwan" not in q.lower():
        extra.append(f"{q} taiwan equity stock".strip())
    if "machine_learning" in tags and "machine learning" not in q.lower():
        extra.append(f"{q} machine learning asset pricing".strip())
    if "fintech" in tags and not {"crypto", "stablecoin", "usdt"} & qtok:
        extra.append(f"{q} fintech stablecoin".strip())

    merged = list(dict.fromkeys([*base, *extra, q]))
    return [item for item in merged if item.strip()][:8]


def agent_research_context(profile: dict[str, Any] | None) -> str:
    """Compact research identity for the procurement agent (Lane B)."""
    if not profile or profile.get("unknown"):
        return ""
    label = formal_display_name(profile) or str(profile.get("email") or "")
    specialties = ", ".join(str(s) for s in (profile.get("specialties") or [])[:4])
    methods = ", ".join(str(m) for m in (profile.get("method_tags") or [])[:3])
    keywords = ", ".join(profile_research_phrases(profile, limit=8))
    papers = "; ".join(str(p)[:100] for p in (profile.get("publication_highlights") or [])[:2])
    ssrn = profile.get("ssrn_papers") or []
    if ssrn and isinstance(ssrn[0], dict):
        papers = f"{ssrn[0].get('title', '')[:90]}; {papers}".strip("; ")
    grant = primary_research_track(profile)
    routes = ", ".join(sorted({str(r.get("source_route") or "") for r in procurement_recommendations(profile, limit=8)}))
    lab = [str(x.get("label") or "") for x in (profile.get("lab_fintech_stack") or [])[:4] if isinstance(x, dict)]
    bits = [f"Researcher: {label}."]
    if specialties:
        bits.append(f"Specialties: {specialties}.")
    if keywords:
        bits.append(f"Keywords: {keywords}.")
    if papers:
        bits.append(f"Recent work: {papers}.")
    if grant and grant.get("title"):
        bits.append(f"Active direction: {str(grant['title'])[:120]}.")
    if lab:
        bits.append(f"Lab FinTech stack: {', '.join(lab)}.")
    if methods:
        bits.append(f"Methods: {methods}.")
    if routes:
        bits.append(f"When sourcing missing data, prefer routes: {routes}.")
    bits.append("Vault inventory is separate — use search/procure tools for data not yet in the lab.")
    return " ".join(bits)


def _row_blob(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("title") or ""),
        str(row.get("dataset_id") or row.get("id") or ""),
        str(row.get("doi") or ""),
        str(row.get("source") or ""),
        str(row.get("collect_via") or ""),
        str(row.get("description") or ""),
    ]
    return " ".join(parts).lower()


def _profile_tags(profile: dict[str, Any]) -> set[str]:
    return {str(t) for t in (profile.get("domain_tags") or []) if t}


def profile_score_adjustment(row: dict[str, Any], query: str, profile: dict[str, Any] | None) -> float:
    """Soft ranking boost/demote from faculty seed profile (not a hard filter)."""
    if not profile:
        return 0.0
    blob = _row_blob(row)
    qtok = set(TOKEN_RE.findall((query or "").lower()))
    tags = _profile_tags(profile)
    delta = 0.0

    for tag in tags:
        for needle in DOMAIN_BOOST_TOKENS.get(tag, ()):
            if needle in blob or needle in qtok:
                delta += 0.35

    absent_demote_keys: set[str] = set()
    for tag, needles in DOMAIN_DEMOTE_WHEN_ABSENT.items():
        if tag in tags:
            continue
        absent_demote_keys.update(needles)

    for needle in absent_demote_keys:
        if needle in blob and needle not in qtok:
            delta -= 0.6

    preferred = {str(s).lower() for s in (profile.get("preferred_sources") or [])}
    collect_via = str(row.get("collect_via") or row.get("source") or "").lower()
    if "cluster_scrape" in preferred and collect_via in {"magic", "scrape", "magic_procure"}:
        delta += 0.4
    if "datacite" in preferred and collect_via == "datacite":
        delta += 0.25
    if "twse_openapi" in preferred and "twse" in blob:
        delta += 0.5
    if "bigquery" in preferred and ("bigquery" in blob or "ethereum_usdt" in blob or "usdt" in blob):
        delta += 0.45

    for phrase in profile_research_phrases(profile, limit=10):
        if len(phrase) < 5:
            continue
        if phrase in blob:
            delta += 0.28
            continue
        parts = [t for t in phrase.split() if len(t) >= 4]
        if len(parts) >= 2 and all(part in blob for part in parts):
            delta += 0.22

    stack_ids = set()
    for item in profile.get("lab_fintech_stack") or []:
        if not isinstance(item, dict):
            continue
        for rid in item.get("registry_dataset_ids") or []:
            stack_ids.add(str(rid).lower())
        if item.get("registry_dataset_id"):
            stack_ids.add(str(item["registry_dataset_id"]).lower())
    row_id = str(row.get("dataset_id") or row.get("id") or "").lower()
    if row_id and row_id in stack_ids:
        delta += 0.75
    for rid in profile.get("registry_dataset_ids") or []:
        if row_id and row_id == str(rid).lower():
            delta += 0.5

    if str(row.get("kind") or "") == "datacite" or str(row.get("collect_via") or "") == "datacite":
        delta += datacite_scope_score_adjustment(row, profile)

    for rec in profile.get("procurement_recommendations") or (
        procurement_recommendations(profile) if profile.get("recommended_datasets") else []
    ):
        title = str(rec.get("dataset") or "").lower()
        if title and title in blob:
            delta += 0.35

    return delta


def profiles_are_distinct(profiles: list[dict[str, Any]], *, min_tag_distance: int = 2) -> bool:
    """True when no two profiles share identical domain tag sets."""
    seen: list[set[str]] = []
    for p in profiles:
        tags = _profile_tags(p)
        for other in seen:
            if len(tags.symmetric_difference(other)) < min_tag_distance:
                return False
        seen.append(tags)
    return True


def formal_display_name(profile: dict[str, Any] | None) -> str:
    """Title + surname only — never given name (UI + agent addressing)."""
    if not profile:
        return ""
    title_raw = str(profile.get("title") or "Professor").split(",")[0].strip()
    if re.search(r"assistant professor", title_raw, re.I):
        title_short = "Asst. Prof."
    elif re.search(r"associate professor", title_raw, re.I):
        title_short = "Assoc. Prof."
    elif re.search(r"professor", title_raw, re.I):
        title_short = "Prof."
    else:
        title_short = title_raw.split()[0] if title_raw else "Prof."

    name = str(profile.get("name_en") or "").strip()
    surname = ""
    if "," in name:
        surname = name.split(",", 1)[0].strip()
    elif name:
        surname = name.split()[-1]
    return f"{title_short} {surname}".strip() if surname else title_short


def _public_preferred_sources(profile: dict[str, Any]) -> list[str]:
    remap = {
        "magic_procure": "yzu_submit_job",
    }
    out: list[str] = []
    for raw in profile.get("preferred_sources") or []:
        source = remap.get(str(raw), str(raw))
        if source and source not in out:
            out.append(source)
    return out


def profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": profile.get("slug"),
        "name_en": profile.get("name_en"),
        "email": profile.get("email"),
        "discipline": profile.get("discipline"),
        "title": profile.get("title"),
        "domain_tags": profile.get("domain_tags") or [],
        "method_tags": profile.get("method_tags") or [],
        "preferred_sources": _public_preferred_sources(profile),
        "specialties": profile.get("specialties") or [],
        "research_keywords": profile.get("research_keywords") or [],
        "publication_highlights": (profile.get("publication_highlights") or profile.get("journal_papers") or [])[:3],
        "starter_prompts": cold_start_prompts(profile),
        "paper_count_parsed": profile.get("paper_count_parsed", 0),
        "pilot_professor": bool(profile.get("pilot_professor")),
        "unknown": bool(profile.get("unknown")),
        "default_search_query": default_search_query(profile),
        "procurement_recommendations": procurement_recommendations(profile),
        "recommendation_clusters": recommendation_route_clusters(profile),
        "bigquery_hints": bigquery_route_hints(profile),
        "research_tracks": profile.get("research_tracks") or [],
        "lab_fintech_stack": [
            {k: item.get(k) for k in ("id", "label", "partition_id", "route", "registry_dataset_ids")}
            for item in (profile.get("lab_fintech_stack") or [])
            if isinstance(item, dict)
        ],
        "datacite_scopes": [
            {k: scope.get(k) for k in ("id", "seed_queries", "note")}
            for scope in (profile.get("datacite_scopes") or [])
            if isinstance(scope, dict)
        ],
        "intel_sources": profile.get("external_profiles") or {},
        "profile_schema": "v2_intel",
    }


def llm_gap_hint(profile: dict[str, Any] | None, query: str) -> str:
    """Short system hint when catalog can't deliver immediately — tools + YZU jobs."""
    base = (
        "If no registry hit is ready, use acquisition tools (probe URL, yzu_submit_job, cluster scrape, "
        "DataCite collect) rather than only describing APIs. Confirm before large collects."
    )
    if not profile:
        return base
    methods = profile.get("method_tags") or []
    sources = profile.get("preferred_sources") or []
    bits = [base]
    if "scrape_text" in methods or "cluster_scrape" in sources:
        bits.append("Scrape/web sources are in scope for this professor — route via cluster when needed.")
    if "datacite" in sources:
        bits.append("Prefer DataCite resolve/collect when DOIs match.")
    if "bigquery" in sources:
        bits.append("For on-chain FinTech (USDT/Ethereum), route via BigQuery dry-run before large exports.")
    hints = bigquery_route_hints(profile, query)
    if hints:
        bits.append(f"BigQuery registry candidates: {', '.join(h['registry_id'] for h in hints)}.")
    if query.strip():
        bits.append(f"User query: {query.strip()[:200]}")
    return " ".join(bits)
