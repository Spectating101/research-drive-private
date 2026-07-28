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
    "social_media": ("gdelt", "fair", "climate"),
    "marketing_consumer": ("gdelt", "fair", "climate", "patent"),
    "org_behavior": ("gdelt", "crypto", "bitcoin"),
    "psychology_survey": ("gdelt", "crypto", "equities"),
    "patents": ("gdelt", "consumer", "brand"),
    "accounting": ("gdelt", "nft"),
    "green_marketing": ("gdelt", "crypto", "bitcoin"),
}

DOMAIN_BOOST_TOKENS: dict[str, tuple[str, ...]] = {
    "fintech": ("fintech", "crypto", "bitcoin", "ethereum", "blockchain", "defi", "stablecoin", "bigquery"),
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
    "nft": ("nft", "non-fungible", "marketplace", "rarity", "blockchain"),
    "on_chain": ("on-chain", "onchain", "ethereum", "token transfer", "erc20", "stablecoin"),
}

GENERIC_COLD_START = [
    "Identify a public dataset for my research and land it via custom procure",
    "Search DataCite for recent panels in my field",
    "Craft a collect plan for a public URL I provide",
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
    """Prefer explicit score; fall back to priority so procure rows don't sink to 0."""
    for key in ("score", "priority"):
        raw = rec.get(key)
        if raw is None or raw == "":
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def _infer_source_route(rec: dict[str, Any], profile: dict[str, Any]) -> str:
    """Honor explicit routes only — do not keyword-map vendors into fake product lanes."""
    explicit = str(rec.get("source_route") or rec.get("route") or "").strip().lower()
    if explicit in {"vault", "registry"}:
        # Vault/registry only when the rec is actually a held reference — else procure.
        return "procure" if str(rec.get("holding_status") or "") in {"missing", "unwired", "catalog"} else explicit
    if explicit:
        return explicit
    family = str(rec.get("family") or "")
    if family in {"custom_pipeline", "procure", "nft", "crypto"}:
        return "procure"
    if family in {"datacite_scope", "replication", "governance"}:
        return "datacite"
    preferred = {str(s).lower() for s in (profile.get("preferred_sources") or [])}
    if "datacite" in preferred and family not in {"taiwan_equity_panel"}:
        return "datacite"
    return "procure"


def lab_fintech_stack_recommendations(
    profile: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Held reference pieces only — never injected as procurement product lanes.

    Prefer ``reference_holdings`` on the public profile. This helper remains for
    ops/debug; ``procurement_recommendations`` no longer prepends these rows.
    """
    root = Path(repo_root).resolve() if repo_root else None
    registry_by_id: dict[str, dict[str, Any]] = {}
    if root is not None:
        for candidate in (
            root / "config/research_query_registry.json",
            root / "drive/config/research_query_registry.json",
        ):
            if not candidate.is_file():
                continue
            try:
                doc = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for row in doc.get("datasets") or []:
                if isinstance(row, dict) and row.get("dataset_id"):
                    registry_by_id[str(row["dataset_id"])] = row
            break

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
            f"Query held reference panel {label} if local bytes exist; else craft a custom collect"
        )
        route = str(item.get("route") or "vault")
        held = True
        holding_status = "held"
        if dataset_id and root is not None:
            from scripts.research_data_mcp.registry_access import (
                _LOCAL_SAMPLE_BACKENDS,
                local_data_ready,
            )

            row = registry_by_id.get(str(dataset_id)) or {"dataset_id": dataset_id}
            backend = str(row.get("backend") or "")
            readiness = str(row.get("analysis_readiness") or "")
            if backend in _LOCAL_SAMPLE_BACKENDS:
                held = local_data_ready(row, root)
                holding_status = "held" if held else "missing"
                if not held:
                    route = "procure"
                    priority = min(priority, 3.2)
            elif readiness in {"dry_run_before_execution", "minutes_rate_limited", "procurement_planning"}:
                holding_status = "guarded"
                held = True
            elif readiness in {"metadata_search", "catalog_only"}:
                holding_status = "catalog"
                held = False
                route = "procure"
                priority = min(priority, 3.2)
            else:
                holding_status = "connected"
                held = True
        elif not dataset_id and route == "vault":
            route = "procure"
            priority = min(priority, 3.5)
            holding_status = "unwired"
            held = False

        # Only emit held/connected references here — missing ones are craft targets, not menu items.
        if holding_status in {"missing", "unwired", "catalog"} or route in {"acquire", "procure"}:
            continue

        out.append(
            {
                "family": "reference_holding",
                "dataset": label,
                "prompt": prompt,
                "dataset_id": dataset_id,
                "partition_id": item.get("partition_id"),
                "vault_path": item.get("vault_path"),
                "score": priority,
                "source_route": route,
                "holding_status": holding_status,
                "role": "reference_holding",
                "paper_link": item.get("paper_link"),
                "grant_track": item.get("grant_track"),
            }
        )
    return out


def procurement_recommendations(
    profile: dict[str, Any],
    *,
    limit: int = 12,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Procurement intents — identify + custom procure. No lab-stack product menu."""
    del repo_root  # held references live on profile.reference_holdings, not in this list
    out: list[dict[str, Any]] = []
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
        route = _infer_source_route(rec, profile)
        row = {
            "family": rec.get("family") or "custom_pipeline",
            "dataset": rec.get("dataset"),
            "prompt": prompt,
            "dataset_id": rec.get("dataset_id"),
            "score": _rec_score(rec),
            "source_route": route,
        }
        pipeline = str(rec.get("pipeline") or "").strip()
        if not pipeline and route in {"procure", "acquire"}:
            pipeline = "custom"
        if pipeline:
            row["pipeline"] = pipeline
        if rec.get("holding_status"):
            row["holding_status"] = rec.get("holding_status")
        out.append(row)
    out.sort(key=lambda row: row["score"], reverse=True)
    return out[:limit]


def recommendation_route_clusters(
    profile: dict[str, Any],
    *,
    limit: int = 12,
    repo_root: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Group procurement recommendations by source_route for Discover UI."""
    clusters: dict[str, list[dict[str, Any]]] = {}
    for rec in procurement_recommendations(profile, limit=limit, repo_root=repo_root):
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
    """Hints only from explicit profile.bigquery_interests — never invent USDT/vendor cards."""
    if not profile:
        return []
    preferred = {str(s).lower() for s in (profile.get("preferred_sources") or [])}
    interests = profile.get("bigquery_interests") or []
    if "bigquery" not in preferred and not interests:
        return []
    q_only = (query or "").lower().strip()
    combined = f"{query} {' '.join(profile_research_phrases(profile))}".lower()
    hints: list[dict[str, str]] = []
    seen: set[str] = set()
    for interest in interests:
        if not isinstance(interest, dict):
            continue
        rid = str(interest.get("registry_id") or "").strip()
        if not rid or rid in seen:
            continue
        triggers = [str(t).lower() for t in (interest.get("trigger_keywords") or []) if t]
        if not triggers:
            continue
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
    # Do not append vendor/stablecoin seeds from fintech tags — craft/identify handles that.
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
    bits = [f"Researcher: {label}."]
    if specialties:
        bits.append(f"Specialties: {specialties}.")
    if keywords:
        bits.append(f"Keywords: {keywords}.")
    if papers:
        bits.append(f"Recent work: {papers}.")
    if grant and grant.get("title"):
        bits.append(f"Active direction: {str(grant['title'])[:120]}.")
    if methods:
        bits.append(f"Methods: {methods}.")
    if routes:
        bits.append(f"When sourcing missing data, prefer routes: {routes}.")
    bits.append(
        "Acquisition doctrine: research_craft_collect_plan → yzu_submit_job "
        "(generic http_manifest/scraper_run/source_probe only; no named vendor downloaders)."
    )
    bits.append("Vault inventory is separate — use search/craft tools for data not yet in the lab.")
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
    if "bigquery" in preferred and "bigquery" in blob:
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

    # No lab_fintech_stack / vendor-id ranking boosts — craft + registry search only.
    row_id = str(row.get("dataset_id") or row.get("id") or "").strip().lower()
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


def profile_summary(profile: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, Any]:
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
        "procurement_recommendations": procurement_recommendations(profile, repo_root=repo_root),
        "recommendation_clusters": recommendation_route_clusters(profile, repo_root=repo_root),
        "bigquery_hints": bigquery_route_hints(profile),
        "research_tracks": profile.get("research_tracks") or [],
        # Held reference pieces only — not branded product modules (OpenSea/Skynet/etc.).
        "reference_holdings": [
            {
                **{k: item.get(k) for k in ("id", "label", "partition_id", "route", "registry_dataset_ids")},
                "role": "reference_holding",
            }
            for item in (profile.get("lab_fintech_stack") or [])
            if isinstance(item, dict)
        ],
        # Back-compat alias for older FE; same objects as reference_holdings.
        "lab_fintech_stack": [
            {k: item.get(k) for k in ("id", "label", "partition_id", "route", "registry_dataset_ids")}
            for item in (profile.get("lab_fintech_stack") or [])
            if isinstance(item, dict)
        ],
        "example_procure_targets": [
            {k: row.get(k) for k in ("label", "why", "example_dataset_id", "example_partition_id")}
            for row in (profile.get("example_procure_targets") or [])
            if isinstance(row, dict)
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
        "If no registry hit is ready: research_craft_collect_plan for a concrete URL "
        "(generic http_manifest/scraper_run/source_probe only), then yzu_submit_job. "
        "Never run named vendor pipelines — craft a custom plan for the target."
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
        bits.append("BigQuery seat available — dry-run before large exports; craft the concrete query, do not assume a USDT module.")
    hints = bigquery_route_hints(profile, query)
    if hints:
        bits.append(f"BigQuery registry candidates: {', '.join(h['registry_id'] for h in hints)}.")
    if query.strip():
        bits.append(f"User query: {query.strip()[:200]}")
    return " ".join(bits)
