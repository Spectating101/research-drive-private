from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from scripts.research_data_mcp import cloudflare_access


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DESK_CLOUDFLARE_ACCESS_TEAM_DOMAIN",
        "https://research-drive.cloudflareaccess.com",
    )
    monkeypatch.setenv("DESK_CLOUDFLARE_ACCESS_AUD", "research-drive-public-audience")


def test_verified_access_assertion_becomes_restricted_stable_principal(monkeypatch):
    _configure(monkeypatch)
    observed = {}

    class FakeJwks:
        def __init__(self, url):
            observed["url"] = url

        def get_signing_key_from_jwt(self, token):
            observed["token"] = token
            return SimpleNamespace(key="verified-key")

    def decode(token, key, **kwargs):
        observed.update(token=token, key=key, **kwargs)
        return {
            "sub": "cloudflare-subject-123",
            "email": "Researcher@Example.edu",
            "name": "Researcher",
        }

    monkeypatch.setitem(sys.modules, "jwt", SimpleNamespace(PyJWKClient=FakeJwks, decode=decode))
    principal = cloudflare_access.principal_from_assertion("signed-access-jwt")

    assert principal is not None
    assert principal.principal_id.startswith("cf-")
    assert principal.email == "researcher@example.edu"
    assert principal.display_name == "Researcher"
    assert principal.role == "public_member"
    assert "use_ask" in principal.permissions
    assert "submit_collection" not in principal.permissions
    assert "view_faculty_profile" not in principal.permissions
    assert "approve_jobs" not in principal.permissions
    assert observed["url"] == "https://research-drive.cloudflareaccess.com/cdn-cgi/access/certs"
    assert observed["audience"] == "research-drive-public-audience"
    assert observed["issuer"] == "https://research-drive.cloudflareaccess.com"
    assert observed["algorithms"] == ["RS256"]


def test_unverified_or_malformed_access_assertion_fails_closed(monkeypatch):
    _configure(monkeypatch)

    class FailingJwks:
        def __init__(self, _url):
            pass

        def get_signing_key_from_jwt(self, _token):
            raise RuntimeError("signature key unavailable")

    monkeypatch.setitem(sys.modules, "jwt", SimpleNamespace(PyJWKClient=FailingJwks))
    assert cloudflare_access.principal_from_assertion("attacker-controlled-header") is None


@pytest.mark.parametrize(
    "team_domain",
    [
        "http://research-drive.cloudflareaccess.com",
        "https://research-drive.example.com",
        "https://research-drive.cloudflareaccess.com/extra-path",
    ],
)
def test_partial_or_invalid_access_configuration_never_activates(monkeypatch, team_domain):
    monkeypatch.setenv("DESK_CLOUDFLARE_ACCESS_TEAM_DOMAIN", team_domain)
    monkeypatch.setenv("DESK_CLOUDFLARE_ACCESS_AUD", "audience")
    assert cloudflare_access.configured_access() is None
