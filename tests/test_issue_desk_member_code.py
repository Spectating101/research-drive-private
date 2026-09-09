from __future__ import annotations

import hashlib
import json

from scripts.research_query_engine import issue_desk_member_code


def test_dry_run_does_not_create_registry(tmp_path, capsys):
    path = tmp_path / "principals.json"
    assert issue_desk_member_code.main(
        ["--file", str(path), "--principal-id", "r1", "--display-name", "Researcher", "--email", "r1@example.test"]
    ) == 0
    assert not path.exists()
    assert "DRY RUN" in capsys.readouterr().out


def test_write_stores_only_digest_and_preserves_existing_rows(tmp_path, capsys):
    path = tmp_path / "principals.json"
    path.write_text(json.dumps({"principals": [{"id": "operator", "role": "operator", "token_sha256": "a" * 64}]}))
    assert issue_desk_member_code.main(
        ["--file", str(path), "--principal-id", "r1", "--display-name", "Researcher", "--email", "R1@Example.Test", "--write"]
    ) == 0
    code = capsys.readouterr().out.splitlines()[-1]
    payload = json.loads(path.read_text())
    assert path.stat().st_mode & 0o777 == 0o600
    assert len(payload["principals"]) == 2
    row = payload["principals"][-1]
    assert row == {
        "id": "r1",
        "email": "r1@example.test",
        "display_name": "Researcher",
        "role": "public_member",
        "token_sha256": hashlib.sha256(code.encode()).hexdigest(),
    }
    assert code not in path.read_text()


def test_duplicate_principal_is_refused(tmp_path, capsys):
    path = tmp_path / "principals.json"
    path.write_text(json.dumps({"principals": [{"id": "r1"}]}))
    assert issue_desk_member_code.main(
        ["--file", str(path), "--principal-id", "r1", "--display-name", "Researcher", "--email", "r1@example.test", "--write"]
    ) == 2
    assert "already exists" in capsys.readouterr().err
