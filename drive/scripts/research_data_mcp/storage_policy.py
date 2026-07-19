#!/usr/bin/env python3
"""Canonical storage policy (three-tier: GDrive / USB cache / NVMe desk)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.research_data_mcp.storage_tiers import load_unified_storage_policy


def load_storage_policy(repo_root: Path) -> dict[str, Any]:
    return load_unified_storage_policy(repo_root)
