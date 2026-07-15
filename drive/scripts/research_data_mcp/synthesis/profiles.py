"""Load synthesis profile definitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = "config/synthesis_profiles.json"


def synthesis_config_path(repo_root: Path) -> Path:
    for candidate in (
        repo_root / "drive" / "config" / "synthesis_profiles.json",
        repo_root / "config" / "synthesis_profiles.json",
    ):
        if candidate.is_file():
            return candidate
    return repo_root / "drive" / "config" / "synthesis_profiles.json"


def load_profiles(repo_root: Path) -> dict[str, Any]:
    path = synthesis_config_path(repo_root)
    if not path.is_file():
        return {"version": 1, "profiles": []}
    return json.loads(path.read_text(encoding="utf-8"))


def get_profile(repo_root: Path, profile_id: str) -> dict[str, Any] | None:
    data = load_profiles(repo_root)
    for row in data.get("profiles") or []:
        if row.get("id") == profile_id:
            return dict(row)
    return None


def list_profile_summaries(repo_root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in load_profiles(repo_root).get("profiles") or []:
        out.append(
            {
                "id": row.get("id"),
                "title": row.get("title"),
                "type": row.get("type"),
                "description": row.get("description"),
                "join_keys": row.get("join_keys") or [],
                "sources": row.get("sources") or [],
                "research_questions": row.get("research_questions") or [],
            }
        )
    return out
