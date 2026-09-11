#!/usr/bin/env python3
"""Optional shared-secret gate for desk write operations."""

from __future__ import annotations

import hashlib
import hmac
import base64
import contextvars
import json
import os
import secrets
import time
from contextlib import contextmanager
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from scripts.research_data_mcp.desk_principal import (
    DeskPrincipal,
    configured_principals,
    default_principal,
    member_access_codes_configured,
    permissions_document,
    principal_by_id,
    principal_for_token,
    new_public_guest_principal,
)
from scripts.research_data_mcp.cloudflare_access import (
    configured_access as cloudflare_access_configured,
    principal_from_request as cloudflare_access_principal,
)

DESK_SESSION_COOKIE = "rd_desk_session"
_SESSION_MSG = b"research-drive-desk-session-v1"
_SESSION_VERSION = "v3"
# v4 carries the small, verified public-member identity minted after a
# Cloudflare Access login.  v3 intentionally only names a locally configured
# principal (or a guest); it cannot restore an Access identity after the
# browser leaves the single protected login endpoint.
_MEMBER_SESSION_VERSION = "v4"
_LEGACY_SESSION_VERSION = "v2"
_CLOCK_SKEW_SECONDS = 300
_CURRENT_PRINCIPAL: contextvars.ContextVar[DeskPrincipal | None] = contextvars.ContextVar(
    "research_drive_principal", default=None
)

_PUBLIC_PATHS = {
    "/",
    "/healthz",
    "/library/desk/session",
    "/library/desk/capabilities",
}
_PROTECTED_API_PREFIXES = ("/health", "/datasets", "/query", "/library", "/yzu")


def access_token_required() -> str | None:
    return (os.getenv("YZU_DESK_ACCESS_TOKEN") or os.getenv("DESK_ACCESS_TOKEN") or "").strip() or None


def _session_signing_secret() -> str:
    return str(os.getenv("YZU_DESK_SESSION_SIGNING_SECRET") or access_token_required() or "").strip()


def desk_auth_configured() -> bool:
    return bool(cloudflare_access_configured()) or bool(
        _session_signing_secret()
        and (access_token_required() or configured_principals())
    )


def current_desk_principal() -> DeskPrincipal | None:
    return _CURRENT_PRINCIPAL.get()


@contextmanager
def desk_principal_context(principal: DeskPrincipal | None):
    """Temporarily bind an authenticated principal for storage-level checks."""
    token = _CURRENT_PRINCIPAL.set(principal)
    try:
        yield principal
    finally:
        _CURRENT_PRINCIPAL.reset(token)


def path_requires_auth(path: str, method: str = "GET") -> bool:
    if path == "/api":
        path = "/"
    elif path.startswith("/api/"):
        path = path[4:]
    method_u = (method or "GET").upper()
    if path in _PUBLIC_PATHS:
        return False
    is_api = any(path == prefix or path.startswith(f"{prefix}/") for prefix in _PROTECTED_API_PREFIXES)
    if not is_api:
        return False
    if method_u in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}:
        return True
    return False


def required_permission(path: str, method: str = "GET") -> str:
    """Conservative route-family role requirement for authenticated callers."""
    if path == "/api":
        path = "/"
    elif path.startswith("/api/"):
        path = path[4:]
    method_u = str(method or "GET").upper()
    # Account identity is immutable here; this permission controls only the
    # authenticated researcher's principal-scoped research-context profile.
    if path.rstrip("/") == "/library/profile":
        return "manage_research_profile"
    # Ask and Synthesis hold private, durable researcher context. They need
    # `use_ask` for reads as well as writes; do this before the generic GET
    # rule below so a guest cannot retrieve an addressable saved session.
    if path.startswith(("/library/chat", "/library/advise")):
        return "use_ask"
    if path.startswith("/library/desk/warm"):
        return "use_ask"
    if path.startswith("/library/synthesis/threads") and not path.endswith(
        ("/execute", "/collect-missing")
    ):
        return "use_ask"
    if path == "/health" or path.startswith(("/library/desk/resources", "/library/desk/brief")):
        return "view_operations"
    if method_u in {"GET", "HEAD"}:
        if path.startswith("/yzu") or path.startswith(
            ("/library/ops", "/library/credentials", "/library/campaigns")
        ):
            return "view_operations"
        if path.startswith("/library/jobs"):
            return "view_research_data"
        if path.startswith("/library/faculty"):
            return "view_faculty_profile"
        return "view_research_data"
    if method_u == "POST" and path.rstrip("/") == "/library/jobs":
        return "submit_collection"
    if path.startswith("/yzu") or path.startswith(
        ("/library/jobs", "/library/campaigns", "/library/credentials")
    ):
        return "approve_jobs"
    return "submit_collection"


