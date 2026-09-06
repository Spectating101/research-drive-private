#!/usr/bin/env python3
"""Promotion is atomic only if the staged pair survives the real preflight first.

These tests exercise the release scripts as a composed boundary without requiring
systemd or a deployed host. Host-only restartability is represented by a bounded
probe, while build identity, checkout cleanliness, registry authority, candidate
location, and the actual symlink swap are all handled by the production scripts.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROMOTE = ROOT / "drive/scripts/research_query_engine/promote_front_door.sh"


def _run(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _git(cwd: Path, *args: str) -> str:
    proc = _run("git", "-C", str(cwd), *args)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip()


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Research Drive test")


def _commit_all(path: Path, message: str) -> str:
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", message)
    return _git(path, "rev-parse", "HEAD")


def _write_release(ui: Path, ui_sha: str, backend_sha: str) -> tuple[str, Path]:
    release_id = f"{ui_sha}--{backend_sha}"
    release = ui / "releases" / release_id
    release.mkdir(parents=True, exist_ok=True)
    (release / "index.html").write_text("<!doctype html><title>Research Drive</title>\n", encoding="utf-8")
    (release / "research-drive-build.json").write_text(
        json.dumps({"public_sha": ui_sha, "private_sha": backend_sha}),
        encoding="utf-8",
    )
    return release_id, release


@pytest.fixture
def release_pair(tmp_path: Path) -> dict[str, object]:
    backend = tmp_path / "backend"
    _init_repo(backend)
    (backend / "config").mkdir(parents=True)
    (backend / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "held_asset"}]}),
        encoding="utf-8",
    )
    (backend / "runtime.py").write_text("READY = True\n", encoding="utf-8")
    backend_sha = _commit_all(backend, "backend authority")

    ui = tmp_path / "ui"
    _init_repo(ui)
    (ui / "package.json").write_text('{"name":"release-test"}\n', encoding="utf-8")
    (ui / "app.js").write_text("export const version = 1;\n", encoding="utf-8")
    old_ui_sha = _commit_all(ui, "old ui")
    (ui / "app.js").write_text("export const version = 2;\n", encoding="utf-8")
    new_ui_sha = _commit_all(ui, "new ui")

    old_id, old_release = _write_release(ui, old_ui_sha, backend_sha)
    new_id, new_release = _write_release(ui, new_ui_sha, backend_sha)
    (ui / "dist").symlink_to(old_release)

    env_file = tmp_path / "front-door.env"
    env_file.write_text(
        "\n".join(
            [
                f"SHARPE_REPO_ROOT={backend}",
                f"YZU_PUBLIC_REPO={ui}",
                f"YZU_PUBLIC_SHA={new_ui_sha}",
                f"YZU_DESK_STATIC_DIR={ui / 'dist'}",
                "SHARPE_REGISTRY_PATH=config/research_query_registry.json",
                f"RESEARCH_DATA_ROOTS={tmp_path}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    restart_ok = tmp_path / "restart-ok.sh"
    restart_ok.write_text("#!/usr/bin/env bash\necho restartability=ready\n", encoding="utf-8")
    restart_ok.chmod(0o755)

    restart_fail = tmp_path / "restart-fail.sh"
    restart_fail.write_text("#!/usr/bin/env bash\necho restartability=not-ready\nexit 1\n", encoding="utf-8")
    restart_fail.chmod(0o755)

    return {
        "backend": backend,
        "backend_sha": backend_sha,
        "ui": ui,
        "old_id": old_id,
        "old_release": old_release,
        "new_id": new_id,
        "new_release": new_release,
        "env_file": env_file,
        "restart_ok": restart_ok,
        "restart_fail": restart_fail,
    }


def _promotion_env(pair: dict[str, object], probe: Path) -> dict[str, str]:
    return {
        **os.environ,
        "YZU_PUBLIC_REPO": str(pair["ui"]),
        "FRONT_DOOR_ENV": str(pair["env_file"]),
        "PREFLIGHT_RESTARTABILITY_SCRIPT": str(probe),
    }


def _live_target(pair: dict[str, object]) -> Path:
    return (Path(str(pair["ui"])) / "dist").resolve()


def test_coherent_candidate_is_preflighted_then_atomically_promoted(release_pair):
    proc = _run(
        "bash",
        str(PROMOTE),
        str(release_pair["new_id"]),
        env=_promotion_env(release_pair, Path(str(release_pair["restart_ok"]))),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "preflight=ready" in proc.stdout
    assert f"promoted={release_pair['new_id']}" in proc.stdout
    assert f"previous={release_pair['old_id']}" in proc.stdout
    assert _live_target(release_pair) == Path(str(release_pair["new_release"])).resolve()


def test_identity_mismatch_refuses_before_live_link_moves(release_pair):
    identity = Path(str(release_pair["new_release"])) / "research-drive-build.json"
    identity.write_text(
        json.dumps({"public_sha": "f" * 40, "private_sha": release_pair["backend_sha"]}),
        encoding="utf-8",
    )
    before = _live_target(release_pair)
    proc = _run(
        "bash",
        str(PROMOTE),
        str(release_pair["new_id"]),
        env=_promotion_env(release_pair, Path(str(release_pair["restart_ok"]))),
    )
    assert proc.returncode != 0
    assert "staged identity pair" in (proc.stdout + proc.stderr)
    assert _live_target(release_pair) == before


def test_failed_restartability_preflight_leaves_old_release_live(release_pair):
    before = _live_target(release_pair)
    proc = _run(
        "bash",
        str(PROMOTE),
        str(release_pair["new_id"]),
        env=_promotion_env(release_pair, Path(str(release_pair["restart_fail"]))),
    )
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "preflight refused this release" in combined
    assert "restartability preflight failed" in combined
    assert _live_target(release_pair) == before


def test_real_directory_at_live_path_is_never_replaced(release_pair):
    live = Path(str(release_pair["ui"])) / "dist"
    live.unlink()
    live.mkdir()
    (live / "keep.txt").write_text("do not replace\n", encoding="utf-8")
    proc = _run(
        "bash",
        str(PROMOTE),
        str(release_pair["new_id"]),
        env=_promotion_env(release_pair, Path(str(release_pair["restart_ok"]))),
    )
    assert proc.returncode != 0
    assert "refusing to replace a real directory" in (proc.stdout + proc.stderr)
    assert (live / "keep.txt").read_text(encoding="utf-8") == "do not replace\n"
