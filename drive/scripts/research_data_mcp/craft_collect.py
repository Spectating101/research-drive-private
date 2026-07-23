#!/usr/bin/env python3
"""Craft a *generic* collect plan from a research need + URL.

This is the AI integration seam: Composer identifies a target (Skynet, SEC,
OpenSea, anything), then this module builds a custom pipeline plan using only
generic job primitives. It never emits named vendor product pipelines
(``skynet_*``, ``opensea_*``, etc. as job_type / script_key / pipeline_id).

Doctrine: SKYNET (the ask) ≠ Skynet (a desk module).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from scripts.research_data_mcp.scrape_plan import (
    build_generic_scrape_plan,
    build_http_manifest_plan_for_url,
    classify_url,
    extract_urls,
    plan_for_url,
)

# Only these job types are legal outputs of craft.
GENERIC_JOB_TYPES = frozenset({"http_manifest", "scraper_run", "source_probe"})

# Named product / branded harvest IDs — refuse if someone tries to smuggle them in.
_FORBIDDEN_PRODUCT_IDS = frozenset(
    {
        "skynet_stablecoin_harvest",
        "opensea_nft_metadata_layer",
        "ethereum_usdt_rpc_pilot",
        "ethereum_usdt_transfers",  # held registry row ok to *query*; not a collect job_type/script
        "coingecko_simple_price",
        "coingecko_daily",
        "nft_opensea",
    }
)
_FORBIDDEN_PIPELINE_RE = re.compile(
    r"^(skynet_.*_harvest|opensea_.*|coingecko_daily|ethereum_usdt_rpc.*)$",
    re.I,
)


def is_forbidden_product_id(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text in GENERIC_JOB_TYPES or text in {"generic_url_scrape", "source_probe", "custom"}:
        return False
    # Crafted landing ids may mention a host token (e.g. craft_skynet_…) — that is fine.
    if text.startswith("craft_"):
        return False
    if text.lower() in _FORBIDDEN_PRODUCT_IDS:
        return True
    return bool(_FORBIDDEN_PIPELINE_RE.match(text))


def validate_generic_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Raise ValueError if plan is not a safe generic collect plan."""
    if not isinstance(plan, dict):
        raise ValueError("collect_plan must be an object")
    job_type = str(plan.get("job_type") or "").strip()
    if job_type not in GENERIC_JOB_TYPES:
        raise ValueError(
            f"collect_plan.job_type must be one of {sorted(GENERIC_JOB_TYPES)}; got {job_type!r}"
        )
    # Only refuse named product ids in executable slots — not destination/dataset landing names.
    for key in ("pipeline_id", "script_key", "queue_task_id", "source_task_id", "job_type", "task_id"):
        raw = str(plan.get(key) or "").strip()
        if raw and is_forbidden_product_id(raw):
            raise ValueError(
                f"collect_plan rejects named vendor product id in {key}={raw!r}; "
                "craft a generic http_manifest/scraper_run/source_probe instead"
            )
    if job_type == "scraper_run":
        script = str(plan.get("script_key") or "generic_url_scrape").strip()
        if script and script != "generic_url_scrape":
            raise ValueError(
                f"scraper_run must use script_key=generic_url_scrape; got {script!r}"
            )
    out = dict(plan)
    out["pipeline"] = "custom"
    out["crafted"] = True
    out.setdefault("launchable", True)
    out.setdefault("requires_approval", True)
    return out


