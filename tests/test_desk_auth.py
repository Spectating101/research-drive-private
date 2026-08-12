from types import SimpleNamespace

import pytest

from drive.scripts.research_data_mcp import desk_auth
from drive.scripts.research_data_mcp.desk_auth import (
    DESK_SESSION_COOKIE,
    authorize,
    clear_desk_session,
    desk_session_cookie_valid,
    issue_desk_session,
    path_requires_auth,
    session_cookie_value,
)
from scripts.research_data_mcp.desk_principal import DeskPrincipal


def _handler(**headers: str) -> SimpleNamespace:
    return SimpleNamespace(headers=headers)


@pytest.fixture(autouse=True)
def _clean_desk_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YZU_DESK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("DESK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("DESK_PUBLIC_ORIGINS", raising=False)
    monkeypatch.delenv("DESK_SESSION_BOOTSTRAP_HOSTS", raising=False)
    monkeypatch.delenv("DESK_CLOUDFLARE_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("DESK_CLOUDFLARE_ACCESS_AUD", raising=False)


@pytest.mark.parametrize(
    "path",
    ["/", "/healthz", "/library/desk/session", "/library/desk/capabilities"],
)
def test_explicit_public_paths_remain_public_without_token(path: str) -> None:
    assert path_requires_auth(path, method="POST") is False
    assert authorize(_handler(), path, method="POST") == (True, "")


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/library/chat", "GET"),
        ("/api/health", "GET"),
        ("/datasets", "GET"),
        ("/query/private-panel", "GET"),
        ("/library/faculty/profile", "GET"),
        ("/library/credentials/profiles", "GET"),
        ("/yzu/workers", "GET"),
        ("/library/jobs", "POST"),
        ("/library/future-write-route", "POST"),
        ("/yzu/future-write-route", "DELETE"),
    ],
)
def test_protected_routes_fail_closed_without_configured_token(path: str, method: str) -> None:
    ok, message = authorize(_handler(), path, method=method)

    assert ok is False
    assert message == "Desk access token is not configured on this host"


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer secret-token"},
        {"X-Desk-Token": "secret-token"},
    ],
)
def test_configured_token_authorizes_protected_route(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]
) -> None:
    monkeypatch.setenv("YZU_DESK_ACCESS_TOKEN", "secret-token")

    assert authorize(_handler(**headers), "/library/chat") == (True, "")


def test_wrong_token_is_rejected_even_when_length_differs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YZU_DESK_ACCESS_TOKEN", "secret-token")

    ok, message = authorize(
        _handler(Authorization="Bearer x"),
        "/library/chat",
    )

    assert ok is False
    assert "Desk access token required" in message


def test_session_bootstrap_requires_configured_token_and_same_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    same_origin = _handler(Host="desk.internal", Origin="https://desk.internal")
    assert issue_desk_session(same_origin) == (
        False,
        "Desk access token is not configured on this host",
        None,
    )

    monkeypatch.setenv("DESK_ACCESS_TOKEN", "secret-token")
    for refused in (
        _handler(Host="desk.internal", Origin="https://evil.example"),
        _handler(Host="desk.internal"),
        same_origin,
    ):
        ok, message, cookie = issue_desk_session(refused)
        assert ok is False
        assert message == "Desk session bootstrap is not permitted for this request"
        assert cookie is None

    monkeypatch.setenv("DESK_SESSION_BOOTSTRAP_HOSTS", "desk.internal")
    ok, message, cookie = issue_desk_session(same_origin)
    assert (ok, message) == (True, "")
    assert cookie is not None
    assert cookie.startswith(f"{DESK_SESSION_COOKIE}=v3.")
    assert "Path=/" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie
    assert "Domain=" not in cookie


def test_public_origin_configuration_never_grants_session_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DESK_ACCESS_TOKEN", "secret-token")
    monkeypatch.setenv("DESK_PUBLIC_ORIGINS", "https://review.example.test")
    handler = _handler(Host="review.example.test", Origin="https://review.example.test")
    assert issue_desk_session(handler)[0] is False


def test_session_cookie_authorizes_and_token_rotation_invalidates_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DESK_ACCESS_TOKEN", "secret-token")
    handler = _handler(Cookie=f"{DESK_SESSION_COOKIE}={session_cookie_value('secret-token')}")

    assert desk_session_cookie_valid(handler, "secret-token") is True
    assert authorize(handler, "/library/chat") == (True, "")

    monkeypatch.setenv("DESK_ACCESS_TOKEN", "rotated-token")
    assert desk_session_cookie_valid(handler, "rotated-token") is False
    assert authorize(handler, "/library/chat")[0] is False


def test_clear_session_removes_stale_cookie_without_configured_token() -> None:
    ok, message, cookie = clear_desk_session(_handler())

    assert (ok, message) == (True, "")
    assert cookie == f"{DESK_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"


def test_verified_cloudflare_access_member_has_no_private_or_operator_power(monkeypatch):
    monkeypatch.setenv(
        "DESK_CLOUDFLARE_ACCESS_TEAM_DOMAIN",
        "https://research-drive.cloudflareaccess.com",
    )
    monkeypatch.setenv("DESK_CLOUDFLARE_ACCESS_AUD", "public-audience")
    member = DeskPrincipal(
        principal_id="cf-member",
        email="member@example.edu",
        display_name="Member",
        role="public_member",
    )
    monkeypatch.setattr(desk_auth, "cloudflare_access_principal", lambda _handler: member)
    handler = _handler(**{"Cf-Access-Jwt-Assertion": "verified-by-access"})

    assert authorize(handler, "/datasets", "GET")[0] is True
    assert authorize(handler, "/library/chat", "POST")[0] is True
    assert authorize(handler, "/library/jobs", "POST")[0] is True
    assert authorize(handler, "/library/faculty/profile", "GET")[0] is False
    assert authorize(handler, "/library/jobs/approve-safe", "POST")[0] is False
    assert authorize(handler, "/yzu/workers", "GET")[0] is False

    ok, message, cookie = issue_desk_session(handler)
    assert (ok, message, cookie) == (True, "", None)
