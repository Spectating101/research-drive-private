#!/usr/bin/env python3
"""The gate must refuse a release that is not what it claims to be.

Written after two self-inflicted outages and a review finding. The first version checked UI
dirtiness and not backend dirtiness, so it returned ready while backend source differed from
the SHA being deployed — the exact condition the gate exists to catch. An untested gate is
not a gate.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "drive/scripts/research_query_engine/preflight_release.sh"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True).stdout.strip()


def _repo(path: Path, filename: str = "code.py") -> str:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    (path / filename).write_text("x = 1\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "init")
    return _git(path, "rev-parse", "HEAD")


@pytest.fixture
def release(tmp_path):
    """A coherent release: backend and UI clean, identity naming both SHAs, releases/ present."""
    backend = tmp_path / "backend"
    backend_sha = _repo(backend)
    (backend / "config").mkdir(parents=True, exist_ok=True)
    (backend / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "a"}]}), encoding="utf-8")

    ui = tmp_path / "ui"
    ui_sha = _repo(ui, "app.js")
    release_id = f"{ui_sha}--{backend_sha}"
    rel = ui / "releases" / release_id
    rel.mkdir(parents=True)
    (rel / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (rel / "research-drive-build.json").write_text(
        json.dumps({"public_sha": ui_sha, "private_sha": backend_sha}), encoding="utf-8")
    (ui / "dist").symlink_to(rel)

    env = tmp_path / "front-door.env"
    env.write_text(
        f"SHARPE_REPO_ROOT={backend}\n"
        f"YZU_PUBLIC_REPO={ui}\n"
        f"YZU_PUBLIC_SHA={ui_sha}\n"
        f"YZU_DESK_STATIC_DIR={ui}/dist\n"
        f"SHARPE_REGISTRY_PATH=config/research_query_registry.json\n"
        f"RESEARCH_DATA_ROOTS={tmp_path}\n",
        encoding="utf-8")
    return {"env": env, "backend": backend, "ui": ui, "backend_sha": backend_sha,
            "ui_sha": ui_sha, "release_id": release_id, "release_dir": rel}


def _run(env_file: Path, **extra) -> subprocess.CompletedProcess:
    import os

    environ = {**os.environ, "FRONT_DOOR_ENV": str(env_file), **{k: str(v) for k, v in extra.items()}}
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=environ, timeout=120)


def test_a_coherent_release_is_ready(release):
    out = _run(release["env"])
    assert out.returncode == 0, out.stdout + out.stderr
    assert "READY" in out.stdout


def test_a_modified_backend_file_is_refused(release):
    """The hole review found: runtime source differing from the SHA being deployed."""
    (release["backend"] / "code.py").write_text("x = 2  # drifted\n", encoding="utf-8")
    out = _run(release["env"])
    assert out.returncode != 0
    assert "modified tracked path" in out.stdout
    assert "NOT READY" in out.stdout


def test_a_moved_ui_checkout_is_refused(release):
    """Outage one: the UI tree moved under a hardcoded expected SHA."""
    env = release["env"].read_text(encoding="utf-8").replace(release["ui_sha"], "0" * 40)
    release["env"].write_text(env, encoding="utf-8")
    out = _run(release["env"])
    assert out.returncode != 0
    assert "!= expected" in out.stdout


def test_a_build_naming_another_backend_is_refused(release):
    identity = release["release_dir"] / "research-drive-build.json"
    identity.write_text(json.dumps({"public_sha": release["ui_sha"], "private_sha": "f" * 40}),
                        encoding="utf-8")
    out = _run(release["env"])
    assert out.returncode != 0
    assert "build names backend" in out.stdout


def test_a_dist_with_no_release_directory_is_refused(release):
    """Outage two: a dist symlink with no releases/<sha>/ behind it."""
    import shutil

    shutil.rmtree(release["release_dir"])
    out = _run(release["env"])
    assert out.returncode != 0


def test_untracked_backend_files_warn_but_do_not_block(release):
    (release["backend"] / "scratch_notes.txt").write_text("note\n", encoding="utf-8")
    out = _run(release["env"])
    assert out.returncode == 0
    assert "untracked backend path" in out.stdout


def test_preflight_can_validate_a_staged_pair_without_changing_live_dist(release):
    """Promotion must validate its candidate, not the old dist target from front-door.env."""
    staged = release["ui"] / "releases" / release["release_id"]
    out = _run(release["env"], PREFLIGHT_STATIC_DIR=staged)
    assert out.returncode == 0, out.stdout + out.stderr


def test_preflight_can_validate_a_staged_backend_without_repointing_live_env(release, tmp_path):
    """The live environment names its current checkout, not a staged candidate."""
    candidate = tmp_path / "candidate-backend"
    candidate_sha = _repo(candidate, "candidate.py")
    (candidate / "config").mkdir(parents=True)
    (candidate / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "candidate"}]}), encoding="utf-8"
    )
    staged = release["ui"] / "releases" / f"{release['ui_sha']}--{candidate_sha}"
    staged.mkdir()
    (staged / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (staged / "research-drive-build.json").write_text(
        json.dumps({"public_sha": release["ui_sha"], "private_sha": candidate_sha}),
        encoding="utf-8",
    )

    out = _run(
        release["env"],
        SHARPE_REPO_ROOT=candidate,
        PREFLIGHT_STATIC_DIR=staged,
    )

    assert out.returncode == 0, out.stdout + out.stderr
    assert candidate_sha in out.stdout


def test_restartability_check_is_part_of_the_release_gate_when_required(release, tmp_path):
    probe = tmp_path / "restart-probe.sh"
    probe.write_text("#!/usr/bin/env bash\necho restartability=ready\n", encoding="utf-8")
    probe.chmod(0o755)
    out = _run(
        release["env"],
        PREFLIGHT_CHECK_RESTARTABILITY="1",
        PREFLIGHT_RESTARTABILITY_SCRIPT=probe,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "restartability=ready" in out.stdout


def test_failed_restartability_check_refuses_promotion_preflight(release, tmp_path):
    probe = tmp_path / "restart-probe.sh"
    probe.write_text("#!/usr/bin/env bash\necho unit-not-enabled\nexit 1\n", encoding="utf-8")
    probe.chmod(0o755)
    out = _run(
        release["env"],
        PREFLIGHT_CHECK_RESTARTABILITY="1",
        PREFLIGHT_RESTARTABILITY_SCRIPT=probe,
    )
    assert out.returncode != 0
    assert "restartability preflight failed" in out.stdout
    assert "unit-not-enabled" in out.stdout


def test_json_mode_reports_readiness_and_the_fingerprint(release):
    proc = subprocess.run(["bash", str(SCRIPT), "--json"], capture_output=True, text=True,
                          env={**__import__("os").environ, "FRONT_DOOR_ENV": str(release["env"])},
                          timeout=120)
    payload = json.loads(proc.stdout)
    assert payload["ready"] is True
    assert payload["backend_sha"] == release["backend_sha"]
    assert payload["registry_rows"] == 1
    assert payload["registry_sha256_16"]
    assert payload["registry_authority"] == "git"


def test_expected_runtime_registry_link_is_a_ready_release(release, tmp_path):
    runtime = tmp_path / "runtime"
    (runtime / "config").mkdir(parents=True)
    expected = runtime / "config/research_query_registry.json"
    expected.write_text(json.dumps({"datasets": [{"dataset_id": "runtime"}]}), encoding="utf-8")
    local = release["backend"] / "config/research_query_registry.json"
    local.unlink()
    local.symlink_to(expected)
    with release["env"].open("a", encoding="utf-8") as handle:
        handle.write(f"YZU_RUNTIME_DRIVE_ROOT={runtime}\n")
    out = _run(release["env"])
    assert out.returncode == 0, out.stdout + out.stderr
    assert "registry_mode runtime" in out.stdout


def test_runtime_registry_link_to_another_target_is_refused(release, tmp_path):
    runtime = tmp_path / "runtime"
    (runtime / "config").mkdir(parents=True)
    (runtime / "config/research_query_registry.json").write_text('{"datasets": []}', encoding="utf-8")
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"datasets": [{"dataset_id": "wrong"}]}), encoding="utf-8")
    local = release["backend"] / "config/research_query_registry.json"
    local.unlink()
    local.symlink_to(other)
    with release["env"].open("a", encoding="utf-8") as handle:
        handle.write(f"YZU_RUNTIME_DRIVE_ROOT={runtime}\n")
    out = _run(release["env"])
    assert out.returncode != 0
    assert "runtime registry target mismatch" in out.stdout
