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



def _curated_connect_payload(repo_root: Path, *, gateway: Any | None = None) -> dict[str, Any]:
    """Honest Connect panel: curated desk sources + execution mode, not bare counts."""
    path = repo_root / "config/desk_sources.json"
    layers: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        for layer in data.get("layers") or []:
            if isinstance(layer, dict):
                layers.append(
                    {
                        "id": layer.get("id"),
                        "label": layer.get("label") or layer.get("id"),
                    }
                )
        # Live capability probes we can assert cheaply.
        bq_ok = False
        hf_ok = False
        try:
            if gateway is not None:
                from scripts.research_data_mcp import bigquery_client

                bq_ok = bigquery_client.status().get("credentials") == "available"
                profiles = gateway.list_credential_profiles().get("profiles") or []
                hf_ok = any(p.get("id") == "huggingface" and p.get("configured") for p in profiles)
        except Exception:
            pass

        LIVE_QUERYABLE = {
            "gdelt": "local_query",
            "sec_edgar": "local_query",
            "datacite": "api_live",
            "bigquery": "api_live" if bq_ok else "needs_credentials",
            "huggingface": "api_live" if hf_ok else "needs_credentials",
            "yfinance": "queue",
        }
        LICENSED = {"lseg_edp", "wrds", "crsp_moveit", "capital_iq"}
        AI_ASSISTED = {"web_generic", "open_research", "reddit"}

        # Licensed-seat evidence from access scope + Refinitiv probe artifacts.
        seat_status: dict[str, dict[str, Any]] = {}
        try:
            access_path = None
            for rel in (
                "docs/status/generated/databank_access_scope.json",
                "drive/docs/status/generated/databank_access_scope.json",
                "config/databank_access_scope.json",
                "drive/config/databank_access_scope.json",
            ):
                cand = repo_root / rel
                if cand.is_file():
                    access_path = cand
                    break
            if access_path is not None:
                access_doc = json.loads(access_path.read_text(encoding="utf-8"))
                for row in access_doc.get("sources") or []:
                    sid = str(row.get("source_id") or row.get("id") or "")
                    if "wrds" in sid:
                        seat_status["wrds"] = {
                            "state": "seat_unavailable",
                            "note": str(row.get("notes") or "WRDS credentials do not authenticate on this desk"),
                        }
                    if "capital" in sid or "compustat" in sid:
                        seat_status["capital_iq"] = {
                            "state": "manual_export",
                            "note": str(row.get("notes") or "Manual / scripted export path"),
                        }
            probe_path = None
            for rel in (
                "docs/status/generated/refinitiv_entitlement_probe.json",
                "drive/docs/status/generated/refinitiv_entitlement_probe.json",
            ):
                cand = repo_root / rel
                if cand.is_file():
                    probe_path = cand
                    break
            if probe_path is not None:
                probe = json.loads(probe_path.read_text(encoding="utf-8"))
                summary = probe.get("summary") or probe.get("entitlement_summary") or {}
                if summary.get("all_ok") is True or int(summary.get("tiers_ok") or 0) > 0:
                    seat_status["lseg_edp"] = {
                        "state": "entitled",
                        "note": f"Refinitiv probe tiers_ok={summary.get('tiers_ok')}/{summary.get('tiers_total')}",
                        "probe": summary,
                    }
                else:
                    seat_status["lseg_edp"] = {
                        "state": "seat_unverified",
                        "note": "Refinitiv entitlement probe present but not all_ok",
                        "probe": summary,
                    }
            # CRSP MOVEit follows licensed path when configured in desk sources.
            seat_status.setdefault(
                "crsp_moveit",
                {"state": "licensed_path", "note": "MOVEit institutional transfer path"},
            )
        except Exception:
            pass

        for src in data.get("sources") or []:
            if not isinstance(src, dict):
                continue
            if src.get("show_on_resources") is False:
                continue
            sid = str(src.get("id") or "")
            collect = src.get("collect_via") or []
            if isinstance(collect, str):
                collect = [collect]
            seat = seat_status.get(sid)
            if sid in LICENSED:
                state = str((seat or {}).get("state") or "licensed_seat")
                mode = {
                    "entitled": "licensed_entitled",
                    "seat_unavailable": "licensed_unavailable",
                    "manual_export": "licensed_manual",
                    "licensed_path": "licensed_seat",
                    "seat_unverified": "licensed_seat",
                }.get(state, "licensed_seat")
            elif sid in AI_ASSISTED:
                mode = "ai_assisted"
            elif sid in LIVE_QUERYABLE:
                mode = LIVE_QUERYABLE[sid]
            elif "pipeline" in collect or "queue" in collect or "http_manifest" in collect:
                mode = "automated_collect"
            else:
                mode = "configured"
            row_out = {
                "id": sid,
                "label": src.get("label") or sid,
                "collect_via": collect,
                "routes": src.get("routes"),
                "layers": src.get("layers") or [],
                "execution_mode": mode,
                "show_on_resources": bool(src.get("show_on_resources", True)),
            }
            if seat:
                row_out["entitlement"] = seat
            elif mode == "needs_credentials":
                row_out["entitlement"] = {
                    "state": "credentials_missing",
                    "note": "Route exists but desk credentials are not configured.",
                }
            sources.append(row_out)
    # Always include show_on_resources=false? No — resources panel is professor-facing.
    # But count all curated sources for honesty.
    total_configured = 0
    if path.is_file():
        try:
            total_configured = len(json.loads(path.read_text(encoding="utf-8")).get("sources") or [])
        except Exception:
            total_configured = len(sources)
    return {
        "source_count": len(sources) or 9,
        "layer_count": len(layers) or 9,
        "configured_source_count": total_configured or len(sources),
        "layers": layers,
        "sources": sources,
        "semantics": {
            "local_query": "Bytes on desk — queryable now",
            "api_live": "Live API with credentials",
            "needs_credentials": "Configured route; credentials missing",
            "licensed_seat": "Institutional seat / entitlement required",
            "licensed_entitled": "Institutional seat verified by entitlement probe",
            "licensed_unavailable": "Seat documented but credentials do not authenticate",
            "licensed_manual": "Licensed source via manual/scripted export",
            "automated_collect": "Queue/pipeline/http_manifest collect",
            "ai_assisted": "Discover/Ask/probe path — not a silent instant connector",
            "configured": "Route declared in desk_sources",
        },
    }



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
    runtime = gateway.orchestrator.runtime_health()
    runtime_cluster = runtime.get("cluster") or {}
    runtime_desk = runtime.get("desk") or {}
    runtime_workers = list(runtime_cluster.get("workers") or [])
    runtime_usage = runtime_cluster.get("usage") or {}
    runtime_runs = runtime_desk.get("jobs") or {}
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
    actionable = jobs.get("actionable") if isinstance(jobs.get("actionable"), dict) else {}
    failed_recent = int(jobs.get("failed_recent") or actionable.get("failed_recent") or 0)
    failed_actionable = int(jobs.get("failed_actionable") or actionable.get("failed_actionable") or failed_recent)
    failed_ops_noise = int(jobs.get("failed_ops_noise") or actionable.get("failed_ops_noise") or 0)
    days = int(jobs.get("recent_days") or actionable.get("failed_recent_days") or 7)
    if failed_actionable > 0:
        _issue(
            "jobs-failed-recent",
            f"{failed_actionable} actionable failed job(s) in last {days}d"
            + (f" ({failed_ops_noise} ops/canary quarantined)" if failed_ops_noise else ""),
            "motion",
        )
    elif failed_ops_noise > 0:
        _issue(
            "jobs-ops-noise",
            f"{failed_ops_noise} ops/canary failed job(s) in last {days}d (non-blocking)",
            "motion",
        )
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

    # Honest collector counts: inventory joined ≠ heartbeat online/idle.
    worker_online = worker_idle = worker_stale = worker_unseen = 0
    worker_joined = int(wl.get("joined") or 0) if wl.get("joined") is not None else None
    try:
        honesty = gateway.yzu.workers(live=False)
        for node in honesty.get("windows_lab") or []:
            st = str(node.get("status") or "").strip().lower()
            if st == "online":
                worker_online += 1
            elif st == "idle":
                worker_idle += 1
            elif st == "stale":
                worker_stale += 1
            elif st in {"joined_unseen", "joined"}:
                worker_unseen += 1
        if worker_joined is None:
            worker_joined = worker_online + worker_idle + worker_stale + worker_unseen
    except Exception:
        pass
    worker_available = worker_online + worker_idle
    worker_busy = runtime_desk.get("worker_pools", {}).get("busy")
    if worker_busy is None:
        worker_busy = pools.get("busy") if pools.get("busy") is not None else 0
    worker_total = runtime_desk.get("worker_pools", {}).get(
        "total",
        pools.get("total") if pools.get("total") is not None else wl.get("total"),
    )

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
                "busy": worker_busy,
                "total": worker_total,
                "online": worker_online,
                "idle": worker_idle,
                "stale": worker_stale,
                "joined": worker_joined,
                "available": worker_available,
                "joined_unseen": worker_unseen,
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
            "desk_session_cookie": bool(desk.get("desk_session_cookie")),
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
            "runtime_runs": runtime_runs,
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
                "busy": worker_busy,
                "joined": worker_joined if worker_joined is not None else wl.get("joined"),
                "total": worker_total,
                "online": worker_online,
                "idle": worker_idle,
                "stale": worker_stale,
                "available": worker_available,
                "max_parallel": _cluster_max_parallel(repo_root),
            },
            "queue": {
                "open": cq.get("pending") or cq.get("queued") or cq.get("open"),
                "runnable_tasks": catalog.get("runnable_queue_tasks"),
                "total_tasks": catalog.get("queue_tasks"),
                "pipelines": catalog.get("pipelines"),
                "connectors": catalog.get("connectors"),
            },
            "runtime": {
                "workers": runtime_workers,
                "worker_pools": runtime_desk.get("worker_pools") or {},
                "runs": runtime_runs,
                "usage": runtime_usage,
            },
        },
        # Canonical runtime truth is additive: existing Resources cards retain
        # their legacy compatibility fields while new consumers can render
        # freshness, reservations, usage, and lifecycle facts directly.
        "runtime": runtime,
        "connect": _curated_connect_payload(repo_root, gateway=gateway),
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
