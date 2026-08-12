"""Verified Cloudflare Access identities for the public Research Drive desk.

Cloudflare inserts a signed ``Cf-Access-Jwt-Assertion`` at the origin after a
browser has satisfied an Access application.  Headers alone are forgeable, so
this module verifies the JWT against Cloudflare's rotating public keys and the
configured issuer/audience before it creates a local principal.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from scripts.research_data_mcp.desk_principal import DeskPrincipal

_ASSERTION_HEADER = "Cf-Access-Jwt-Assertion"


@dataclass(frozen=True)
class CloudflareAccessConfig:
    team_domain: str
    audience: str


def _team_domain(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    parsed = urlparse(raw)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or not parsed.netloc.endswith(".cloudflareaccess.com")
    ):
        return ""
    return f"https://{parsed.netloc.lower()}"


def configured_access() -> CloudflareAccessConfig | None:
    """Return complete public-Access configuration, otherwise ``None``.

    Partial configuration intentionally does not activate an alternate auth
    path.  That keeps an accidentally set team domain from weakening the desk's
    existing private-token boundary.
    """
    team_domain = _team_domain(os.getenv("DESK_CLOUDFLARE_ACCESS_TEAM_DOMAIN") or "")
    audience = str(os.getenv("DESK_CLOUDFLARE_ACCESS_AUD") or "").strip()
    if not team_domain or not audience or len(audience) > 256:
        return None
    return CloudflareAccessConfig(team_domain=team_domain, audience=audience)


def _public_member_role() -> str:
    # The public identity bridge never grants an operator role from a JWT or a
    # browser-controlled header.  Operators remain explicit local principals.
    return "public_member"


def _principal_from_claims(claims: dict[str, Any], config: CloudflareAccessConfig) -> DeskPrincipal | None:
    subject = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    if not subject or not email or len(subject) > 512 or len(email) > 320:
        return None
    stable = hashlib.sha256(f"{config.team_domain}\0{subject}".encode("utf-8")).hexdigest()[:32]
    display_name = str(claims.get("name") or "").strip()[:160] or email.split("@", 1)[0]
    return DeskPrincipal(
        principal_id=f"cf-{stable}",
        email=email,
        display_name=display_name,
        role=_public_member_role(),
    )


def principal_from_assertion(assertion: str) -> DeskPrincipal | None:
    """Verify a Cloudflare Access assertion and return a restricted principal.

    Any malformed assertion, network/key problem, claim mismatch, or missing
    optional dependency fails closed.  No decoded but unverified JWT claim is
    ever used as identity.
    """
    config = configured_access()
    token = str(assertion or "").strip()
    if not config or not token:
        return None
    try:
        import jwt

        client = jwt.PyJWKClient(f"{config.team_domain}/cdn-cgi/access/certs")
        signing_key = client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=config.audience,
            issuer=config.team_domain,
            options={"require": ["exp", "iat", "sub", "email"]},
        )
    except Exception:
        return None
    return _principal_from_claims(claims if isinstance(claims, dict) else {}, config)


def principal_from_request(handler: Any) -> DeskPrincipal | None:
    headers = getattr(handler, "headers", {}) or {}
    return principal_from_assertion(str(headers.get(_ASSERTION_HEADER) or ""))
