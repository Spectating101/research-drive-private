from __future__ import annotations

from types import SimpleNamespace

from scripts.research_data_mcp import desk_auth
from scripts.research_data_mcp.desk_principal import DeskPrincipal
from scripts.research_data_mcp.http_router import handle_post


def test_preview_uses_ask_authority_but_execute_keeps_collection_boundary():
    assert desk_auth.required_permission(
        "/library/synthesis/threads/thread-a/preview", "POST"
    ) == "use_ask"
    assert desk_auth.required_permission(
        "/library/synthesis/threads/thread-a/execute", "POST"
    ) == "submit_collection"
    assert desk_auth.required_permission(
        "/library/synthesis/threads/thread-a/collect-missing", "POST"
    ) == "submit_collection"


def test_public_member_has_preview_authority_without_collection_authority(monkeypatch):
    researcher = DeskPrincipal(
        principal_id="cf-alice-0123456789abcdef0123456789abcdef",
        email="alice@example.edu",
        display_name="Alice",
        role="public_member",
    )
    monkeypatch.setattr(desk_auth, "desk_auth_configured", lambda: True)
    monkeypatch.setattr(desk_auth, "request_desk_principal", lambda _handler: researcher)
    handler = SimpleNamespace(headers={})

    assert desk_auth.authorize(
        handler, "/library/synthesis/threads/thread-a/preview", "POST"
    )[0] is True
    allowed, message = desk_auth.authorize(
        handler, "/library/synthesis/threads/thread-a/execute", "POST"
    )
    assert allowed is False
    assert "submit_collection" in message


def test_preview_route_invokes_only_bounded_preview_action(tmp_path):
    observed = {}

    class Gateway:
        repo_root = tmp_path

        def synthesis_thread_submit_execution(self, thread_id: str, *, action: str):
            observed.update(thread_id=thread_id, action=action)
            return {
                "thread": {
                    "id": thread_id,
                    "state": {
                        "execution": {
                            "status": "spec_accepted",
                            "preview": {"status": "succeeded"},
                        }
                    },
                }
            }

    result = handle_post(
        "/library/synthesis/threads/thread-a/preview",
        {},
        SimpleNamespace(gateway=Gateway()),
    )
    assert result["status"] == 200
    assert observed == {"thread_id": "thread-a", "action": "preview"}
