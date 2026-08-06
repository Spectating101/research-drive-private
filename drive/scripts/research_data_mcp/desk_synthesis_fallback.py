#!/usr/bin/env python3
"""Synthesis alternate-brain stub — Gemini fallback is stripped.

Desk judgment is Cursor Composer + MCP only. This module remains so health
payloads and old imports resolve, but never runs a second reasoning provider.
"""

from __future__ import annotations

from typing import Any


class SynthesisFallbackError(RuntimeError):
    """Raised if anything still tries to invoke the stripped Gemini path."""

    def __init__(self, category: str, detail: str = "", *, status_code: int | None = None):
        self.category = str(category or "stripped")
        self.detail = str(detail or "")[:240]
        self.status_code = status_code
        super().__init__(self.detail or self.category)


def gemini_synthesis_enabled() -> bool:
    return False


def gemini_synthesis_configured() -> bool:
    return False


def synthesis_fallback_runtime_status(
    *,
    max_age_seconds: int = 300,
) -> dict[str, Any]:
    _ = max_age_seconds
    return {
        "status": "stripped",
        "verified": True,
        "provider": "none",
        "enabled": False,
        "configured": False,
        "brain": "cursor_composer_mcp_only",
        "note": "Gemini Synthesis fallback removed — Composer + MCP only.",
    }


def run_gemini_synthesis_turn(prompt: str) -> tuple[str, dict[str, Any]]:
    _ = prompt
    raise SynthesisFallbackError(
        "stripped",
        "Gemini Synthesis fallback is stripped; use Cursor Composer + MCP.",
    )


def _reset_synthesis_fallback_runtime_status() -> None:
    """Test helper — no-op after strip."""
    return
