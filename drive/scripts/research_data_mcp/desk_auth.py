#!/usr/bin/env python3
"""Optional shared-secret gate for desk write operations."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

DESK_SESSION_COOKIE = "rd_desk_session"
_SESSION_MSG = b"research-drive-desk-session-v1"
_DEFAULT_SESSION_MAX_AGE = 86_400
_DEFAULT_ALLOWED_ORIGINS = (
    "http://100.127.141.44:8767",
    "http://127.0.0.1:5178",
    "http://127.0.0.1:4178",
)


def access_token_required() -> str | None:
    return (os.getenv("YZU_DESK_ACCESS_TOKEN") or os.getenv("DESK_ACCESS_TOKEN") or "").strip() or None


def session_max_age_seconds() -> int:
    raw = (os.getenv("YZU_DESK_SESSION_MAX_AGE_SECONDS") or "").strip()
    try:
        age = int(raw) if raw else _DEFAULT_SESSION_MAX_AGE
    except ValueError:
        age = _DEFAULT_SESSION_MAX_AGE
    return max(300, min(age, 7 * 86_400))


def desk_allowed_origins() -> set[str]:
    raw = (os.getenv("YZU_DESK_ALLOWED_ORIGINS") or "").strip()
    configured = {item.strip().rstrip("/") for item in raw.split(",") if item.strip()}
    defaults = {item.rstrip("/") for item in _DEFAULT_ALLOWED_ORIGINS}
    return configured | defaults


def path_requires_auth(path: str) -> bool:
    if path in {
        "/library/chat",
        "/library/chat/stream",
        "/library/jobs",
        "/library/jobs/approve-safe",
        "/library/discover/collect",
        "/library/discover/sources/preview",
        "/library/archive",
        "/library/desk/warm",
        "/library/datacite/collect",
        "/library/datacite/enrich",
        "/library/synthesis/run",
        "/library/synthesis/pair",
        "/yzu/jobs",
        "/yzu/jobs/approve-safe",
    }:
        return True
    if path.startswith("/library/discover/intents"):
        return True
    if path.startswith("/library/discover/subscriptions"):
        return True
    if path.startswith("/library/synthesis/threads/") and path.rsplit("/", 1)[-1] in {
        "patches",
        "proposal",
        "execute",
        "conversation",
    }:
        return True
    if path.startswith("/library/licenses/"):
        return True
    if path.startswith("/library/jobs/") and path.rsplit("/", 1)[-1] in {"approve", "cancel"}:
        return True
    if path.startswith("/yzu/schedules/") and path.endswith("/run"):
        return True
    if path.startswith("/yzu/jobs/") and path.rsplit("/", 1)[-1] in {"approve", "cancel"}:
        return True
    if path.startswith("/library/campaigns/") and path.rsplit("/", 1)[-1] in {
        "approve-collect",
        "resume",
        "add-datacite",
    }:
        return True
    return False


def _session_signature(token: str, expires_at: int) -> str:
    payload = f"{_SESSION_MSG.decode()}:{expires_at}".encode("utf-8")
    return hmac.new(token.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def session_cookie_value(token: str, *, expires_at: int | None = None) -> str:
    exp = expires_at if expires_at is not None else int(time.time()) + session_max_age_seconds()
    return f"v2.{exp}.{_session_signature(token, exp)}"


def _cookie_header_value(token: str, *, clear: bool = False) -> str:
    if clear:
        return f"{DESK_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
    max_age = session_max_age_seconds()
    value = session_cookie_value(token)
    # Tailscale-internal front door is HTTP today — omit Secure.
    return f"{DESK_SESSION_COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"


def read_desk_session_cookie(handler: BaseHTTPRequestHandler) -> str:
    raw = str(handler.headers.get("Cookie") or "")
    if not raw:
        return ""
    jar = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return ""
    morsel = jar.get(DESK_SESSION_COOKIE)
    if not morsel:
        return ""
    return str(morsel.value or "").strip()


def desk_session_cookie_valid(handler: BaseHTTPRequestHandler, token: str) -> bool:
    got = read_desk_session_cookie(handler)
    if not got or not token:
        return False
    parts = got.split(".")
    if len(parts) != 3 or parts[0] != "v2":
        return False
    try:
        expires_at = int(parts[1])
    except ValueError:
        return False
    if expires_at <= int(time.time()):
        return False
    return hmac.compare_digest(parts[2], _session_signature(token, expires_at))


def _request_has_token_auth(handler: BaseHTTPRequestHandler) -> bool:
    token = access_token_required()
    if not token:
        return False
    auth = str(handler.headers.get("Authorization") or "")
    header = str(handler.headers.get("X-Desk-Token") or "")
    if auth.startswith("Bearer ") and auth[7:].strip() == token:
        return True
    return header.strip() == token


def same_origin_desk_request(handler: BaseHTTPRequestHandler) -> bool:
    """Allow session bootstrap only for configured browser origins or token auth."""

    if _request_has_token_auth(handler):
        return True

    origin = str(handler.headers.get("Origin") or "").strip().rstrip("/")
    referer = str(handler.headers.get("Referer") or "").strip()
    if not origin and not referer:
        return False

    allowed = desk_allowed_origins()
    if origin:
        return origin in allowed
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        return f"{parsed.scheme}://{parsed.netloc}".lower().rstrip("/") in allowed
    return False


def issue_desk_session(handler: BaseHTTPRequestHandler) -> tuple[bool, str, str | None]:
    """Return (ok, message, Set-Cookie header value)."""
    token = access_token_required()
    if not token:
        return False, "Desk access token is not configured on this host", None
    if not same_origin_desk_request(handler):
        return False, "Desk session bootstrap requires an allowed browser origin or desk token", None
    return True, "", _cookie_header_value(token)


def clear_desk_session(handler: BaseHTTPRequestHandler) -> tuple[bool, str, str | None]:
    token = access_token_required()
    if not token:
        # Still clear any stale cookie.
        return True, "", _cookie_header_value("", clear=True)
    if not same_origin_desk_request(handler):
        return False, "Desk session clear requires an allowed browser origin or desk token", None
    return True, "", _cookie_header_value(token, clear=True)


def authorize(handler: BaseHTTPRequestHandler, path: str) -> tuple[bool, str]:
    token = access_token_required()
    if not token or not path_requires_auth(path):
        return True, ""
    auth = str(handler.headers.get("Authorization") or "")
    header = str(handler.headers.get("X-Desk-Token") or "")
    if auth.startswith("Bearer ") and auth[7:].strip() == token:
        return True, ""
    if header.strip() == token:
        return True, ""
    if desk_session_cookie_valid(handler, token):
        return True, ""
    return False, "Desk access token required (set Authorization: Bearer or X-Desk-Token)"
