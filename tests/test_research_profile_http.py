from __future__ import annotations

from types import SimpleNamespace

from scripts.research_data_mcp import desk_auth
from scripts.research_data_mcp.desk_principal import DeskPrincipal
from scripts.research_data_mcp.http_router import handle_get, handle_post


def _stack(tmp_path):
    return SimpleNamespace(gateway=SimpleNamespace(repo_root=tmp_path))


def _researcher(name: str) -> DeskPrincipal:
    return DeskPrincipal(
        principal_id=f"cf-{name}-0123456789abcdef0123456789abcdef",
        email=f"{name}@example.edu",
        display_name=name.title(),
        role="public_member",
    )


def test_registered_profile_routes_roundtrip_for_current_principal(tmp_path):
    alice = _researcher("alice")
    stack = _stack(tmp_path)
    with desk_auth.desk_principal_context(alice):
        empty = handle_get("/library/profile", {}, stack)
        assert empty["status"] == 200
        assert empty["body"]["principal"]["email"] == "alice@example.edu"
        assert empty["body"]["configured"] is False

        saved = handle_post(
            "/library/profile",
            {
                "discipline": "Finance",
                "research_topics": ["stablecoins"],
                "current_project": "Master's thesis",
            },
            stack,
        )
        assert saved["status"] == 200
        assert saved["body"]["configured"] is True

        reread = handle_get("/library/profile", {}, stack)
        assert reread["body"]["profile"]["research_topics"] == ["stablecoins"]


def test_profile_handler_refuses_guest_even_if_dispatch_is_called_directly(tmp_path):
    guest = DeskPrincipal(
        principal_id="guest-abcdefghijklmnopqrstuvwxyz",
        email="",
        display_name="Guest researcher",
        role="public_guest",
    )
    with desk_auth.desk_principal_context(guest):
        result = handle_get("/library/profile", {}, _stack(tmp_path))
    assert result["status"] == 403
    assert "signed-in Research Drive account" in result["body"]["message"]
