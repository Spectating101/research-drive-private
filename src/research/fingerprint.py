"""
Reproducibility fingerprint for backtest / signal / scorecard outputs.

Every output that downstream analysis depends on should carry a
{git_commit, git_dirty, panel_sha256, config_sha256, timestamp_utc,
python_version, hostname} block so a future reader can answer:

  - Exactly which code produced this?
  - Exactly which data did it consume?
  - Exactly which config knobs were set?

Without that, two backtests "from the same setup" aren't actually
comparable. With it, every claim is reproducible.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", *args],
            cwd=_REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _git_commit() -> Optional[str]:
    return _git("rev-parse", "HEAD")


def _git_dirty() -> Optional[bool]:
    status = _git("status", "--porcelain")
    if status is None:
        return None
    return bool(status.strip())


def _hash_file(path: Path, *, chunk: int = 1 << 20) -> Optional[str]:
    """sha256 of file contents; None if file missing."""
    if path is None:
        return None
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return None
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for buf in iter(lambda: fh.read(chunk), b""):
                h.update(buf)
        return h.hexdigest()
    except OSError:
        return None


def _hash_obj(obj: Any) -> str:
    """Stable sha256 of any JSON-serializable object."""
    payload = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_fingerprint(
    *,
    panel_path: Optional[Path] = None,
    config: Optional[Mapping[str, Any]] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a fingerprint dict.

    panel_path: input data file to hash (e.g., the daily alpha panel CSV).
    config: any dict of strategy/run params; will be canonical-JSON hashed.
    extra: additional named hashes to compute, mapping label -> Path.
    """
    fp: Dict[str, Any] = {
        "schema": "sharpe-renaissance/fingerprint/v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "git_dirty": _git_dirty(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "hostname": socket.gethostname(),
        "user": os.environ.get("USER") or os.environ.get("USERNAME"),
    }
    if panel_path is not None:
        p = Path(panel_path)
        fp["panel_path"] = str(p)
        fp["panel_sha256"] = _hash_file(p)
        try:
            fp["panel_size_bytes"] = p.stat().st_size if p.exists() else None
        except OSError:
            fp["panel_size_bytes"] = None
    if config is not None:
        fp["config_sha256"] = _hash_obj(config)
    if extra:
        fp["extra_hashes"] = {label: _hash_file(Path(p)) for label, p in extra.items()}
    return fp


def stamp(
    payload: Dict[str, Any],
    *,
    panel_path: Optional[Path] = None,
    config: Optional[Mapping[str, Any]] = None,
    extra: Optional[Mapping[str, Any]] = None,
    key: str = "fingerprint",
) -> Dict[str, Any]:
    """
    Attach a fingerprint to an existing output payload in-place under `key`.
    Returns the (mutated) payload for fluent use.
    """
    payload[key] = make_fingerprint(panel_path=panel_path, config=config, extra=extra)
    return payload
