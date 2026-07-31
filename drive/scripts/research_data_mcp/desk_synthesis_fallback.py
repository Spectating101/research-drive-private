#!/usr/bin/env python3
"""Read-only Gemini fallback for Synthesis reasoning.

Cursor Composer remains the primary desk brain because it can use the research
MCP tools. This fallback receives the deterministic Library grounding already
built by Research Drive and can only return prose. It cannot collect, execute,
materialise, register, or otherwise mutate platform state.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MAX_GEMINI_RESPONSE_BYTES = 2 * 1024 * 1024
SYNTHESIS_FALLBACK_HEALTH_TTL_SECONDS = 300

_LOCK = threading.Lock()
_LAST: dict[str, Any] = {}


class SynthesisFallbackError(RuntimeError):
    """Sanitised provider failure safe to expose in health artifacts."""

    def __init__(self, category: str, detail: str = "", *, status_code: int | None = None):
        self.category = str(category or "provider_error")
        safe_detail = str(detail or "")
        secret = _api_key()
        if secret:
            safe_detail = safe_detail.replace(secret, "[redacted]")
        self.detail = safe_detail[:240]
        self.status_code = status_code
        super().__init__(self.detail or self.category)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _api_key() -> str:
    return (
        os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
    )


def gemini_synthesis_enabled() -> bool:
    """Require explicit operator opt-in before sending research context off-host."""
    return os.getenv("DESK_SYNTHESIS_GEMINI_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def gemini_synthesis_configured() -> bool:
    return gemini_synthesis_enabled() and bool(_api_key())


def _model() -> str:
    return (
        os.getenv("DESK_SYNTHESIS_GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
        or DEFAULT_GEMINI_MODEL
    )


def _base_url() -> str:
    """Keep the credential-bound fallback on the audited provider endpoint."""
    return DEFAULT_GEMINI_BASE_URL


def _record(status: str, *, category: str | None = None) -> None:
    with _LOCK:
        _LAST.clear()
        _LAST.update(
            {
                "status": status,
                "verified": True,
                "checked_at": _utc_now(),
                "provider": "gemini",
                "model": _model(),
                "error_category": category,
            }
        )


def synthesis_fallback_runtime_status(
    *,
    max_age_seconds: int = SYNTHESIS_FALLBACK_HEALTH_TTL_SECONDS,
) -> dict[str, Any]:
    if not gemini_synthesis_enabled():
        return {
            "status": "disabled",
            "configured": False,
            "verified": False,
            "checked_at": None,
            "provider": "gemini",
            "model": _model(),
            "error_category": "disabled_by_policy",
        }
    configured = gemini_synthesis_configured()
    if not configured:
        return {
            "status": "unavailable",
            "configured": False,
            "verified": False,
            "checked_at": None,
            "provider": "gemini",
            "model": _model(),
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
            "provider": "gemini",
            "model": _model(),
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


def _error_from_http(exc: urllib.error.HTTPError) -> SynthesisFallbackError:
    status_code = int(getattr(exc, "code", 0) or 0) or None
    detail = ""
    try:
        payload = json.loads(exc.read().decode("utf-8", errors="replace"))
        detail = str((payload.get("error") or {}).get("message") or "")
    except Exception:
        detail = ""
    lowered = detail.lower()
    if status_code in {401, 403} or "api key not valid" in lowered:
        category = "authentication"
    elif status_code == 429:
        category = "rate_limited"
    elif status_code and status_code >= 500:
        category = "provider_internal"
    else:
        category = "provider_error"
    return SynthesisFallbackError(category, detail, status_code=status_code)


def _response_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        block_reason = str(
            ((payload.get("promptFeedback") or {}).get("blockReason") or "")
        ).strip()
        raise SynthesisFallbackError(
            "blocked" if block_reason else "empty_reply",
            block_reason or "Gemini returned no response candidate",
        )
    content = (candidates[0] or {}).get("content") or {}
    parts = content.get("parts") or []
    text = "".join(
        str(part.get("text") or "")
        for part in parts
        if isinstance(part, dict) and part.get("text")
    ).strip()
    if not text:
        raise SynthesisFallbackError("empty_reply", "Gemini returned no text")
    return text


def run_gemini_synthesis_turn(
    prompt: str,
    *,
    timeout_seconds: float = 90.0,
) -> tuple[str, dict[str, Any]]:
    """Return one grounded, read-only Synthesis reasoning turn."""
    if not gemini_synthesis_enabled():
        raise SynthesisFallbackError(
            "disabled_by_policy",
            "Gemini Synthesis fallback is not enabled by the operator",
        )
    api_key = _api_key()
    if not api_key:
        raise SynthesisFallbackError(
            "not_configured", "No Gemini API credential is configured"
        )

    model = _model()
    endpoint = f"{_base_url()}/models/{model}:generateContent"
    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": (
                        "You are the read-only reasoning fallback for Research Drive "
                        "Synthesis. Use only the supplied grounding and label proposed "
                        "choices and unknowns explicitly. Never claim to have collected, "
                        "executed, materialised, registered, or made data query-ready. "
                        "Return plain prose suitable for a research workspace."
                    )
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": str(prompt or "")[:120_000]}],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2400,
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=max(float(timeout_seconds), 1.0)) as response:
            raw = response.read(MAX_GEMINI_RESPONSE_BYTES + 1)
            if len(raw) > MAX_GEMINI_RESPONSE_BYTES:
                raise SynthesisFallbackError(
                    "response_too_large",
                    "Gemini response exceeded the bounded response limit",
                )
            body = json.loads(raw.decode("utf-8"))
        text = _response_text(body)
    except urllib.error.HTTPError as exc:
        error = _error_from_http(exc)
        _record("degraded", category=error.category)
        raise error from None
    except SynthesisFallbackError as exc:
        _record("degraded", category=exc.category)
        raise
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        category = "timeout" if isinstance(exc, TimeoutError) else "connection"
        _record("degraded", category=category)
        raise SynthesisFallbackError(category, str(exc)) from None

    _record("ready")
    return text, {
        "provider": "gemini",
        "model": model,
        "read_only": True,
        "grounding": "research_drive",
    }


def _reset_synthesis_fallback_runtime_status() -> None:
    """Test helper; production state resets with the desk process."""
    with _LOCK:
        _LAST.clear()
