import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.research_query_engine import server


def test_normalize_api_path_keeps_direct_routes_and_strips_api_prefix():
    assert server.normalize_api_path("/health") == "/health"
    assert server.normalize_api_path("/api/health") == "/health"
    assert server.normalize_api_path("/api/library/live-identity") == "/library/live-identity"
    assert server.normalize_api_path("/api") == "/"


def test_is_api_path_does_not_capture_spa_routes():
    assert server.is_api_path("/health")
    assert server.is_api_path("/api/library/chat/stream")
    assert server.is_api_path("/datasets/example")
    assert not server.is_api_path("/")
    assert not server.is_api_path("/library-ui")
    assert not server.is_api_path("/datasets-old")
    assert not server.is_api_path("/discover/history")


def test_cors_is_same_origin_only_by_default(monkeypatch):
    monkeypatch.delenv("YZU_DESK_CORS_ORIGIN", raising=False)
    assert server.normalize_cors_origin() == ""


def test_cors_accepts_one_explicit_origin():
    assert server.normalize_cors_origin("https://desk.example.test/") == "https://desk.example.test"


@pytest.mark.parametrize(
    "value",
    ["*", "desk.example.test", "https://desk.example.test/path", "https://desk.example.test?q=1"],
)
def test_cors_rejects_wildcard_and_non_origin_values(value):
    with pytest.raises(ValueError):
        server.normalize_cors_origin(value)


def test_resolve_static_dir_uses_repo_root_for_relative_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "REPO_ROOT", tmp_path)
    assert server.resolve_static_dir("public/dist") == (tmp_path / "public/dist").resolve()


def test_resolve_static_dir_prefers_explicit_value_over_environment(monkeypatch, tmp_path):
    env_dir = tmp_path / "env-dist"
    explicit_dir = tmp_path / "explicit-dist"
    monkeypatch.setenv("YZU_DESK_STATIC_DIR", str(env_dir))
    assert server.resolve_static_dir(explicit_dir) == explicit_dir.resolve()


def test_require_ui_build_fails_fast_without_index(tmp_path):
    with pytest.raises(FileNotFoundError, match="UI build missing"):
        server.require_ui_build(tmp_path)


def test_require_ui_build_accepts_public_dist(tmp_path):
    index = tmp_path / "index.html"
    index.write_text("<main>Research Drive</main>", encoding="utf-8")
    assert server.require_ui_build(tmp_path) == index


def test_parser_reads_optiplex_environment(monkeypatch, tmp_path):
    static_dir = tmp_path / "dist"
    registry = tmp_path / "registry.json"
    monkeypatch.setenv("YZU_DESK_HOST", "100.64.0.10")
    monkeypatch.setenv("YZU_DESK_PORT", "9876")
    monkeypatch.setenv("YZU_DESK_STATIC_DIR", str(static_dir))
    monkeypatch.setenv("SHARPE_REGISTRY_PATH", str(registry))
    monkeypatch.setenv("YZU_DESK_SERVE_UI", "true")
    monkeypatch.setenv("YZU_DESK_CORS_ORIGIN", "https://desk.example.test")

    args = server.build_parser().parse_args([])

    assert args.host == "100.64.0.10"
    assert args.port == 9876
    assert Path(args.static_dir) == static_dir
    assert Path(args.registry) == registry
    assert args.serve_ui is True
    assert args.cors_origin == "https://desk.example.test"


def test_invalid_environment_port_is_rejected(monkeypatch):
    monkeypatch.setenv("YZU_DESK_PORT", "not-a-port")
    with pytest.raises(ValueError, match="must be an integer"):
        server.build_parser()


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _public_authority(tmp_path: Path) -> tuple[Path, str]:
    public = tmp_path / "public"
    public.mkdir()
    subprocess.run(["git", "init", "-q", str(public)], check=True)
    _git(public, "config", "user.email", "front-door-test@example.invalid")
    _git(public, "config", "user.name", "Front Door Test")
    (public / "authority.txt").write_text("public authority\n", encoding="utf-8")
    _git(public, "add", "authority.txt")
    _git(public, "commit", "-q", "-m", "public authority")
    return public, _git(public, "rev-parse", "HEAD")


def _fake_python(tmp_path: Path) -> tuple[Path, Path]:
    capture = tmp_path / "server-args.txt"
    fake = tmp_path / "python-front-door-test"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ ${1:-} == - ]]; then exec python3 \"$@\"; fi\n"
        "printf '%s\\n' \"$@\" > \"${YZU_TEST_CAPTURE}\"\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake, capture


def _launcher_environment(repo_root: Path, public: Path, public_sha: str, fake_python: Path, capture: Path) -> dict:
    env = os.environ.copy()
    env.update(
        {
            "YZU_PUBLIC_REPO": str(public),
            "YZU_PUBLIC_SHA": public_sha,
            "YZU_DESK_HOST": "100.64.0.10",
            "YZU_DESK_PORT": "8765",
            "YZU_DESK_ACCESS_TOKEN": "test-token",
            "YZU_PYTHON_BIN": str(fake_python),
            "YZU_TEST_CAPTURE": str(capture),
            "SHARPE_REGISTRY_PATH": "drive/config/research_query_registry.json",
        }
    )
    env.pop("YZU_DESK_STATIC_DIR", None)
    return env


def test_optiplex_launcher_accepts_exact_public_and_private_authorities(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    private_sha = _git(repo_root, "rev-parse", "HEAD")
    public, public_sha = _public_authority(tmp_path)
    static_dir = public / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<main>Research Drive</main>", encoding="utf-8")
    (static_dir / "research-drive-build.json").write_text(
        json.dumps({"public_sha": public_sha, "private_sha": private_sha}),
        encoding="utf-8",
    )
    fake_python, capture = _fake_python(tmp_path)
    env = _launcher_environment(repo_root, public, public_sha, fake_python, capture)

    result = subprocess.run(
        ["bash", str(repo_root / "drive/scripts/research_query_engine/run_optiplex_front_door.sh")],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    args = capture.read_text(encoding="utf-8").splitlines()
    assert args[0] == "drive/scripts/research_query_engine/server.py"
    assert "--serve-ui" in args
    assert "100.64.0.10" in args
    assert str(static_dir) in args


def test_optiplex_launcher_rejects_stale_private_build_identity(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    public, public_sha = _public_authority(tmp_path)
    static_dir = public / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<main>Research Drive</main>", encoding="utf-8")
    (static_dir / "research-drive-build.json").write_text(
        json.dumps({"public_sha": public_sha, "private_sha": "stale-private-sha"}),
        encoding="utf-8",
    )
    fake_python, capture = _fake_python(tmp_path)
    env = _launcher_environment(repo_root, public, public_sha, fake_python, capture)

    result = subprocess.run(
        ["bash", str(repo_root / "drive/scripts/research_query_engine/run_optiplex_front_door.sh")],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "rebuild before start" in result.stderr
    assert not capture.exists()
