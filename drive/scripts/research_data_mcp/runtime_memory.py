#!/usr/bin/env python3
"""Release-independent mutable state paths for the Research Drive desk.

Immutable release checkouts are code authorities, not database authorities.
Production already exposes ``YZU_RUNTIME_DRIVE_ROOT`` for mutable registry and
procured data; desk memory follows that same runtime root so a release switch
cannot strand private chat, Discover, or Synthesis state in the old checkout.
"""

from __future__ import annotations

import os
from pathlib import Path


def procurement_memory_root(repo_root: str | Path) -> Path:
    """Return the durable procurement-memory directory for this process.

    ``RESEARCH_DRIVE_MEMORY_ROOT`` is an explicit host override.  Otherwise a
    configured runtime drive owns the state.  Repo-local storage remains the
    deterministic development/test fallback.
    """

    root = Path(repo_root).expanduser().resolve()
    explicit = str(os.getenv("RESEARCH_DRIVE_MEMORY_ROOT") or "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        return (path if path.is_absolute() else root / path).resolve()
    runtime = str(os.getenv("YZU_RUNTIME_DRIVE_ROOT") or "").strip()
    if runtime:
        return Path(runtime).expanduser().resolve() / "data_lake/procurement_memory"
    return root / "data_lake/procurement_memory"


def procurement_memory_path(repo_root: str | Path, *parts: str) -> Path:
    return procurement_memory_root(repo_root).joinpath(*parts)
