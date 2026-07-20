#!/usr/bin/env python3
"""cursor_composer_available must require an importable cursor_sdk."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "kernel"), str(REPO / "drive")]


def test_cursor_composer_available_false_without_key(monkeypatch):
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    from scripts.research_data_mcp import desk_brain

    importlib.reload(desk_brain)
    assert desk_brain.cursor_composer_available() is False


def test_cursor_composer_available_false_when_sdk_missing(monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    import builtins

    real_import = builtins.__import__

    def _block_cursor_sdk(name, *args, **kwargs):
        if name == "cursor_sdk" or name.startswith("cursor_sdk."):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_cursor_sdk)
    from scripts.research_data_mcp import desk_brain

    importlib.reload(desk_brain)
    assert desk_brain.cursor_composer_available() is False
