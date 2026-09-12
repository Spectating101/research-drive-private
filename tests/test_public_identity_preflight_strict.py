from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "drive/scripts/research_query_engine/preflight_release.sh"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False
    ).stdout.strip()


def _repo(path: Path, filename: str) -> str:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    (path / filename).write_text("x = 1\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "init")
    return _git(path, "rev-parse", "HEAD")


@pytest.fixture
def public_release(tmp_path: Path):
    backend = tmp_path / "backend"
    backend_sha = _repo(backend, "code.py")
    # Preflight imports the backend's runtime validator. Link this test fixture
    # to the real module tree rather than copying a weaker fake validator.
    source_drive = Path(__file__).resolve().parents[1] / "drive"
    (backend / "drive").symlink_to(source_drive, target_is_directory=True)
    (backend / "config").mkdir()
    (backend / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "a"}]}), encoding="utf-8"
    )

    ui = tmp_path / "ui"
    ui_sha = _repo(ui, "app.js")
    rel = ui / "releases" / f"{ui_sha}--{backend_sha}"
    rel.mkdir(parents=True)
    (rel / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (rel / "research-drive-build.json").write_text(
        json.dumps(
            {
                "public_sha": ui_sha,
                "private_sha": backend_sha,
                "release_scope": "external-public",
            }
        ),
        encoding="utf-8",
    )
    (ui / "dist").symlink_to(rel)

    env = tmp_path / "front-door.env"
    env.write_text(
        f"SHARPE_REPO_ROOT={backend}\n"
        f"YZU_PUBLIC_REPO={ui}\n"
        f"YZU_PUBLIC_SHA={ui_sha}\n"
        f"YZU_DESK_STATIC_DIR={ui}/dist\n"
        "YZU_DESK_RELEASE_SCOPE=external-public\n"
        "SHARPE_REGISTRY_PATH=config/research_query_registry.json\n"
        f"RESEARCH_DATA_ROOTS={tmp_path}\n",
        encoding="utf-8",
    )
    return env


def _run(env: Path, **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **os.environ,
            "FRONT_DOOR_ENV": str(env),
            "DESK_COMPOSER_PROVIDER": "none",
            **extra,
        },
    )


def test_nonempty_but_invalid_cloudflare_values_do_not_pass_preflight(public_release):
    out = _run(
        public_release,
        DESK_CLOUDFLARE_ACCESS_TEAM_DOMAIN="https://not-cloudflare.example.com",
        DESK_CLOUDFLARE_ACCESS_AUD="looks-nonempty",
    )
    assert out.returncode != 0
    assert "invalid according to runtime configured_access" in out.stdout
    assert "member_sign_in=cloudflare_access" not in out.stdout


def test_valid_cloudflare_shape_uses_runtime_authority(public_release):
    out = _run(
        public_release,
        DESK_CLOUDFLARE_ACCESS_TEAM_DOMAIN="https://research-drive.cloudflareaccess.com",
        DESK_CLOUDFLARE_ACCESS_AUD="research-drive-public",
    )
    # The host may still fail if PyJWT is intentionally absent; the important
    # property here is that the strict runtime authority recognizes the shape.
    assert "invalid according to runtime configured_access" not in out.stdout
    if "external public member sign-in requires PyJWT" not in out.stdout:
        assert "member_sign_in=cloudflare_access" in out.stdout
