"""Authorization boundary tests for the desk.

These encode a live vulnerability found on deployed 73ed5d0: an anonymous
browser visiting a public desk was same-origin by definition, so the session
bootstrap minted a privileged cookie for them. `POST /library/jobs/approve-safe`
then *ran* the approval sweep for an unauthenticated internet visitor.

The existing live smoke checks rendering only, and can be run with a token,
which masked all of this.
"""

from __future__ import annotations

import pytest

from scripts.research_data_mcp import desk_auth


class FakeHandler:
    def __init__(self, **headers: str) -> None:
        self.headers = {k.replace("_", "-"): v for k, v in headers.items()}


TOKEN = "t0ken-for-tests-only-not-a-real-secret"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "YZU_DESK_ACCESS_TOKEN",
        "DESK_ACCESS_TOKEN",
        "DESK_PUBLIC_ORIGINS",
        "DESK_SESSION_BOOTSTRAP_HOSTS",
        "DESK_SESSION_MAX_AGE_SECONDS",
        "YZU_DESK_SESSION_SIGNING_SECRET",
        "DESK_PRINCIPALS_FILE",
        "DESK_DEFAULT_USER_ID",
        "DESK_DEFAULT_USER_EMAIL",
        "DESK_DEFAULT_USER_NAME",
        "DESK_DEFAULT_USER_ROLE",
        "DESK_DEFAULT_WORKSPACE_ID",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("YZU_DESK_ACCESS_TOKEN", TOKEN)


# --- session minting -------------------------------------------------------

def test_anonymous_same_origin_browser_cannot_mint_a_session():
    """The actual vulnerability: same-origin is not authentication."""
    handler = FakeHandler(Host="desk.example.test", Origin="https://desk.example.test")
    assert desk_auth.same_origin_desk_request(handler) is False
    ok, _msg, cookie = desk_auth.issue_desk_session(handler)
    assert ok is False
    assert cookie is None


def test_referer_only_anonymous_browser_cannot_mint():
    handler = FakeHandler(Host="desk.example.test", Referer="https://desk.example.test/?tab=home")
    assert desk_auth.same_origin_desk_request(handler) is False


def test_no_default_public_origin_is_configured():
    """It used to default to a real public hostname."""
    assert desk_auth._public_desk_origins() == set()


def test_token_bearing_request_may_mint():
    handler = FakeHandler(Host="desk.example.test", X_Desk_Token=TOKEN)
    ok, _msg, cookie = desk_auth.issue_desk_session(handler)
    assert ok is True
    assert cookie and desk_auth.DESK_SESSION_COOKIE in cookie


def test_bearer_token_is_accepted_for_minting():
    handler = FakeHandler(Host="desk.example.test", Authorization=f"Bearer {TOKEN}")
    assert desk_auth.same_origin_desk_request(handler) is True


def test_allowlisted_host_restores_internal_browser_convenience(monkeypatch):
    monkeypatch.setenv("DESK_SESSION_BOOTSTRAP_HOSTS", "100.127.141.44")
    internal = FakeHandler(Host="100.127.141.44:8765", Origin="http://100.127.141.44:8765")
    assert desk_auth.same_origin_desk_request(internal) is True
    # ...and only there: a public host stays refused.
    public = FakeHandler(Host="desk.example.test", Origin="https://desk.example.test")
    assert desk_auth.same_origin_desk_request(public) is False


def test_cross_origin_request_is_refused(monkeypatch):
    monkeypatch.setenv("DESK_SESSION_BOOTSTRAP_HOSTS", "100.127.141.44")
    handler = FakeHandler(Host="100.127.141.44:8765", Origin="https://evil.example")
    assert desk_auth.same_origin_desk_request(handler) is False


def test_scriptless_request_without_origin_or_referer_is_refused(monkeypatch):
    monkeypatch.setenv("DESK_SESSION_BOOTSTRAP_HOSTS", "100.127.141.44")
    handler = FakeHandler(Host="100.127.141.44:8765")
    assert desk_auth.same_origin_desk_request(handler) is False


# --- fail-closed behaviour -------------------------------------------------

