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


def _row(principal_id: str, token: str, *, role: str):
    return {
        "id": principal_id,
        "email": f"{principal_id}@example.test",
        "display_name": principal_id.title(),
        "role": role,
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    }


def test_distinct_tokens_resolve_distinct_principals(tmp_path, monkeypatch):
    alice_token = "alice-token-for-test"
    bob_token = "bob-token-for-test"
    path = _write_principals(
        tmp_path,
        [
            _row("alice", alice_token, role="member"),
            _row("bob", bob_token, role="operator"),
        ],
    )
    monkeypatch.setenv("DESK_PRINCIPALS_FILE", str(path))
    monkeypatch.setenv("YZU_DESK_SESSION_SIGNING_SECRET", "session-secret-for-test")
    monkeypatch.delenv("YZU_DESK_ACCESS_TOKEN", raising=False)

    alice = desk_auth.request_desk_principal(FakeHandler(Authorization=f"Bearer {alice_token}"))
    bob = desk_auth.request_desk_principal(FakeHandler(X_Desk_Token=bob_token))
    assert alice and alice.principal_id == "alice" and alice.role == "member"
    assert bob and bob.principal_id == "bob" and bob.role == "operator"

    alice_doc = desk_auth.desk_capability_document(
        FakeHandler(Authorization=f"Bearer {alice_token}")
    )
    bob_doc = desk_auth.desk_capability_document(FakeHandler(X_Desk_Token=bob_token))
    assert alice_doc["permissions"]["submit_collection"] is True
    assert alice_doc["permissions"]["approve_jobs"] is False
    assert bob_doc["permissions"]["view_research_data"] is True
    assert bob_doc["permissions"]["approve_jobs"] is True
    assert alice_token not in repr(alice_doc)
    assert bob_token not in repr(bob_doc)


def test_v3_cookie_preserves_principal_identity(tmp_path, monkeypatch):
    token = "researcher-token-for-test"
    signing = "session-signing-secret-for-test"
    path = _write_principals(
        tmp_path,
        [_row("member-1", token, role="member")],
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
    assert principal and principal.principal_id == "member-1"
    assert principal.role == "member"


def test_principal_file_never_accepts_raw_token_field(tmp_path, monkeypatch):
    path = _write_principals(
        tmp_path,
        [
            {
                "id": "unsafe-entry",
                "role": "operator",
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
        "member": "member-token-for-test",
        "operator": "operator-token-for-test",
    }
    path = _write_principals(
        tmp_path,
        [
            _row(role, token, role=role)
            for role, token in tokens.items()
        ],
    )
    monkeypatch.setenv("DESK_PRINCIPALS_FILE", str(path))
    monkeypatch.setenv("YZU_DESK_SESSION_SIGNING_SECRET", "session-secret-for-test")
    monkeypatch.delenv("YZU_DESK_ACCESS_TOKEN", raising=False)

    member = FakeHandler(Authorization=f"Bearer {tokens['member']}")
    operator = FakeHandler(Authorization=f"Bearer {tokens['operator']}")

    assert desk_auth.authorize(member, "/datasets", "GET")[0] is True
    assert desk_auth.authorize(member, "/library/jobs", "GET")[0] is True
    assert desk_auth.authorize(member, "/library/chat", "POST")[0] is True
    assert desk_auth.authorize(member, "/library/jobs", "POST")[0] is True
    allowed, message = desk_auth.authorize(
        member, "/library/jobs/approve-safe", "POST"
    )
    assert allowed is False and "approve_jobs" in message
    allowed, message = desk_auth.authorize(
        member, "/library/jobs/example/approve", "POST"
    )
    assert allowed is False and "approve_jobs" in message
    assert desk_auth.authorize(operator, "/library/jobs/approve-safe", "POST")[0] is True


def test_legacy_role_names_collapse_to_two_roles(tmp_path, monkeypatch):
    path = _write_principals(
        tmp_path,
        [
            _row("legacy-researcher", "member-alias-token", role="researcher"),
            _row("legacy-admin", "operator-alias-token", role="admin"),
        ],
    )
    monkeypatch.setenv("DESK_PRINCIPALS_FILE", str(path))
    monkeypatch.setenv("YZU_DESK_SESSION_SIGNING_SECRET", "session-secret-for-test")
    monkeypatch.delenv("YZU_DESK_ACCESS_TOKEN", raising=False)

    member = desk_auth.request_desk_principal(
        FakeHandler(Authorization="Bearer member-alias-token")
    )
    operator = desk_auth.request_desk_principal(
        FakeHandler(Authorization="Bearer operator-alias-token")
    )
    assert member and member.role == "member"
    assert operator and operator.role == "operator"
