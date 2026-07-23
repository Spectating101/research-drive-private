#!/usr/bin/env python3
"""Optional shared-secret gate for desk write operations."""

from __future__ import annotations

import hashlib
import hmac
import os
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

DESK_SESSION_COOKIE = "rd_desk_session"
_SESSION_MSG = b"research-drive-desk-session-v1"


def access_token_required() -> str | None:
    return (os.getenv("YZU_DESK_ACCESS_TOKEN") or os.getenv("DESK_ACCESS_TOKEN") or "").strip() or None


def path_requires_auth(path: str, method: str = "GET") -> bool:
    method_u = (method or "GET").upper()
    if path == "/library/desk/session":
        return False
    if path in {"/healthz", "/api/health", "/"}:
        return False
    # Fail-closed: every mutating desk/cluster route needs the desk token.
    if method_u in {"POST", "PUT", "PATCH", "DELETE"} and (
        path.startswith("/library/") or path.startswith("/yzu/")
    ):
        return True
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


def session_cookie_value(token: str) -> str:
    digest = hmac.new(token.encode("utf-8"), _SESSION_MSG, hashlib.sha256).hexdigest()
    return f"v1.{digest}"


def _cookie_header_value(token: str, *, clear: bool = False) -> str:
    if clear:
        return f"{DESK_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
    value = session_cookie_value(token)
    # Tailscale-internal front door is HTTP today — omit Secure.
    return f"{DESK_SESSION_COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict"


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
    return hmac.compare_digest(got, session_cookie_value(token))


def same_origin_desk_request(handler: BaseHTTPRequestHandler) -> bool:
    """Allow session bootstrap only for same-origin browser calls to this desk."""
    host = str(handler.headers.get("Host") or "").strip().lower()
    if not host:
        return False
    origin = str(handler.headers.get("Origin") or "").strip()
    referer = str(handler.headers.get("Referer") or "").strip()
    allowed = {f"http://{host}", f"https://{host}"}
    if origin:
        return origin.rstrip("/") in allowed
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        return f"{parsed.scheme}://{parsed.netloc}".lower() in allowed
    # No Origin/Referer → refuse bootstrap (blocks curl/script session minting).
    return False


def _token_matches(provided: str, expected: str) -> bool:
    a = provided.encode("utf-8")
    b = expected.encode("utf-8")
    if len(a) != len(b):
        hmac.compare_digest(b, b)  # constant work
        return False
    return hmac.compare_digest(a, b)


def issue_desk_session(handler: BaseHTTPRequestHandler) -> tuple[bool, str, str | None]:
    """Return (ok, message, Set-Cookie header value)."""
    token = access_token_required()
    if not token:
        return False, "Desk access token is not configured on this host", None
    if not same_origin_desk_request(handler):
        return False, "Desk session bootstrap requires a same-origin browser request", None
    return True, "", _cookie_header_value(token)


def clear_desk_session(handler: BaseHTTPRequestHandler) -> tuple[bool, str, str | None]:
    token = access_token_required()
    if not token:
        # Still clear any stale cookie.
        return True, "", _cookie_header_value("", clear=True)
    if not same_origin_desk_request(handler):
        return False, "Desk session clear requires a same-origin browser request", None
    return True, "", _cookie_header_value(token, clear=True)


def authorize(handler: BaseHTTPRequestHandler, path: str, method: str = "GET") -> tuple[bool, str]:
    token = access_token_required()
    if not token or not path_requires_auth(path, method=method):
        return True, ""
    auth = str(handler.headers.get("Authorization") or "")
    header = str(handler.headers.get("X-Desk-Token") or "")
    provided = ""
    if auth.startswith("Bearer "):
        provided = auth[7:].strip()
    elif header.strip():
        provided = header.strip()
    if provided and _token_matches(provided, token):
        return True, ""
    if desk_session_cookie_valid(handler, token):
        return True, ""
    return False, "Desk access token required (set Authorization: Bearer or X-Desk-Token)"
