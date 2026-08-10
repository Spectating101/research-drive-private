from __future__ import annotations

import json
from pathlib import Path

from scripts.research_data_mcp import drive_first


def _repo_with_storage(tmp_path: Path) -> Path:
    config = tmp_path / "config"
    config.mkdir()
    (config / "storage_tiers.json").write_text(
        json.dumps(
            {
                "tiers": {
                    "canonical": {
                        "drive_root": "gdrive:Vault",
                        "drive_root_folder_id": "root-123",
                        "rclone_pacing": {
                            "transfers": 2,
                            "checkers": 3,
                            "tpslimit": 2,
                            "tpslimit_burst": 2,
                            "drive_pacer_min_sleep": "750ms",
                            "drive_pacer_burst": 4,
                            "retries": 2,
                            "low_level_retries": 3,
                        },
                        "rclone_extra_flags": ["--drive-acknowledge-abuse"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_archive_uses_configured_drive_pacing_and_root(monkeypatch, tmp_path: Path):
    repo = _repo_with_storage(tmp_path)
    local = repo / "payload.txt"
    local.write_text("proof", encoding="utf-8")
    calls: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(drive_first.subprocess, "run", lambda cmd, **_: calls.append(cmd) or Completed())
    out = drive_first.archive_local_to_remote(repo, "payload.txt", "probe")

    assert out["ok"] is True
    assert calls[0][0:2] == ["rclone", "copy"]
    assert ["--transfers", "2"] == calls[0][calls[0].index("--transfers") : calls[0].index("--transfers") + 2]
    assert "--tpslimit" in calls[0]
    assert ["--drive-root-folder-id", "root-123"] == calls[0][calls[0].index("--drive-root-folder-id") : calls[0].index("--drive-root-folder-id") + 2]
    assert "--transfers" not in calls[1]
    assert "--tpslimit" in calls[1]


def test_archive_classifies_drive_quota_failures(monkeypatch, tmp_path: Path):
    repo = _repo_with_storage(tmp_path)
    local = repo / "payload.txt"
    local.write_text("proof", encoding="utf-8")

    class Failed:
        returncode = 1
        stdout = ""
        stderr = "403 rateLimitExceeded: Quota exceeded for quota metric Queries"

    monkeypatch.setattr(drive_first.subprocess, "run", lambda *_args, **_kwargs: Failed())
    out = drive_first.archive_local_to_remote(repo, "payload.txt", "probe")

    assert out["ok"] is False
    assert out["error"] == "drive_rate_limited"
