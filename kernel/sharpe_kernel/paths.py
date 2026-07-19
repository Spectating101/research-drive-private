"""Filesystem layout for the split Sharpe-Renaissance monorepo."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def repo_root() -> Path:
    env = os.environ.get("SHARPE_REPO_ROOT") or os.environ.get("SR_DIR")
    if env:
        return Path(env).resolve()
    # kernel/sharpe_kernel/paths.py -> repo root
    return Path(__file__).resolve().parents[2]


def repo_root_from_file(path: str | Path) -> Path:
    """Walk up from any file path until repo root (kernel/ + drive/ siblings)."""
    cur = Path(path).resolve()
    if cur.is_file():
        cur = cur.parent
    for candidate in (cur, *cur.parents):
        if (candidate / "kernel").is_dir() and (candidate / "drive").is_dir():
            return candidate
    return repo_root()


def drive_root() -> Path:
    return repo_root() / "drive"


def alpha_root() -> Path:
    return repo_root() / "alpha"


def kernel_root() -> Path:
    return repo_root() / "kernel"


def data_lake_root() -> Path:
    env = os.environ.get("SHARPE_DATA_LAKE")
    if env:
        return Path(env).resolve()
    return repo_root() / "data_lake"


def registry_path() -> Path:
    env = os.environ.get("SHARPE_REGISTRY_PATH")
    if env:
        return Path(env).resolve()
    # Producer lives under drive; root config/ symlink keeps legacy paths working.
    candidate = repo_root() / "config" / "research_query_registry.json"
    if candidate.exists():
        return candidate
    return drive_root() / "config" / "research_query_registry.json"


def integration_config_path() -> Path:
    env = os.environ.get("SHARPE_INTEGRATION_CONFIG")
    if env:
        return Path(env).resolve()
    candidate = repo_root() / "config" / "platform_integration.json"
    if candidate.exists():
        return candidate
    return alpha_root() / "config" / "platform_integration.json"


def bootstrap_repo_paths(caller_file: str | Path) -> Path:
    """Return monorepo root and ensure kernel, alpha, and root are on sys.path."""
    import sys

    root = repo_root_from_file(caller_file)
    for p in (kernel_root(), alpha_root(), root):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)
    return root
