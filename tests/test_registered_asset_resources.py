from __future__ import annotations

import json
from pathlib import Path

from scripts.research_data_mcp.desk_activity import log_path, read_recent
from scripts.yzu_cluster.jobs import YzuJobStore


def _repo(tmp_path: Path) -> tuple[Path, YzuJobStore]:
    (tmp_path / "config").mkdir()
    (tmp_path / "config/yzu_cluster.json").write_text(
        json.dumps(
            {
                "controller": {
                    "hostname": "optiplex-test",
                    "jobs_root": "data/jobs",
                    "status_root": "data/status",
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": []}),
        encoding="utf-8",
    )
    return tmp_path, YzuJobStore(tmp_path / "data/jobs/jobs.sqlite3")


def _result(dataset_id: str, *, verified: bool = True) -> dict:
    return {
        "registration_evidence": {
            "dataset_id": dataset_id,
            "registry_id": dataset_id,
            "manifest_id": f"manifest-{dataset_id}",
            "vault_path": f"gdrive:Research-Drive/{dataset_id}",
            "archive_verified": verified,
            "registry_readback": verified,
            "readiness": "registered",
            "title": f"Registered {dataset_id}",
        }
    }


def test_resources_activity_projects_verified_registered_asset_without_log_write(tmp_path: Path) -> None:
    root, jobs = _repo(tmp_path)
    jobs.create("Smoke asset", {}, {"job_type": "http_manifest"}, status="completed", job_id="smoke-job")
    jobs.update("smoke-job", "completed", _result("smoke_asset"))
    activity_path = log_path(root)
    assert not activity_path.exists()

    events = read_recent(limit=20, repo_root=root)

    assert len(events) == 1
    event = events[0]
    assert event["id"] == "registered-smoke-job"
    assert event["action"] == "Registered"
    assert event["target"] == "Registered · Registered smoke_asset"
    assert event["meta"]["action"] == "Registered Library asset"
    assert event["meta"]["dataset_id"] == "smoke_asset"
    assert event["meta"]["registry_id"] == "smoke_asset"
    assert event["meta"]["manifest_id"] == "manifest-smoke_asset"
    assert event["meta"]["job_id"] == "smoke-job"
    assert event["meta"]["readiness"] == "registered"
    assert event["meta"]["archive_verified"] is True
    assert event["meta"]["registry_readback"] is True
    assert not activity_path.exists(), "receipt projection must not append a duplicate activity row"


def test_resources_activity_excludes_unverified_completion(tmp_path: Path) -> None:
    root, jobs = _repo(tmp_path)
    jobs.create("Incomplete", {}, {"job_type": "http_manifest"}, status="completed", job_id="incomplete-job")
    jobs.update("incomplete-job", "completed", _result("incomplete_asset", verified=False))

    assert read_recent(limit=20, repo_root=root) == []


def test_logged_and_registered_events_share_one_sorted_feed(tmp_path: Path) -> None:
    root, jobs = _repo(tmp_path)
    jobs.create("Smoke asset", {}, {"job_type": "http_manifest"}, status="completed", job_id="smoke-job")
    jobs.update("smoke-job", "completed", _result("smoke_asset"))

    path = log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "id": "ask-event",
                "ts": "2099-01-01T00:00:00+00:00",
                "action": "ask",
                "target": "Inspect asset",
                "session_id": "session-1",
                "cost": None,
                "meta": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    events = read_recent(limit=20, repo_root=root)

    assert [event["id"] for event in events] == ["ask-event", "registered-smoke-job"]
