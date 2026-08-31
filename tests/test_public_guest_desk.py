"""Public guest desk boundary: useful research access without reasoning or mutation authority."""

from __future__ import annotations

import pytest

from scripts.research_data_mcp import desk_auth


class FakeHandler:
    def __init__(self, **headers: str) -> None:
        self.headers = {key.replace("_", "-"): value for key, value in headers.items()}


@pytest.fixture(autouse=True)
def guest_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DESK_SESSION_BOOTSTRAP_HOSTS",
        "DESK_PUBLIC_GUEST_HOSTS",
        "DESK_PRINCIPALS_FILE",
        "DESK_DEFAULT_USER_ROLE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("YZU_DESK_ACCESS_TOKEN", "public-guest-test-token")
    monkeypatch.setenv("DESK_PUBLIC_GUEST_HOSTS", "previous.easycamp.tech")


@pytest.fixture(autouse=True)
def clear_request_principal() -> None:
    """Direct auth-helper tests must not leak a request identity to later tests."""
    desk_auth._CURRENT_PRINCIPAL.set(None)
    yield
    desk_auth._CURRENT_PRINCIPAL.set(None)


def _guest_cookie() -> str:
    mint = FakeHandler(
        Host="previous.easycamp.tech",
        Origin="https://previous.easycamp.tech",
        X_Forwarded_Proto="https",
    )
    ok, message, cookie = desk_auth.issue_desk_session(mint)
    assert ok is True and message == "" and cookie
    assert "Secure" in cookie and "HttpOnly" in cookie
    return cookie.split("=", 1)[1].split(";", 1)[0]


def test_public_guest_session_is_unique_and_read_only():
    first = _guest_cookie()
    second = _guest_cookie()
    assert first != second
    guest = FakeHandler(
        Host="previous.easycamp.tech",
        Cookie=f"{desk_auth.DESK_SESSION_COOKIE}={first}",
    )
    principal = desk_auth.request_desk_principal(guest)
    assert principal and principal.role == "public_guest"
    assert principal.principal_id.startswith("guest-")
    assert desk_auth.authorize(guest, "/datasets", "GET")[0] is True
    assert desk_auth.authorize(guest, "/library/chat", "POST")[0] is False
    assert desk_auth.authorize(guest, "/library/chat/session-123", "GET")[0] is False
    assert desk_auth.authorize(guest, "/library/desk/warm", "POST")[0] is False
    assert desk_auth.authorize(guest, "/library/synthesis/threads", "GET")[0] is False
    assert desk_auth.authorize(guest, "/library/faculty/profile", "GET")[0] is False
    assert desk_auth.authorize(guest, "/yzu/workers", "GET")[0] is False
    assert desk_auth.authorize(guest, "/library/jobs", "POST")[0] is False
    assert desk_auth.authorize(guest, "/library/jobs/approve-safe", "POST")[0] is False


def test_public_guest_mint_requires_configured_same_origin_browser():
    wrong_origin = FakeHandler(
        Host="previous.easycamp.tech", Origin="https://evil.example"
    )
    wrong_host = FakeHandler(Host="other.example", Origin="https://other.example")
    bare = FakeHandler(Host="previous.easycamp.tech")
    for handler in (wrong_origin, wrong_host, bare):
        ok, _message, cookie = desk_auth.issue_desk_session(handler)
        assert ok is False and cookie is None


def test_capabilities_describe_guest_without_reasoning_or_private_permissions():
    value = _guest_cookie()
    guest = FakeHandler(
        Host="previous.easycamp.tech",
        Cookie=f"{desk_auth.DESK_SESSION_COOKIE}={value}",
    )
    document = desk_auth.desk_capability_document(guest)
    assert document["access"] == "public_guest"
    assert document["permissions"]["view_research_data"] is True
    assert document["permissions"]["use_ask"] is False
    assert document["permissions"]["submit_collection"] is False
    assert document["permissions"]["approve_jobs"] is False
    assert document["session"]["public_guest_available"] is True
