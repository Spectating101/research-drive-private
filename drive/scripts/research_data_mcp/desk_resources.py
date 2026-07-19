#!/usr/bin/env python3
"""Roll up desk consumption for Resources — AI, metered APIs, usage, motion, compute."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _gb(n: int | float | None) -> float | None:
    if n is None:
        return None
    try:
        return round(float(n) / 1024**3, 2)
    except (TypeError, ValueError):
        return None


def _count_tavily_keys() -> int:
    keys = set()
    for env_key, val in os.environ.items():
        if env_key.startswith("TAVILY_API_KEY") and val and "tvly-" in val:
            keys.add(val)
    return len(keys)


def _tavily_live_enabled() -> bool:
    for name in ("TAVILY_LIVE_ENABLED", "TAVILY_ALLOW_LIVE"):
        if os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
    return False


def _read_tavily_external_usage(repo_root: Path) -> dict[str, Any] | None:
    """Best-effort read of Molina TavilyBalancer _usage.json (if present)."""
    cache_dir = os.getenv(
        "TAVILY_CACHE_DIR",
        "/home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/data/tavily_cache",
    )
    path = Path(cache_dir) / "_usage.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return None


def _load_governance(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "config/procurement_governance.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cluster_max_parallel(repo_root: Path) -> int | None:
    path = repo_root / "config/yzu_cluster.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int((data.get("worker_pools") or {}).get("windows_lab", {}).get("max_parallel") or 0) or None
    except Exception:
        return None


def _curated_connect_counts(repo_root: Path) -> tuple[int, int]:
    path = repo_root / "config/desk_sources.json"
    if not path.is_file():
        return 9, 9
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sources = sum(1 for s in data.get("sources") or [] if s.get("show_on_resources"))
        layers = len(data.get("layers") or [])
        return sources or 9, layers or 9
    except Exception:
        return 9, 9


def build_desk_resources(gateway: Any, *, live: bool = False) -> dict[str, Any]:
    """Single rollup for Resources UI — consumption first, not catalog inventory."""
    repo_root: Path = gateway.repo_root
    health = gateway.desk_health(live=False)
    desk = health.get("desk") or {}
    tiers = desk.get("storage_tiers") or {}
    canonical = tiers.get("canonical") or desk.get("archive") or {}
    hot = tiers.get("hot") or {}
    cache = tiers.get("cache") or desk.get("bulk_storage") or {}

    from scripts.research_data_mcp import bigquery_client
    from scripts.research_data_mcp.desk_usage import today_summary

    bq = bigquery_client.status()
    usage_today = today_summary(repo_root)
    tavily_ext = _read_tavily_external_usage(repo_root)
    gov = _load_governance(repo_root)
    budgets = gov.get("budgets") or {}

    profiles = gateway.list_credential_profiles().get("profiles") or []
    cred_configured = sum(1 for p in profiles if p.get("configured"))
    cred_total = len(profiles)

    cat = {"summary": {}}
    try:
        cat = gateway.procurement_catalog(q="", limit=1)
    except Exception:
        pass
    catalog = cat.get("summary") or {}

    cluster = gateway.cluster_status(live=False)  # never SSH-probe shards — UI must stay sub-second
    wl = (cluster.get("worker_pools") or {}).get("windows_lab") or {}
    pools = desk.get("worker_pools") or {}
    jobs = gateway.orchestrator.stats()
    ops = gateway.ops_status()

    campaigns = gateway.list_campaigns(limit=50).get("campaigns") or []
    active_statuses = {"running", "pending", "active", "in_progress", "collecting"}
    campaigns_active = sum(1 for c in campaigns if str(c.get("status") or "").lower() in active_statuses)

    dc = cluster.get("datacite") or {}
    gdelt = cluster.get("gdelt") or {}
    cq = ops.get("collection_queue") or {}
    dh = ops.get("datacite_harvest") or {}

    vault_used = canonical.get("used_tb")
    vault_cap = canonical.get("quota_tb") or canonical.get("pool_tb")
    vault_pct = None
    if vault_used is not None and vault_cap:
        try:
            vault_pct = round(float(vault_used) / float(vault_cap) * 100)
        except (TypeError, ValueError, ZeroDivisionError):
            vault_pct = None

    mcp = desk.get("mcp_tools") or {}
    composer_model = desk.get("composer_model") or "composer-2.5"
    composer_ok = bool(desk.get("composer_configured"))
    legacy_ok = bool(desk.get("legacy_llm_configured"))

    bq_ok = bq.get("credentials") == "available"
    tavily_keys = _count_tavily_keys()
    hf_ok = any(p.get("id") == "huggingface" and p.get("configured") for p in profiles)

    issues: list[dict[str, str]] = []

    def _issue(key: str, label: str, section: str) -> None:
        issues.append({"key": key, "label": label, "section": section})

    cache_pct = None
    if cache.get("used_gb") is not None and cache.get("total_gb"):
        try:
            cache_pct = round(float(cache["used_gb"]) / float(cache["total_gb"]) * 100)
        except (TypeError, ValueError, ZeroDivisionError):
            cache_pct = None
    if cache_pct is not None and cache_pct >= 85:
        _issue("usb-cache", "USB bulk cache", "usage")
    if vault_pct is not None and vault_pct >= 75:
        _issue("vault", "GDrive vault", "usage")
    if hot.get("headroom_ok") is False:
        free_gb = hot.get("free_gb")
        need_gb = hot.get("required_min_gb")
        if free_gb is not None and need_gb is not None:
            _issue("nvme", f"NVMe hot desk {free_gb} GB free (min {need_gb} GB)", "usage")
        else:
            _issue("nvme", "NVMe hot desk", "usage")
    if jobs.get("pending_approval", 0) > 0:
        _issue("jobs-pending", f"{jobs['pending_approval']} job(s) pending approval", "motion")
    # Lifetime failed/cancelled totals are historical — only flag recent failures.
    failed_recent = int(jobs.get("failed_recent") or (jobs.get("actionable") or {}).get("failed_recent") or 0)
    if failed_recent > 0:
        days = int(jobs.get("recent_days") or (jobs.get("actionable") or {}).get("failed_recent_days") or 7)
        _issue("jobs-failed-recent", f"{failed_recent} failed job(s) in last {days}d", "motion")
    if not composer_ok and not legacy_ok:
        _issue("composer", "Ask engine offline", "ai")
    if not bq_ok:
        _issue("bigquery", "BigQuery credentials missing", "metered")

    tavily_today = usage_today.get("tavily_calls") or 0
    if isinstance(tavily_ext, dict):
        for val in tavily_ext.values():
            if isinstance(val, (int, float)):
                tavily_today = max(tavily_today, int(val))

    source_count, layer_count = _curated_connect_counts(repo_root)

    from scripts.research_data_mcp.desk_activity import read_recent, top_bq_drivers
    from scripts.research_data_mcp.desk_usage import period_summary

    period = period_summary(days=30, repo_root=repo_root)
    activity_events = read_recent(limit=40, repo_root=repo_root)
    bq_drivers = top_bq_drivers(limit=5, repo_root=repo_root)

    return {
        "status": "ok",
        "generated_at": _utc_now(),
        "hero": {
            "composer": {
                "model": composer_model,
                "configured": composer_ok,
                "legacy_configured": legacy_ok,
            },
            "mcp_tools": mcp.get("total"),
            "query_engine": {"port": 8765, "up": health.get("status") in {"ok", "demo"}},
            "workers": {
                "busy": pools.get("busy") if pools.get("busy") is not None else wl.get("joined"),
                "total": pools.get("total") if pools.get("total") is not None else wl.get("total"),
            },
            "vault": {
                "used_tb": vault_used,
                "cap_tb": vault_cap,
                "pct": vault_pct,
            },
            "chips": {
                "bigquery": "configured" if bq_ok else "missing",
                "tavily": f"{tavily_keys} keys" if tavily_keys else "off",
                "huggingface": "on" if hf_ok else "off",
                "collect_tokens": f"{cred_configured}/{cred_total}" if cred_total else None,
            },
        },
        "ai": {
            "composer_model": composer_model,
            "composer_configured": composer_ok,
            "legacy_llm_configured": legacy_ok,
            "desk_token_required": bool(desk.get("desk_token_required")),
            "mcp_tools": mcp,
            "composer_turns_today": usage_today.get("composer_turns") or 0,
        },
        "metered": {
            "bigquery": {
                "configured": bq_ok,
                "project": bq.get("project"),
                "credential_type": bq.get("credential_type"),
                "default_max_bytes_billed": bq.get("default_max_bytes_billed"),
                "hard_max_bytes_billed": bq.get("hard_max_bytes_billed"),
                "default_max_gib": _gb(bq.get("default_max_bytes_billed")),
                "bytes_billed_today": usage_today.get("bq_bytes_billed") or 0,
                "gib_billed_today": usage_today.get("bq_gib_billed") or 0.0,
            },
            "tavily": {
                "keys_loaded": tavily_keys,
                "live_enabled": _tavily_live_enabled(),
                "session_budget": budgets.get("max_tavily_live_per_magic"),
                "calls_today": tavily_today,
            },
            "huggingface": {
                "configured": hf_ok,
            },
            "collect_credentials": {
                "configured": cred_configured,
                "total_profiles": cred_total,
            },
            "governance_budgets": {
                "max_deepseek_calls_per_magic": budgets.get("max_deepseek_calls_per_magic"),
                "max_probes_per_magic": budgets.get("max_probes_per_magic"),
                "max_tavily_live_per_magic": budgets.get("max_tavily_live_per_magic"),
            },
            "probes_today": usage_today.get("probe_calls") or 0,
        },
        "usage": {
            "vault": {
                "label": canonical.get("label") or "GDrive vault",
                "used_tb": vault_used,
                "cap_tb": vault_cap,
                "pct": vault_pct,
                "ok": desk.get("gdrive", {}).get("ok", True) is not False,
            },
            "hot": {
                "label": hot.get("label") or "NVMe hot desk",
                "used_pct": hot.get("used_pct"),
                "free_gb": hot.get("free_gb"),
                "headroom_ok": hot.get("headroom_ok", True) is not False,
            },
            "cache": {
                "label": cache.get("label") or "USB bulk cache",
                "mounted": cache.get("mounted", True) is not False,
                "used_gb": cache.get("used_gb"),
                "total_gb": cache.get("total_gb"),
                "pct": cache_pct,
            },
            "staging_disk_free_gb": desk.get("staging_disk_free_gb"),
        },
        "motion": {
            "jobs": jobs,
            "campaigns_active": campaigns_active,
            "gdelt": {
                "progress": desk.get("jobs", {}).get("gdelt_progress") or cq.get("gdelt_progress"),
                "ok_months": gdelt.get("ok_months"),
                "fleet_running": gdelt.get("fleet_running"),
            },
            "datacite": {
                "total_percent": dc.get("total_percent"),
                "total_progress": dc.get("total_progress"),
                "total_target": dc.get("total_target"),
                "y2025_percent": dc.get("y2025_percent"),
                "shard_workers": dh.get("running") or dh.get("active_workers"),
                "status": dh.get("status"),
            },
        },
        "compute": {
            "controller": cluster.get("controller") or desk.get("brain"),
            "windows_lab": {
                "busy": pools.get("busy"),
                "joined": wl.get("joined"),
                "total": pools.get("total") or wl.get("total"),
                "max_parallel": _cluster_max_parallel(repo_root),
            },
            "queue": {
                "open": cq.get("pending") or cq.get("queued") or cq.get("open"),
                "runnable_tasks": catalog.get("runnable_queue_tasks"),
                "total_tasks": catalog.get("queue_tasks"),
                "pipelines": catalog.get("pipelines"),
                "connectors": catalog.get("connectors"),
            },
        },
        "connect": {
            "source_count": source_count,
            "layer_count": layer_count,
        },
        "issues": issues,
        "issues_count": len(issues),
        "spending": {
            "period": period,
            "today": usage_today,
            "drivers": bq_drivers,
        },
        "activity": {
            "events": activity_events,
        },
    }