def _session_signature(token: str, payload: str) -> str:
    message = _SESSION_MSG + b"\0" + payload.encode("utf-8")
    return hmac.new(token.encode("utf-8"), message, hashlib.sha256).hexdigest()


def session_cookie_value(
    token: str,
    *,
    issued_at: int | None = None,
    nonce: str | None = None,
    principal: DeskPrincipal | None = None,
) -> str:
    issued = int(time.time()) if issued_at is None else int(issued_at)
    entropy = nonce or secrets.token_urlsafe(18)
    actor = principal or default_principal()
    claims_document: dict[str, str] = {"sub": actor.principal_id}
    version = _SESSION_VERSION
    if actor.role == "public_member" and actor.principal_id.startswith("cf-"):
        version = _MEMBER_SESSION_VERSION
        claims_document.update(
            {
                "email": actor.email,
                "display_name": actor.display_name,
                "role": "public_member",
            }
        )
    claims = base64.urlsafe_b64encode(
        json.dumps(claims_document, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    payload = f"{version}.{issued}.{entropy}.{claims}"
    return f"{payload}.{_session_signature(token, payload)}"


def request_is_https(handler: BaseHTTPRequestHandler | None) -> bool:
    if handler is None:
        return False
    proto = str(handler.headers.get("X-Forwarded-Proto") or "").strip().lower()
    if proto:
        return proto.split(",")[0].strip() == "https"
    return bool(getattr(handler, "_desk_tls", False))


def _cookie_header_value(
    token: str,
    *,
    clear: bool = False,
    secure: bool = False,
    max_age: int | None = None,
    principal: DeskPrincipal | None = None,
) -> str:
    flags = "Path=/; HttpOnly; SameSite=Strict"
    if secure:
        flags += "; Secure"
    if clear:
        return f"{DESK_SESSION_COOKIE}=; {flags}; Max-Age=0"
    value = session_cookie_value(token, principal=principal)
    ttl = _session_max_age() if max_age is None else max_age
    return f"{DESK_SESSION_COOKIE}={value}; {flags}; Max-Age={ttl}"


def _session_max_age() -> int:
    raw = (os.getenv("DESK_SESSION_MAX_AGE_SECONDS") or "").strip()
    try:
        value = int(raw) if raw else 43200
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
    return desk_session_principal(handler, token) is not None


def desk_session_principal(
    handler: BaseHTTPRequestHandler, token: str
) -> DeskPrincipal | None:
    got = read_desk_session_cookie(handler)
    if not got or not token:
        return None
    parts = got.split(".")
    if len(parts) == 4 and parts[0] == _LEGACY_SESSION_VERSION:
        version, issued_raw, nonce, provided_signature = parts
        claims = ""
    elif len(parts) == 5 and parts[0] in {_SESSION_VERSION, _MEMBER_SESSION_VERSION}:
        version, issued_raw, nonce, claims, provided_signature = parts
    else:
        return None
    if not nonce or len(nonce) > 128:
        return None
    try:
        issued = int(issued_raw)
    except (TypeError, ValueError):
        return None
    age = int(time.time()) - issued
    if age < -_CLOCK_SKEW_SECONDS or age > _session_max_age():
        return None
    payload = f"{version}.{issued}.{nonce}" if not claims else f"{version}.{issued}.{nonce}.{claims}"
    expected_signature = _session_signature(token, payload)
    if not hmac.compare_digest(provided_signature, expected_signature):
        return None
    if version == _LEGACY_SESSION_VERSION:
        return default_principal()
    try:
        padding = "=" * (-len(claims) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(claims + padding).decode("utf-8"))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if version == _MEMBER_SESSION_VERSION:
        principal_id = str(decoded.get("sub") or "").strip()
        email = str(decoded.get("email") or "").strip().lower()
        display_name = str(decoded.get("display_name") or "").strip()
        if (
            str(decoded.get("role") or "") != "public_member"
            or not principal_id.startswith("cf-")
            or not 35 <= len(principal_id) <= 96
            or not email
            or len(email) > 320
            or len(display_name) > 160
        ):
            return None
        return DeskPrincipal(
            principal_id=principal_id,
            email=email,
            display_name=display_name or email.split("@", 1)[0],
            role="public_member",
        )
    return principal_by_id(str(decoded.get("sub") or ""))


def _public_desk_origins() -> set[str]:
    raw = (os.getenv("DESK_PUBLIC_ORIGINS") or "").strip()
    out: set[str] = set()
    for part in raw.split(","):
        item = part.strip().rstrip("/")
        if item:
            out.add(item.lower())
    return out


def _bootstrap_hosts() -> set[str]:
    raw = (os.getenv("DESK_SESSION_BOOTSTRAP_HOSTS") or "").strip()
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _public_guest_hosts() -> set[str]:
    raw = (os.getenv("DESK_PUBLIC_GUEST_HOSTS") or "").strip()
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _same_origin_browser_request(
    handler: BaseHTTPRequestHandler, allowed_hosts: set[str]
) -> bool:
    host = str(handler.headers.get("Host") or "").strip().lower()
    host_only = host.split(":")[0]
    if not host or not (host in allowed_hosts or host_only in allowed_hosts):
        return False
    same_origin_values = {f"http://{host}", f"https://{host}"}
    origin = str(handler.headers.get("Origin") or "").strip()
    referer = str(handler.headers.get("Referer") or "").strip()
    if origin:
        return origin.rstrip("/").lower() in same_origin_values
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        return f"{parsed.scheme}://{parsed.netloc}".lower() in same_origin_values
    return False


def request_presents_desk_token(handler: BaseHTTPRequestHandler) -> bool:
    return bool(_supplied_desk_token(handler)) and principal_for_token(
        _supplied_desk_token(handler), shared_token=access_token_required() or ""
    ) is not None


def _supplied_desk_token(handler: BaseHTTPRequestHandler) -> str:
    auth = str(handler.headers.get("Authorization") or "")
    header = str(handler.headers.get("X-Desk-Token") or "")
    return auth[7:].strip() if auth.startswith("Bearer ") else header.strip()


def request_desk_principal(handler: BaseHTTPRequestHandler) -> DeskPrincipal | None:
    shared_token = access_token_required() or ""
    auth = str(handler.headers.get("Authorization") or "")
    header = str(handler.headers.get("X-Desk-Token") or "")
    provided = auth[7:].strip() if auth.startswith("Bearer ") else header.strip()
    if provided:
        principal = principal_for_token(provided, shared_token=shared_token)
        if principal:
            return principal
    cloudflare_principal = cloudflare_access_principal(handler)
    if cloudflare_principal:
        return cloudflare_principal
    secret = _session_signing_secret()
    if secret:
        return desk_session_principal(handler, secret)
    return None


def same_origin_desk_request(handler: BaseHTTPRequestHandler) -> bool:
    if request_presents_desk_token(handler):
        return True
    return _same_origin_browser_request(handler, _bootstrap_hosts())


def public_guest_desk_request(handler: BaseHTTPRequestHandler) -> bool:
    return _same_origin_browser_request(handler, _public_guest_hosts())


def _token_matches(provided: str, expected: str) -> bool:
    provided_digest = hashlib.sha256(provided.encode("utf-8")).digest()
    expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(provided_digest, expected_digest)


def request_has_desk_access(handler: BaseHTTPRequestHandler) -> bool:
    return request_desk_principal(handler) is not None


def desk_capability_document(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    configured = desk_auth_configured()
    principal = request_desk_principal(handler)
    authenticated = principal is not None
    cloudflare_sign_in = bool(cloudflare_access_configured())
    access_code_sign_in = member_access_codes_configured()
    return {
        "version": 2,
        "authenticated": authenticated,
        "server_configured": configured,
        "access": principal.role if principal else "locked",
        "principal": principal.public_dict() if principal else None,
        "permissions": permissions_document(principal),
        "tenancy": {
            "mode": "personal-work",
            "identity_aware": True,
            "personal_work_isolated": True,
            "shared_objects": ["source_catalog", "library", "workers"],
            "private_objects": ["research_profile", "ask_sessions", "discover_intents", "synthesis_threads"],
            "multi_user_ready": True,
        },
        "session": {
            "cookie_version": _MEMBER_SESSION_VERSION,
            "max_age_seconds": _session_max_age(),
            "bootstrap_available": bool(_bootstrap_hosts() or _public_guest_hosts())
            or request_presents_desk_token(handler),
            "public_guest_available": bool(_public_guest_hosts()),
            "member_sign_in_available": cloudflare_sign_in or access_code_sign_in,
            "member_access_code_available": access_code_sign_in,
            "member_sign_in_path": "/library/desk/login" if cloudflare_sign_in else None,
            "member_sign_in_mode": "email" if cloudflare_sign_in else (
                "invite_code" if access_code_sign_in else None
            ),
        },
    }


def issue_desk_session(handler: BaseHTTPRequestHandler) -> tuple[bool, str, str | None]:
    supplied_code = _supplied_desk_token(handler)
    if supplied_code:
        principal = principal_for_token(
            supplied_code, shared_token=access_token_required() or ""
        )
        if not principal:
            return False, "Invalid member access code", None
        token = _session_signing_secret()
        if not token:
            return False, "Desk session signing is not configured on this host", None
        return True, "", _cookie_header_value(
            token,
            secure=request_is_https(handler),
            principal=principal,
        )
    cloudflare_principal = cloudflare_access_principal(handler)
    if cloudflare_principal:
        return True, "", _cookie_header_value(
            _session_signing_secret(),
            secure=request_is_https(handler),
            principal=cloudflare_principal,
        )
    token = _session_signing_secret()
    if not token:
        return False, "Desk access token is not configured on this host", None
    if public_guest_desk_request(handler):
        return True, "", _cookie_header_value(
            token,
            secure=request_is_https(handler),
            principal=new_public_guest_principal(),
        )
    if not same_origin_desk_request(handler):
        return False, "Desk session bootstrap is not permitted for this request", None
    principal = request_desk_principal(handler) if request_presents_desk_token(handler) else default_principal()
    return True, "", _cookie_header_value(
        token,
        secure=request_is_https(handler),
        principal=principal,
    )


def issue_cloudflare_member_session(
    handler: BaseHTTPRequestHandler,
) -> tuple[bool, str, str | None]:
    principal = cloudflare_access_principal(handler)
    if not principal:
        return False, "Verified member sign-in is required", None
    token = _session_signing_secret()
    if not token:
        return False, "Desk session signing is not configured on this host", None
    return True, "", _cookie_header_value(
        token,
        secure=request_is_https(handler),
        principal=principal,
    )


def clear_desk_session(handler: BaseHTTPRequestHandler) -> tuple[bool, str, str | None]:
    token = _session_signing_secret()
    if not token:
        return True, "", _cookie_header_value("", clear=True, secure=request_is_https(handler))
    if not (same_origin_desk_request(handler) or public_guest_desk_request(handler)):
        return False, "Desk session clear requires a same-origin browser request", None
    return True, "", _cookie_header_value(token, clear=True, secure=request_is_https(handler))


def authorize(handler: BaseHTTPRequestHandler, path: str, method: str = "GET") -> tuple[bool, str]:
    if not path_requires_auth(path, method=method):
        _CURRENT_PRINCIPAL.set(request_desk_principal(handler))
        return True, ""
    if not desk_auth_configured():
        _CURRENT_PRINCIPAL.set(None)
        return False, "Desk access token is not configured on this host"
    principal = request_desk_principal(handler)
    _CURRENT_PRINCIPAL.set(principal)
    if principal:
        permission = required_permission(path, method)
        if permission not in principal.permissions:
            return False, f"Desk role {principal.role} lacks permission: {permission}"
        return True, ""
    return False, "Desk access token required (set Authorization: Bearer or X-Desk-Token)"
