#!/usr/bin/env python3
"""Desk scale helpers — discovery cache, I/O pressure, Composer SLA.

Product split:
  discovery rail  — search, probe, describe, light query (must feel instant)
  procurement rail — collect / yzu_submit_job (submit only; cluster does the work)
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Any

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()
_IO_SNAPSHOT: dict[str, Any] = {"sampled_at": 0.0, "data": {}}


def composer_sla_seconds() -> float:
    return max(15.0, float(os.environ.get("DESK_COMPOSER_SLA_SECONDS", "90")))


def search_cache_ttl_seconds() -> float:
    return max(5.0, float(os.environ.get("DESK_SEARCH_CACHE_TTL", "45")))


def search_cache_enabled() -> bool:
    return os.environ.get("DESK_SEARCH_CACHE", "1") not in {"0", "false", "no"}


def _cache_key(kind: str, query: str, **parts: Any) -> str:
    extras = "|".join(f"{k}={parts[k]}" for k in sorted(parts))
    return f"{kind}:{query.strip().lower()}|{extras}"


def get_search_cache(kind: str, query: str, **parts: Any) -> dict[str, Any] | None:
    if not search_cache_enabled() or not query.strip():
        return None
    key = _cache_key(kind, query, **parts)
    ttl = search_cache_ttl_seconds()
    now = time.monotonic()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if not hit:
            return None
        ts, payload = hit
        if now - ts > ttl:
            _CACHE.pop(key, None)
            return None
        out = dict(payload)
        out["cache_hit"] = True
        out["cache_age_seconds"] = round(now - ts, 2)
        return out


def set_search_cache(kind: str, query: str, payload: dict[str, Any], **parts: Any) -> None:
    if not search_cache_enabled() or not query.strip():
        return
    key = _cache_key(kind, query, **parts)
    with _CACHE_LOCK:
        if len(_CACHE) > 256:
            oldest = min(_CACHE.items(), key=lambda item: item[1][0])[0]
            _CACHE.pop(oldest, None)
        _CACHE[key] = (time.monotonic(), dict(payload))


def cache_stats() -> dict[str, Any]:
    with _CACHE_LOCK:
        return {"entries": len(_CACHE), "ttl_seconds": search_cache_ttl_seconds(), "enabled": search_cache_enabled()}


def io_pressure_sample(*, refresh: bool = False) -> dict[str, Any]:
    """Lightweight host signal — disk-sleep procs + load average."""
    global _IO_SNAPSHOT
    now = time.monotonic()
    if not refresh and now - float(_IO_SNAPSHOT.get("sampled_at") or 0) < 8.0:
        return dict(_IO_SNAPSHOT.get("data") or {})

    data: dict[str, Any] = {"pressure": "unknown", "disk_sleep_procs": 0, "load_1m": 0.0}
    try:
        load = open("/proc/loadavg", encoding="utf-8").read().split()
        data["load_1m"] = float(load[0])
        data["load_5m"] = float(load[1])
        ps = subprocess.run(
            ["ps", "-eo", "state"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        d_count = sum(1 for line in (ps.stdout or "").splitlines() if line.strip().startswith("D"))
        data["disk_sleep_procs"] = d_count
        gdelt_procs = 0
        pg = subprocess.run(
            ["pgrep", "-f", "gdelt_gkg_expanded|build_gdelt_crypto|gzip -t"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if pg.stdout:
            gdelt_procs = len([ln for ln in pg.stdout.splitlines() if ln.strip()])
        data["gdelt_io_procs"] = gdelt_procs
        high = d_count >= 2 or gdelt_procs >= 3 or data["load_1m"] >= max(8.0, (os.cpu_count() or 4) * 1.5)
        data["pressure"] = "high" if high else "ok"
    except Exception as exc:  # noqa: BLE001
        data["error"] = str(exc)[:120]

    _IO_SNAPSHOT = {"sampled_at": now, "data": data}
    return dict(data)


def io_pressure_high() -> bool:
    return io_pressure_sample().get("pressure") == "high"


def search_budget_multiplier() -> float:
    """Shrink interactive search budgets when the host is I/O saturated."""
    if io_pressure_high():
        return float(os.environ.get("DESK_SEARCH_BUDGET_IO_PRESSURE_MULT", "0.65"))
    return 1.0


DISCOVERY_RAIL = ("probe", "search", "status", "describe", "query")
PROCUREMENT_RAIL = ("submit_collect", "submit_job")


def scale_status() -> dict[str, Any]:
    return {
        "composer_sla_seconds": composer_sla_seconds(),
        "search_cache": cache_stats(),
        "io": io_pressure_sample(),
        "search_budget_multiplier": search_budget_multiplier(),
        "discovery_rail": list(DISCOVERY_RAIL),
        "procurement_rail": list(PROCUREMENT_RAIL),
        "fast_paths": list(DISCOVERY_RAIL),  # legacy key — discovery only
        "env": {
            "DESK_UNIFIED_SEARCH_BUDGET": os.environ.get("DESK_UNIFIED_SEARCH_BUDGET", "8"),
            "DESK_DATACITE_PREFETCH_BUDGET": os.environ.get("DESK_DATACITE_PREFETCH_BUDGET", "6"),
            "DESK_DATACITE_MAX_SHARD_SCANS": os.environ.get("DESK_DATACITE_MAX_SHARD_SCANS", "4"),
        },
    }