def test_missing_token_refuses_protected_routes(monkeypatch):
    """Previously `authorize` returned True for everything when unconfigured."""
    monkeypatch.delenv("YZU_DESK_ACCESS_TOKEN", raising=False)
    handler = FakeHandler(Host="desk.example.test")
    for path, method in [
        ("/library/discover/collect", "POST"),
        ("/library/jobs/approve-safe", "POST"),
        ("/library/jobs", "GET"),
        ("/yzu/jobs", "POST"),
    ]:
        ok, msg = desk_auth.authorize(handler, path, method=method)
        assert ok is False, f"{method} {path} must fail closed without a token"
        assert "not configured" in msg


def test_missing_token_still_serves_unprotected_routes(monkeypatch):
    monkeypatch.delenv("YZU_DESK_ACCESS_TOKEN", raising=False)
    handler = FakeHandler(Host="desk.example.test")
    ok, _ = desk_auth.authorize(handler, "/healthz", method="GET")
    assert ok is True


def test_mutations_require_auth_by_default():
    for path in ["/library/anything/at/all", "/yzu/whatever"]:
        assert desk_auth.path_requires_auth(path, method="POST") is True


# --- cookie properties -----------------------------------------------------

def test_cookie_is_secure_over_https():
    handler = FakeHandler(Host="d.example", X_Desk_Token=TOKEN, X_Forwarded_Proto="https")
    _ok, _msg, cookie = desk_auth.issue_desk_session(handler)
    assert "Secure" in cookie
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie


def test_cookie_omits_secure_on_plain_http_internal_desk():
    """Setting Secure on the plain-HTTP Tailscale desk would silently drop it."""
    handler = FakeHandler(Host="100.127.141.44:8765", X_Desk_Token=TOKEN)
    _ok, _msg, cookie = desk_auth.issue_desk_session(handler)
    assert "Secure" not in cookie


def test_cookie_has_a_bounded_lifetime():
    handler = FakeHandler(Host="d.example", X_Desk_Token=TOKEN)
    _ok, _msg, cookie = desk_auth.issue_desk_session(handler)
    assert "Max-Age=" in cookie
    age = int(cookie.split("Max-Age=")[1].split(";")[0])
    assert 300 <= age <= 604800


def test_forged_session_cookie_is_rejected():
    handler = FakeHandler(Host="d.example", Cookie=f"{desk_auth.DESK_SESSION_COOKIE}=v1.deadbeef")
    assert desk_auth.desk_session_cookie_valid(handler, TOKEN) is False
    ok, _ = desk_auth.authorize(handler, "/library/jobs/approve-safe", method="POST")
    assert ok is False


def test_valid_session_cookie_authorizes():
    value = desk_auth.session_cookie_value(TOKEN)
    handler = FakeHandler(Host="d.example", Cookie=f"{desk_auth.DESK_SESSION_COOKIE}={value}")
    ok, _ = desk_auth.authorize(handler, "/library/jobs/approve-safe", method="POST")
    assert ok is True


def test_v1_session_cookie_is_revoked_by_the_v2_boundary():
    handler = FakeHandler(
        Host="d.example",
        Cookie=f"{desk_auth.DESK_SESSION_COOKIE}=v1.{'0' * 64}",
    )
    assert desk_auth.desk_session_cookie_valid(handler, TOKEN) is False


def test_expired_v2_session_is_rejected():
    value = desk_auth.session_cookie_value(TOKEN, issued_at=1, nonce="expired-session")
    handler = FakeHandler(Host="d.example", Cookie=f"{desk_auth.DESK_SESSION_COOKIE}={value}")
    assert desk_auth.desk_session_cookie_valid(handler, TOKEN) is False


def test_capability_document_never_exposes_secrets_and_tracks_access():
    locked = desk_auth.desk_capability_document(FakeHandler(Host="d.example"))
    assert locked["authenticated"] is False
    assert locked["permissions"]["view_faculty_profile"] is False
    assert TOKEN not in repr(locked)

    authenticated = desk_auth.desk_capability_document(
        FakeHandler(Host="d.example", X_Desk_Token=TOKEN)
    )
    assert authenticated["authenticated"] is True
    assert authenticated["permissions"]["approve_jobs"] is True
    assert authenticated["principal"]["role"] == "admin"
    assert authenticated["tenancy"]["multi_user_ready"] is False
