#!/usr/bin/env python3
"""Process-local truth about whether Composer has actually completed a call."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

_LOCK = threading.Lock()
_LAST: dict[str, Any] = {}
COMPOSER_HEALTH_TTL_SECONDS = 300


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_category(detail: Any) -> str:
    text = str(detail or "").strip().lower()
    if "internal" in text:
        return "provider_internal"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "rate" in text or "429" in text:
        return "rate_limited"
    if "auth" in text or "unauthorized" in text or "forbidden" in text:
        return "authentication"
    if "empty" in text or "no final" in text:
        return "empty_reply"
    if "connection" in text or "network" in text:
        return "connection"
    if "contract_violation" in text:
        return "contract_violation"
    return "provider_error"


def record_composer_success(*, model: str = "") -> None:
    with _LOCK:
        _LAST.clear()
        _LAST.update(
            {
                "status": "ready",
                "verified": True,
                "checked_at": _utc_now(),
                "model": str(model or ""),
                "error_category": None,
            }
        )


def record_composer_failure(detail: Any, *, model: str = "") -> None:
    with _LOCK:
        _LAST.clear()
        _LAST.update(
            {
                "status": "degraded",
                "verified": True,
                "checked_at": _utc_now(),
                "model": str(model or ""),
                "error_category": _error_category(detail),
            }
        )


def composer_runtime_status(
    *,
    configured: bool,
    max_age_seconds: int = COMPOSER_HEALTH_TTL_SECONDS,
) -> dict[str, Any]:
    if not configured:
        return {
            "status": "unavailable",
            "configured": False,
            "verified": False,
            "checked_at": None,
            "model": "",
            "error_category": "not_configured",
        }
    with _LOCK:
        latest = dict(_LAST)
    if not latest:
        return {
            "status": "unverified",
            "configured": True,
            "verified": False,
            "checked_at": None,
            "model": "",
            "error_category": None,
        }
    checked_at = str(latest.get("checked_at") or "")
    try:
        checked = datetime.fromisoformat(checked_at)
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        age_seconds = max(
            0, int((datetime.now(timezone.utc) - checked).total_seconds())
        )
    except (TypeError, ValueError):
        age_seconds = max(0, int(max_age_seconds)) + 1
    latest["age_seconds"] = age_seconds
    if age_seconds > max(0, int(max_age_seconds)):
        latest["status"] = "stale"
        latest["verified"] = False
        latest["error_category"] = "stale_observation"
    latest["configured"] = True
    return latest


def _reset_composer_runtime_status() -> None:
    """Test helper; production state naturally resets with the desk process."""
    with _LOCK:
        _LAST.clear()
