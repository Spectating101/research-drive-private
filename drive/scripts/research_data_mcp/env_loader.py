#!/usr/bin/env python3
"""Load merged .env.local files for procurement / agent services."""

from __future__ import annotations

import os
from pathlib import Path
from sharpe_kernel.paths import repo_root_from_file


def load_procurement_env(repo_root: Path | None = None) -> list[str]:
    """Merge env files; later paths override earlier. Returns paths loaded."""
    root = Path(repo_root or repo_root_from_file(__file__)).resolve()
    candidates = [
        Path.home() / ".env.local",
        root.parent / ".env.local",
        root / ".env.local",
    ]
    loaded: list[str] = []
    for path in candidates:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ[key] = value
        loaded.append(str(path))
    return loaded