def enforce_submit_doctrine(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Hard gate for HTTP/MCP job submit — refuse named vendor product pipelines.

    Non-collect jobs (archive_upload, hydrate, synthesis, …) pass through unless an
    executable slot carries a forbidden product id.
    """
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")
    for key in ("pipeline_id", "script_key", "queue_task_id", "source_task_id", "job_type", "task_id"):
        raw = str(plan.get(key) or "").strip()
        if raw and is_forbidden_product_id(raw):
            raise ValueError(
                f"Refusing named vendor product id in {key}={raw!r}. "
                "Use research_craft_collect_plan for a generic custom pipeline."
            )
    job_type = str(plan.get("job_type") or "").strip()
    if job_type in GENERIC_JOB_TYPES or plan.get("crafted") or plan.get("pipeline") == "custom":
        return validate_generic_plan(plan)
    return plan


def _slug(text: str, *, limit: int = 48) -> str:
    raw = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return (raw or "craft")[:limit]


def _dataset_id_for(need: str, url: str) -> str:
    host = (urlparse(url).netloc or "web").replace(".", "_")[:24]
    digest = hashlib.sha1(f"{need}|{url}".encode()).hexdigest()[:10]
    return f"craft_{_slug(host, limit=20)}_{digest}"


def _prefer_mode(need: str, url: str, mode: str = "") -> str:
    explicit = str(mode or "").strip().lower()
    if explicit in {"http", "http_manifest", "direct"}:
        return "http_manifest"
    if explicit in {"scrape", "browser", "scraper_run", "page", "catalog"}:
        return "scraper_run" if explicit != "catalog" else "catalog"
    if explicit == "probe":
        return "source_probe"
    # Heuristic: SPA / leaderboard / app hosts usually need browser.
    host = (urlparse(url).netloc or "").lower()
    blob = f"{need} {url} {host}".lower()
    if any(tok in blob for tok in ("leaderboard", "skynet.", "app.", "dashboard", "spa")):
        return "scraper_run"
    # Clear JSON/API GETs should not fall through to browser scrape.
    if classify_url(url) == "direct_http":
        return "http_manifest"
    path = (urlparse(url).path or "").lower()
    if host.startswith("api.") or "/api/" in path or any(
        path.endswith(ext) for ext in (".json", ".geojson", ".csv", ".parquet")
    ):
        return "http_manifest"
    return "scraper_run"


def craft_collect_plan(
    *,
    research_need: str,
    url: str = "",
    title: str = "",
    mode: str = "",
    dataset_id: str = "",
    scrape_mode: str = "page",
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    """Build a generic collect plan. Returns ``{plan, rationale, doctrine}``."""
    need = str(research_need or "").strip()
    if not need:
        raise ValueError("research_need is required")

    url_s = str(url or "").strip()
    if not url_s:
        found = extract_urls(need)
        if found:
            url_s = found[0]
    if not url_s:
        raise ValueError(
            "url is required (or include an https:// URL in research_need) — "
            "craft builds a custom downloader for a concrete target, not a named vendor module"
        )
    if not url_s.startswith("http"):
        if "://" not in url_s:
            url_s = f"https://{url_s}"
        else:
            raise ValueError("url must be http(s)")

    prefer = _prefer_mode(need, url_s, mode)
    host = urlparse(url_s).netloc or "target"
    title_s = str(title or "").strip() or f"Custom collect · {host}"
    did = str(dataset_id or "").strip() or _dataset_id_for(need, url_s)
    if is_forbidden_product_id(did):
        did = _dataset_id_for(need, url_s)

    rationale: list[str] = [
        "Crafted generic custom pipeline (not a named vendor downloader).",
        f"Target host: {host}",
        f"Research need: {need[:240]}",
    ]

    if prefer == "http_manifest":
        plan = build_http_manifest_plan_for_url(url_s, title=title_s, timeout_seconds=timeout_seconds)
        rationale.append("Chose http_manifest — URL looks like a direct file/API GET.")
    elif prefer == "source_probe":
        plan = {
            "title": title_s,
            "job_type": "source_probe",
            "url": url_s,
            "launchable": True,
            "requires_approval": True,
            "timeout_seconds": min(timeout_seconds, 600),
        }
        rationale.append("Chose source_probe — classify connector before collect.")
    elif prefer == "catalog":
        plan = build_generic_scrape_plan(
            url_s,
            mode="catalog",
            title=title_s,
            timeout_seconds=max(timeout_seconds, 7200),
            agent_initiated=True,
        )
        rationale.append("Chose generic Playwright catalog scrape.")
    else:
        plan = build_generic_scrape_plan(
            url_s,
            mode=scrape_mode or "page",
            title=title_s,
            timeout_seconds=timeout_seconds,
            agent_initiated=True,
        )
        rationale.append("Chose generic Playwright page scrape (SPA/HTML target).")

    # Stamp custom-pipeline identity — never a product module name.
    plan["dataset_id"] = did
    plan["destination"] = f"data_lake/procured/{did}"
    plan["partition_id"] = "acquired.procured"
    plan["pipeline"] = "custom"
    plan["crafted"] = True
    plan["craft_target"] = host
    plan["research_need"] = need[:800]
    plan["collect_resolution"] = "craft_collect_plan"
    plan["collect_note"] = (
        "AI-crafted generic collect — target is a URL/API shape, not a desk product module."
    )
    plan = validate_generic_plan(plan)

    return {
        "ok": True,
        "doctrine": (
            "Desk capability = identify + craft custom pipeline. "
            "Vendor names (Skynet, OpenSea, …) are targets, not modules."
        ),
        "rationale": rationale,
        "plan": plan,
        "submit_hint": {
            "tool": "yzu_submit_job",
            "note": "Submit plan as plan_json; researcher must approve in desk UI unless policy auto-approves.",
        },
    }


def craft_discover_route(
    *,
    research_need: str,
    url: str = "",
    title: str = "",
    mode: str = "",
    route_id: str = "craft_primary",
) -> dict[str, Any]:
    """Build one Discover proposal route that embeds an executable generic collect_plan."""
    crafted = craft_collect_plan(research_need=research_need, url=url, title=title, mode=mode)
    plan = crafted["plan"]
    host = str(plan.get("craft_target") or urlparse(str(plan.get("url") or "")).netloc or "target")
    return {
        "id": (route_id or "craft_primary")[:120],
        "title": str(plan.get("title") or f"Custom collect · {host}")[:240],
        "summary": (
            f"AI-crafted generic {plan.get('job_type')} for {host}. "
            "Not a named vendor pipeline."
        )[:1200],
        "access": str(plan.get("job_type") or "custom")[:600],
        "destination": str(plan.get("destination") or "acquired.procured")[:400],
        "cost": "cluster worker · researcher approval",
        "limitation": "Requires a concrete public URL; JS-heavy sites use Playwright scrape.",
        "url": str(plan.get("url") or url)[:800],
        "collect_plan": plan,
        "pipeline": "custom",
        "crafted": True,
    }


def build_crafted_proposal(
    *,
    research_need: str,
    url: str = "",
    title: str = "",
    mode: str = "",
) -> dict[str, Any]:
    """Full Discover proposal object with one crafted route (+ optional probe alternate)."""
    primary = craft_discover_route(
        research_need=research_need, url=url, title=title, mode=mode, route_id="craft_primary"
    )
    routes = [primary]
    # Alternate: probe-first when primary is scrape (researcher may want classify-only).
    if str((primary.get("collect_plan") or {}).get("job_type")) == "scraper_run" and (url or primary.get("url")):
        probe = craft_discover_route(
            research_need=research_need,
            url=url or str(primary.get("url") or ""),
            title=title or "Probe before scrape",
            mode="probe",
            route_id="craft_probe_first",
        )
        routes.append(probe)
    proposal_id = f"craft_{_slug(research_need, limit=24)}_{hashlib.sha1(research_need.encode()).hexdigest()[:8]}"
    return {
        "id": proposal_id[:120],
        "summary": (
            f"Custom pipeline options for: {research_need[:200]}. "
            "Routes use generic job types only — no named vendor downloaders."
        )[:1600],
        "reason": "AI-crafted identify→collect; flywheel promotes whatever lands.",
        "routes": routes,
        "recommended_route_id": "craft_primary",
    }
