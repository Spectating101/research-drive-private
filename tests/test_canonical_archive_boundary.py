from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.research_data_mcp import drive_first, gdrive_verify


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "data_lake" / "staging").mkdir(parents=True)
    (tmp_path / "config" / "storage_tiers.json").write_text(
        json.dumps({"tiers": {"canonical": {"drive_root": "gdrive:Machine_Archive/Research-Drive"}}}),
        encoding="utf-8",
    )
    (tmp_path / "data_lake" / "staging" / "evidence.txt").write_text("evidence", encoding="utf-8")
    return tmp_path


def test_archive_refuses_host_files_and_destinations_outside_canonical_root(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        drive_first.subprocess,
        "run",
        lambda cmd, **kwargs: calls.append(list(cmd)) or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    outside_source = drive_first.archive_local_to_remote(root, "config/storage_tiers.json", "collection/probe")
    assert outside_source["error"] == "archive_local_path_outside_data_lake"

    for suffix in ("../outside", "/outside", "collection/../../outside", "collection//outside"):
        out = drive_first.archive_local_to_remote(root, "data_lake/staging/evidence.txt", suffix)
        assert out["ok"] is False
        assert out["error"].startswith("archive_remote_suffix")

    assert calls == []


def test_archive_destination_is_always_under_configured_canonical_root(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        drive_first.subprocess,
        "run",
        lambda cmd, **kwargs: calls.append(list(cmd)) or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    out = drive_first.archive_local_to_remote(root, "data_lake/staging/evidence.txt", "collection/acquired/probe")
    assert out["ok"] is True
    assert out["remote_path"] == "gdrive:Machine_Archive/Research-Drive/collection/acquired/probe"
    assert all(
        any("gdrive:Machine_Archive/Research-Drive" in part for part in command)
        for command in calls
    )


def test_archive_health_hides_unrelated_rclone_remotes(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(gdrive_verify, "rclone_ready", lambda: True)
    monkeypatch.setattr(gdrive_verify, "rclone_remotes", lambda: ["gdrive", "personal", "another-secret-name"])
    monkeypatch.setattr(
        gdrive_verify.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="collection\n", stderr=""),
    )

    status = gdrive_verify.gdrive_verify_status(root)
    assert status["ready"] is True
    assert status["canonical_remote"] == "gdrive"
    assert "remotes" not in status


def test_archive_exercise_is_scoped_and_cleans_its_exact_probe(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(gdrive_verify, "rclone_ready", lambda: True)
    monkeypatch.setattr(gdrive_verify, "rclone_remotes", lambda: ["gdrive"])

    def run(cmd, **kwargs):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0, stdout="probe.ready\n", stderr="")

    monkeypatch.setattr(gdrive_verify.subprocess, "run", run)
    out = gdrive_verify.exercise_canonical_archive(root)
    assert out["exercise_ok"] is True
    joined = "\n".join(" ".join(row) for row in calls)
    assert "collection/.rd_release_probe/release-" in joined
    assert any(row[1] == "touch" for row in calls)
    assert any(row[1] == "deletefile" for row in calls)
    assert any(row[1] == "rmdir" for row in calls)
