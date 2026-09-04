from __future__ import annotations

import json

import pytest

from scripts.research_data_mcp import http_router
from scripts.research_data_mcp import library_federation as federation
from scripts.research_data_mcp import library_federation_runtime as runtime
from scripts.research_data_mcp.connected_accounts_security import public_connected_accounts_document
from scripts.research_data_mcp.desk_principal import DeskPrincipal


def principal(pid: str) -> DeskPrincipal:
    return DeskPrincipal(
        principal_id=pid,
        email=f"{pid}@example.test",
        display_name=pid,
        role="member",
    )


def account(account_id: str, provider: str = "google_drive") -> dict:
    return {
        "id": account_id,
        "provider": provider,
        "status": "connected",
        "access_mode": "read",
        "remote": f"remote-{account_id}",
    }


def test_multiple_provider_accounts_require_explicit_account_id(tmp_path, monkeypatch):
    actor = principal("alice")
    monkeypatch.setattr(
        federation,
        "list_connected_accounts",
        lambda repo_root, principal=None: [account("g1"), account("g2")],
    )
    with pytest.raises(ValueError, match="account_id is required"):
        federation._selected_account(tmp_path, provider="google_drive", principal=actor)

    selected_actor, selected = federation._selected_account(
        tmp_path,
        provider="google_drive",
        account_id="g2",
        principal=actor,
    )
    assert selected_actor.principal_id == "alice"
    assert selected["id"] == "g2"


