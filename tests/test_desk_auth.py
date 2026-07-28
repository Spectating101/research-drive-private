from types import SimpleNamespace

import pytest

from drive.scripts.research_data_mcp.desk_auth import (
    DESK_SESSION_COOKIE,
    authorize,
    clear_desk_session,
    desk_session_cookie_valid,
    issue_desk_session,
    path_requires_auth,
    session_cookie_value,
)


def _handler(**headers: str) -> SimpleNamespace:
    return SimpleNamespace(headers=headers)


@pytest.fixture(autouse=True)
def _clean_desk_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YZU_DESK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("DESK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("DESK_PUBLIC_ORIGINS", raising=False)


@pytest.mark.parametrize("path", ["/", "/healthz", "/api/health", "/library/desk/session"])
def test_explicit_public_paths_remain_public_without_token(path: str) -> None:
    assert path_requires_auth(path, method="POST") is False
    assert authorize(_handler(), path, method="POST") == (True, "")


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/library/chat", "GET"),
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
    assert issue_desk_session(_handler(Host="desk.internal", Origin="https://evil.example")) == (
        False,
        "Desk session bootstrap requires a same-origin browser request",
        None,
    )
    assert issue_desk_session(_handler(Host="desk.internal")) == (
        False,
        "Desk session bootstrap requires a same-origin browser request",
        None,
    )

    ok, message, cookie = issue_desk_session(same_origin)
    assert (ok, message) == (True, "")
    assert cookie is not None
    assert cookie.startswith(f"{DESK_SESSION_COOKIE}={session_cookie_value('secret-token')};")
    assert "Path=/" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie
    assert "Domain=" not in cookie


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
