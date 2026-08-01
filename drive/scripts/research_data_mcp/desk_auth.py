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


def request_is_https(handler: BaseHTTPRequestHandler | None) -> bool:
    """Whether the browser reached us over HTTPS, including via a tunnel."""
    if handler is None:
        return False
    proto = str(handler.headers.get("X-Forwarded-Proto") or "").strip().lower()
    if proto:
        return proto.split(",")[0].strip() == "https"
    return bool(getattr(handler, "_desk_tls", False))


def _cookie_header_value(
    token: str, *, clear: bool = False, secure: bool = False, max_age: int | None = None
) -> str:
    # Secure is set whenever the request arrived over HTTPS (public tunnels
    # terminate TLS and forward X-Forwarded-Proto). It is omitted on the plain
    # HTTP Tailscale front door, where setting it would silently drop the cookie.
    flags = "Path=/; HttpOnly; SameSite=Strict"
    if secure:
        flags += "; Secure"
    if clear:
        return f"{DESK_SESSION_COOKIE}=; {flags}; Max-Age=0"
    value = session_cookie_value(token)
    ttl = _session_max_age() if max_age is None else max_age
    return f"{DESK_SESSION_COOKIE}={value}; {flags}; Max-Age={ttl}"


def _session_max_age() -> int:
    """Bounded session lifetime. The cookie previously never expired."""
    raw = (os.getenv("DESK_SESSION_MAX_AGE_SECONDS") or "").strip()
    try:
        value = int(raw) if raw else 43200  # 12h
    except ValueError:
        value = 43200
    return max(300, min(value, 604800))


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


def _public_desk_origins() -> set[str]:
    """Browser origins (comma-separated) that may mint desk sessions.

    Defaults to EMPTY. It previously defaulted to a public hostname, which meant
    an unconfigured deploy handed privileged sessions to a public origin.
    """
    raw = (os.getenv("DESK_PUBLIC_ORIGINS") or "").strip()
    out: set[str] = set()
    for part in raw.split(","):
        item = part.strip().rstrip("/")
        if item:
            out.add(item.lower())
    return out


def _bootstrap_hosts() -> set[str]:
    """Host values permitted to mint a desk session without presenting a token.

    Empty by default: no host may mint anonymously. Set
    DESK_SESSION_BOOTSTRAP_HOSTS to the internal desk host (e.g. the Tailscale
    address) to restore the internal browser convenience there and nowhere else.
    """
    raw = (os.getenv("DESK_SESSION_BOOTSTRAP_HOSTS") or "").strip()
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def request_presents_desk_token(handler: BaseHTTPRequestHandler) -> bool:
    """True when the caller already proved possession of the desk token."""
    token = access_token_required()
    if not token:
        return False
    auth = str(handler.headers.get("Authorization") or "")
    header = str(handler.headers.get("X-Desk-Token") or "")
    provided = auth[7:].strip() if auth.startswith("Bearer ") else header.strip()
    return bool(provided) and _token_matches(provided, token)


def same_origin_desk_request(handler: BaseHTTPRequestHandler) -> bool:
    """Whether this request may mint a desk session.

    Same-origin is NOT authentication. An anonymous visitor loading a public
    desk is same-origin by definition, so origin-matching alone previously
    turned any visitor into an authorized session. Minting now requires one of:

      * possession of the desk token, or
      * an explicitly allow-listed Host (DESK_SESSION_BOOTSTRAP_HOSTS), or
      * an explicitly allow-listed Origin (DESK_PUBLIC_ORIGINS),

    and in the last two cases the request must still look like a browser call
    to this same desk.
    """
    if request_presents_desk_token(handler):
        return True

    host = str(handler.headers.get("Host") or "").strip().lower()
    host_only = host.split(":")[0]
    allowed_origins = _public_desk_origins()
    hosts = _bootstrap_hosts()
    host_allowed = bool(host) and (host in hosts or host_only in hosts)

    if not allowed_origins and not host_allowed:
        # Nothing is configured to mint anonymously — refuse.
        return False

    same_origin_values = {f"http://{host}", f"https://{host}"} if host else set()
    origin = str(handler.headers.get("Origin") or "").strip()
    referer = str(handler.headers.get("Referer") or "").strip()

    if origin:
        o = origin.rstrip("/").lower()
        if o in allowed_origins:
            return True
        return host_allowed and o in same_origin_values
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        r = f"{parsed.scheme}://{parsed.netloc}".lower()
        if r in allowed_origins:
            return True
        return host_allowed and r in same_origin_values
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
        return False, "Desk session bootstrap is not permitted for this request", None
    return True, "", _cookie_header_value(token, secure=request_is_https(handler))


def clear_desk_session(handler: BaseHTTPRequestHandler) -> tuple[bool, str, str | None]:
    token = access_token_required()
    if not token:
        # Still clear any stale cookie.
        return True, "", _cookie_header_value("", clear=True, secure=request_is_https(handler))
    if not same_origin_desk_request(handler):
        return False, "Desk session clear requires a same-origin browser request", None
    return True, "", _cookie_header_value(token, clear=True, secure=request_is_https(handler))


def authorize(handler: BaseHTTPRequestHandler, path: str, method: str = "GET") -> tuple[bool, str]:
    token = access_token_required()
    requires = path_requires_auth(path, method=method)
    if not token:
        # Fail closed. This previously returned True whenever no token was
        # configured, which opened every protected route -- including every
        # mutation -- on any host that lost its token configuration.
        if requires:
            return False, "Desk access token is not configured on this host; refusing protected request"
        return True, ""
    if not requires:
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