def test_registry_identity_resolution_requires_provider_account_and_item(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "dataset_id": "panel-1",
                        "name": "Canonical panel",
                        "holdings": [
                            {
                                "provider": "google_drive",
                                "account_id": "g1",
                                "provider_item_id": "file-9",
                                "path": "/Research/panel.csv",
                            }
                        ],
                    },
                    {
                        "dataset_id": "same-filename-different-object",
                        "name": "panel.csv",
                        "holdings": [
                            {
                                "provider": "google_drive",
                                "account_id": "g2",
                                "provider_item_id": "other-file",
                                "path": "/Research/panel.csv",
                            }
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    index = federation._holding_identity_index(registry)
    assert index[("google_drive", "g1", "file-9")] == "panel-1"
    assert ("google_drive", "g2", "file-9") not in index
    assert ("google_drive", "g1", "other-file") not in index


def test_ambiguous_explicit_holding_identity_fails_closed(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "dataset_id": "a",
                        "holdings": [{"provider": "dropbox", "account_id": "d1", "provider_item_id": "id:x"}],
                    },
                    {
                        "dataset_id": "b",
                        "holdings": [{"provider": "dropbox", "account_id": "d1", "provider_item_id": "id:x"}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    assert ("dropbox", "d1", "id:x") not in federation._holding_identity_index(registry)


def test_google_page_preserves_version_and_resolves_only_explicit_holding(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "_request_json",
        lambda *args, **kwargs: {
            "files": [
                {
                    "id": "known",
                    "name": "renamed-anything.csv",
                    "mimeType": "text/csv",
                    "parents": ["root"],
                    "size": "123",
                    "modifiedTime": "2026-09-05T10:00:00Z",
                    "version": "17",
                    "md5Checksum": "abc123",
                },
                {
                    "id": "unknown",
                    "name": "panel-1.csv",
                    "mimeType": "text/csv",
                    "parents": ["root"],
                },
            ],
            "nextPageToken": "page-2",
        },
    )
    page = runtime._google_page(
        token="secret-token",
        account=account("g1"),
        parent_id="",
        cursor="",
        limit=50,
        identities={("google_drive", "g1", "known"): "panel-1"},
    )
    assert page["items"][0]["logical_asset_id"] == "panel-1"
    assert page["items"][0]["version_id"] == "17"
    assert page["items"][0]["content_hash"] == "md5:abc123"
    assert "logical_asset_id" not in page["items"][1]
    assert page["items"][1]["name"] == "panel-1.csv"
    assert page["next_cursor"] == "page-2"
    assert page["has_more"] is True


def test_dropbox_folder_id_is_not_double_prefixed_and_version_is_preserved(monkeypatch):
    calls = []

    def request(url, **kwargs):
        calls.append((url, kwargs))
        return {
            "entries": [
                {
                    ".tag": "file",
                    "id": "id:file",
                    "name": "x.csv",
                    "path_display": "/Research/x.csv",
                    "size": 4,
                    "rev": "a1b2",
                    "content_hash": "deadbeef",
                }
            ],
            "cursor": "provider-cursor-1",
            "has_more": True,
        }

    monkeypatch.setattr(runtime, "_request_json", request)
    page = runtime._dropbox_page(
        token="secret-token",
        account=account("d1", "dropbox"),
        parent_id="id:folder",
        cursor="",
        limit=50,
        identities={},
    )
    assert calls[0][0].endswith("/files/list_folder")
    assert calls[0][1]["json_body"]["path"] == "id:folder"
    assert page["items"][0]["parent_item_id"] == "id:folder"
    assert page["items"][0]["version_id"] == "a1b2"
    assert page["items"][0]["content_hash"] == "dropbox:deadbeef"
    assert page["next_cursor"] == "provider-cursor-1"
    assert page["has_more"] is True


def test_dropbox_cursor_continuation_is_provider_native(monkeypatch):
    calls = []

    def request(url, **kwargs):
        calls.append((url, kwargs))
        return {
            "entries": [{".tag": "file", "id": "id:file", "name": "x.csv", "path_display": "/x.csv", "size": 4}],
            "cursor": "provider-cursor-2",
            "has_more": False,
        }

    monkeypatch.setattr(runtime, "_request_json", request)
    page = runtime._dropbox_page(
        token="secret-token",
        account=account("d1", "dropbox"),
        parent_id="id:folder",
        cursor="provider-cursor-1",
        limit=50,
        identities={},
    )
    assert calls[0][0].endswith("/files/list_folder/continue")
    assert calls[0][1]["json_body"] == {"cursor": "provider-cursor-1"}
    assert page["next_cursor"] == ""
    assert page["has_more"] is False


def usage_event(**overrides):
    event = {
        "event_type": "library_evidence_usage",
        "logical_asset_id": "panel-1",
        "version_id": "v4",
        "action": "used_in_synthesis",
        "project_id": "project-a",
        "related_asset_ids": ["raw-a", "raw-b", "raw-a"],
        "output_id": "output-7",
        "occurred_at": "2026-09-05T12:30:00Z",
        "context": {"surface": "synthesis"},
    }
    event.update(overrides)
    return event


def test_usage_memory_is_durable_idempotent_and_principal_bound(tmp_path):
    alice = principal("alice")
    bob = principal("bob")
    first = federation.persist_library_usage_event(tmp_path, usage_event(), principal=alice)
    duplicate = federation.persist_library_usage_event(tmp_path, usage_event(), principal=alice)
    assert first["event_id"] == duplicate["event_id"]
    assert first["deduplicated"] is False
    assert duplicate["deduplicated"] is True

    alice_rows = federation.list_library_usage_events(tmp_path, principal=alice)
    bob_rows = federation.list_library_usage_events(tmp_path, principal=bob)
    assert alice_rows["count"] == 1
    assert alice_rows["events"][0]["related_asset_ids"] == ["raw-a", "raw-b"]
    assert bob_rows["count"] == 0


def test_http_usage_persistence_rejects_noncanonical_asset_ids(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"datasets": [{"dataset_id": "panel-1"}]}), encoding="utf-8")
    actor = principal("alice")

    accepted = runtime.persist_canonical_library_usage_event(
        tmp_path,
        usage_event(),
        registry_path=registry,
        principal=actor,
    )
    assert accepted["ok"] is True

    with pytest.raises(ValueError, match="canonical Library asset"):
        runtime.persist_canonical_library_usage_event(
            tmp_path,
            usage_event(logical_asset_id="made-up-file"),
            registry_path=registry,
            principal=actor,
        )


def test_usage_memory_requires_timezone_and_typed_event(tmp_path):
    with pytest.raises(ValueError, match="event_type"):
        federation.normalize_usage_event(usage_event(event_type="something_else"))
    with pytest.raises(ValueError, match="timezone"):
        federation.normalize_usage_event(usage_event(occurred_at="2026-09-05T12:30:00"))


def test_public_account_document_advertises_only_operational_directory_adapters(monkeypatch):
    monkeypatch.setenv("RCLONE_CONFIG_PASS", "test-only-password")
    document = public_connected_accounts_document(
        {
            "accounts": [],
            "providers": [
                {
                    "id": "google_drive",
                    "configured": True,
                    "rclone_available": True,
                    "credential_store_encrypted": True,
                },
                {
                    "id": "dropbox",
                    "configured": True,
                    "rclone_available": False,
                    "credential_store_encrypted": True,
                },
                {
                    "id": "onedrive",
                    "configured": True,
                    "rclone_available": True,
                    "credential_store_encrypted": True,
                },
            ],
        }
    )
    providers = {row["id"]: row for row in document["providers"]}
    assert providers["google_drive"]["capabilities"]["directory_browse"] is True
    assert providers["google_drive"]["directory_browse_available"] is True
    assert providers["dropbox"]["capabilities"]["directory_browse"] is False
    assert providers["onedrive"]["capabilities"]["directory_browse"] is False


def test_router_exposes_federation_and_usage_memory_contracts():
    routes = {(row["method"], row["path"]) for row in http_router.ROUTE_CATALOG}
    assert ("GET", "/library/folders") in routes
    assert ("GET", "/library/evidence-usage") in routes
    assert ("POST", "/library/evidence-usage") in routes
