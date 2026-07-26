"""Truthful health projection for Header, Settings, and Resources.

Derives one UI-facing desk_status from existing /health component facts.
Never labels the live desk as demo, and never marks degraded unless a
concrete component fact requires it (today: NVMe headroom failure or an
explicit status=degraded already set from facts).
"""

from __future__ import annotations

from typing import Any


def _gdrive_ok(gdrive: dict[str, Any] | None) -> bool | None:
    if not isinstance(gdrive, dict) or not gdrive:
        return None
    if gdrive.get("ok") is False or gdrive.get("ready") is False or gdrive.get("drive_list_ok") is False:
        return False
    if gdrive.get("ok") is True or gdrive.get("ready") is True or gdrive.get("drive_list_ok") is True:
        return True
    # Probe skipped / unknown — do not invent failure or success for chrome.
    if gdrive.get("probe_skipped") or gdrive.get("ready") is None:
        return None
    if gdrive.get("rclone_installed") or gdrive.get("drive_root"):
        return None
    return None


def build_health_projection(health: dict[str, Any] | None) -> dict[str, Any]:
    """Project Header/Settings/Resources desk status from /health facts only."""
    payload = health if isinstance(health, dict) else {}
    desk = payload.get("desk") if isinstance(payload.get("desk"), dict) else {}
    jobs = desk.get("jobs") if isinstance(desk.get("jobs"), dict) else {}
    tiers = desk.get("storage_tiers") if isinstance(desk.get("storage_tiers"), dict) else {}
    hot = tiers.get("hot") if isinstance(tiers.get("hot"), dict) else {}
    gdrive = desk.get("gdrive") if isinstance(desk.get("gdrive"), dict) else {}
    cluster = payload.get("cluster") if isinstance(payload.get("cluster"), dict) else {}

    datasets = payload.get("datasets")
    if datasets is None:
        datasets = cluster.get("registry_datasets")
    try:
        dataset_n = int(datasets or 0)
    except (TypeError, ValueError):
        dataset_n = 0

    composer_ok = desk.get("composer_configured") is True
    composer_status = str(desk.get("composer_status") or ("ready" if composer_ok else "needs_key"))
    gdrive_ok = _gdrive_ok(gdrive)
    hot_ok = hot.get("headroom_ok")
    pending = int(jobs.get("pending_approval") or 0)
    failed_recent = int(jobs.get("failed_recent") or 0)

    raw_status = str(payload.get("status") or "").strip().lower()
    # Live API never invents demo. Demo is an offline FE seed label only.
    if raw_status == "demo":
        # Preserve only if the payload itself was an explicit demo seed.
        status = "demo"
    elif raw_status == "degraded" or hot_ok is False:
        status = "degraded"
    elif raw_status in {"ok", "synced", ""}:
        status = "ok" if raw_status in {"ok", "synced", ""} else raw_status
    else:
        status = raw_status or "ok"

    if status == "demo":
        desk_status = "demo"
    elif status == "degraded":
        desk_status = "degraded"
    elif dataset_n <= 0 and status == "ok":
        desk_status = "empty"
    elif status == "ok":
        desk_status = "ok"
    else:
        desk_status = status if status in {"ok", "degraded", "empty", "syncing", "unknown"} else "unknown"

    components = {
        "api": {
            "ok": status in {"ok", "degraded", "empty", "demo"},
            "status": "ok" if status != "unknown" else "unknown",
        },
        "composer": {
            "ok": composer_ok,
            "status": composer_status if composer_ok else "needs_key",
            "brain": desk.get("brain"),
        },
        "gdrive": {
            "ok": gdrive_ok,
            "status": (
                "ready"
                if gdrive_ok is True
                else ("error" if gdrive_ok is False else ("pending" if gdrive else "unknown"))
            ),
        },
        "registry": {
            "ok": dataset_n > 0,
            "status": "ok" if dataset_n > 0 else "empty",
            "datasets": dataset_n,
        },
        "storage_hot": {
            "ok": False if hot_ok is False else (True if hot_ok is True else None),
            "status": "degraded" if hot_ok is False else ("ok" if hot_ok is True else "unknown"),
            "used_pct": hot.get("used_pct"),
            "free_gb": hot.get("free_gb"),
        },
        "jobs": {
            "ok": failed_recent <= 0,
            "status": "attention" if pending or failed_recent else "ok",
            "pending_approval": pending,
            "failed_recent": failed_recent,
        },
    }

    return {
        "desk_status": desk_status,
        "status": status if status != "demo" or raw_status == "demo" else status,
        "label": {
            "ok": "Live registry",
            "empty": "Empty registry",
            "degraded": "Desk degraded",
            "demo": "Demo catalog",
            "syncing": "Syncing…",
            "unknown": "Desk status unknown",
        }.get(desk_status, "Desk status unknown"),
        "components": components,
        "consumers": ["header", "settings", "resources"],
    }


def attach_health_projection(health: dict[str, Any]) -> dict[str, Any]:
    """Mutate and return health payload with a truthful projection attached."""
    if not isinstance(health, dict):
        return health
    projection = build_health_projection(health)
    health["projection"] = projection
    # Keep top-level status aligned with facts; never coerce live ok → demo.
    if projection["status"] in {"ok", "degraded"} and health.get("status") != "demo":
        health["status"] = projection["status"]
    return health
