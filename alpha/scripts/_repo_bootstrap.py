"""Standalone repo-root resolver (no sharpe_kernel import required)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_repo_root(caller_file: str | Path) -> Path:
    cur = Path(caller_file).resolve()
    if cur.is_file():
        cur = cur.parent
    for candidate in (cur, *cur.parents):
        if (candidate / "kernel").is_dir() and (candidate / "drive").is_dir():
            return candidate
    env = os.environ.get("SHARPE_REPO_ROOT") or os.environ.get("SR_DIR")
    if env:
        return Path(env).resolve()
    raise RuntimeError("Sharpe-Renaissance repo root not found (set SR_DIR or SHARPE_REPO_ROOT)")


def bootstrap_repo_paths(caller_file: str | Path) -> Path:
    """Return monorepo root; ensure kernel, alpha, and root are on sys.path."""
    root = _find_repo_root(caller_file)
    for p in (root / "kernel", root / "alpha", root):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)
    return root


def repo_root_from_file(caller_file: str | Path) -> Path:
    """Return monorepo root without mutating sys.path."""
    return _find_repo_root(caller_file)
