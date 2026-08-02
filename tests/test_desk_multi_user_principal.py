from __future__ import annotations

import hashlib
import json

from scripts.research_data_mcp import desk_auth


class FakeHandler:
    def __init__(self, **headers: str) -> None:
        self.headers = {key.replace("_", "-"): value for key, value in headers.items()}


def _write_principals(tmp_path, rows):
    path = tmp_path / "principals.json"
    path.write_text(json.dumps({"principals": rows}), encoding="utf-8")
    path.chmod(0o600)
    return path


def _row(principal_id: str, token: str, *, role: str, workspace: str):
    return {
        "id": principal_id,
        "email": f"{principal_id}@example.test",
        "display_name": principal_id.title(),
        "role": role,
        "workspace_ids": [workspace],
        "default_workspace_id": workspace,
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    }


def test_distinct_tokens_resolve_distinct_principals(tmp_path, monkeypatch):
    alice_token = "alice-token-for-test"
    bob_token = "bob-token-for-test"
    path = _write_principals(
        tmp_path,
        [
            _row("alice", alice_token, role="researcher", workspace="lab-a"),
            _row("bob", bob_token, role="viewer", workspace="lab-b"),
        ],
    )
    monkeypatch.setenv("DESK_PRINCIPALS_FILE", str(path))
    monkeypatch.setenv("YZU_DESK_SESSION_SIGNING_SECRET", "session-secret-for-test")
    monkeypatch.delenv("YZU_DESK_ACCESS_TOKEN", raising=False)

    alice = desk_auth.request_desk_principal(FakeHandler(Authorization=f"Bearer {alice_token}"))
    bob = desk_auth.request_desk_principal(FakeHandler(X_Desk_Token=bob_token))
    assert alice and alice.principal_id == "alice" and alice.default_workspace_id == "lab-a"
    assert bob and bob.principal_id == "bob" and bob.default_workspace_id == "lab-b"

    alice_doc = desk_auth.desk_capability_document(
        FakeHandler(Authorization=f"Bearer {alice_token}")
    )
    bob_doc = desk_auth.desk_capability_document(FakeHandler(X_Desk_Token=bob_token))
    assert alice_doc["permissions"]["submit_collection"] is True
    assert alice_doc["permissions"]["approve_jobs"] is False
    assert bob_doc["permissions"]["view_research_data"] is True
    assert bob_doc["permissions"]["use_ask"] is False
    assert alice_token not in repr(alice_doc)
    assert bob_token not in repr(bob_doc)


def test_v3_cookie_preserves_principal_identity(tmp_path, monkeypatch):
    token = "researcher-token-for-test"
    signing = "session-signing-secret-for-test"
    path = _write_principals(
        tmp_path,
        [_row("researcher-1", token, role="researcher", workspace="methods-lab")],
    )
    monkeypatch.setenv("DESK_PRINCIPALS_FILE", str(path))
    monkeypatch.setenv("YZU_DESK_SESSION_SIGNING_SECRET", signing)
    monkeypatch.delenv("YZU_DESK_ACCESS_TOKEN", raising=False)

    mint = FakeHandler(Host="desk.example", X_Desk_Token=token)
    ok, message, cookie = desk_auth.issue_desk_session(mint)
    assert ok is True and message == "" and cookie
    value = cookie.split("=", 1)[1].split(";", 1)[0]
    assert value.startswith("v3.")

    session = FakeHandler(Host="desk.example", Cookie=f"{desk_auth.DESK_SESSION_COOKIE}={value}")
    principal = desk_auth.request_desk_principal(session)
    assert principal and principal.principal_id == "researcher-1"
    assert principal.default_workspace_id == "methods-lab"


def test_principal_file_never_accepts_raw_token_field(tmp_path, monkeypatch):
    path = _write_principals(
        tmp_path,
        [
            {
                "id": "unsafe-entry",
                "role": "admin",
                "workspace_ids": ["lab"],
                "token": "plaintext-must-not-work",
            }
        ],
    )
    monkeypatch.setenv("DESK_PRINCIPALS_FILE", str(path))
    monkeypatch.setenv("YZU_DESK_SESSION_SIGNING_SECRET", "session-secret-for-test")
    monkeypatch.delenv("YZU_DESK_ACCESS_TOKEN", raising=False)
    assert desk_auth.request_desk_principal(
        FakeHandler(Authorization="Bearer plaintext-must-not-work")
    ) is None


def test_roles_are_enforced_server_side(tmp_path, monkeypatch):
    tokens = {
        "viewer": "viewer-token-for-test",
        "researcher": "researcher-token-for-test",
        "steward": "steward-token-for-test",
    }
    path = _write_principals(
        tmp_path,
        [
            _row(role, token, role=role, workspace="shared-lab")
            for role, token in tokens.items()
        ],
    )
    monkeypatch.setenv("DESK_PRINCIPALS_FILE", str(path))
    monkeypatch.setenv("YZU_DESK_SESSION_SIGNING_SECRET", "session-secret-for-test")
    monkeypatch.delenv("YZU_DESK_ACCESS_TOKEN", raising=False)

    viewer = FakeHandler(Authorization=f"Bearer {tokens['viewer']}")
    researcher = FakeHandler(Authorization=f"Bearer {tokens['researcher']}")
    steward = FakeHandler(Authorization=f"Bearer {tokens['steward']}")

    assert desk_auth.authorize(viewer, "/datasets", "GET")[0] is True
    allowed, message = desk_auth.authorize(viewer, "/library/chat", "POST")
    assert allowed is False and "use_ask" in message
    assert desk_auth.authorize(researcher, "/library/chat", "POST")[0] is True
    allowed, message = desk_auth.authorize(
        researcher, "/library/jobs/approve-safe", "POST"
    )
    assert allowed is False and "approve_jobs" in message
    assert desk_auth.authorize(steward, "/library/jobs/approve-safe", "POST")[0] is True
