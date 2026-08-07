#!/usr/bin/env python3
"""Registry resolves for both checkout layouts, and the gateway wins."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drive"))

from scripts.research_data_mcp.vault_meaning_labeler import resolve_registry_path  # noqa: E402


def _registry(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"datasets": []}), encoding="utf-8")
    return path


def test_runtime_layout_uses_drive_config(tmp_path: Path):
    want = _registry(tmp_path / "drive/config/research_query_registry.json")
    assert resolve_registry_path(tmp_path) == want


def test_private_layout_uses_root_config(tmp_path: Path):
    want = _registry(tmp_path / "config/research_query_registry.json")
    assert resolve_registry_path(tmp_path) == want


def test_root_config_wins_when_both_exist(tmp_path: Path):
    root_cfg = _registry(tmp_path / "config/research_query_registry.json")
    _registry(tmp_path / "drive/config/research_query_registry.json")
    assert resolve_registry_path(tmp_path) == root_cfg


def test_gateway_declaration_beats_layout_guessing(tmp_path: Path):
    _registry(tmp_path / "config/research_query_registry.json")
    elsewhere = _registry(tmp_path / "somewhere/else/research_query_registry.json")

    class Gateway:
        registry_path = str(elsewhere)

    assert resolve_registry_path(tmp_path, Gateway()) == elsewhere


def test_a_gateway_pointing_at_nothing_falls_back(tmp_path: Path):
    want = _registry(tmp_path / "drive/config/research_query_registry.json")

    class Gateway:
        registry_path = str(tmp_path / "absent.json")

    assert resolve_registry_path(tmp_path, Gateway()) == want
