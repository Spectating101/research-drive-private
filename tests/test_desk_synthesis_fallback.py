"""Gemini Synthesis fallback is stripped — Composer + MCP only."""

from __future__ import annotations


def test_gemini_synthesis_stripped():
    from scripts.research_data_mcp import desk_synthesis_fallback as fallback

    assert fallback.gemini_synthesis_enabled() is False
    assert fallback.gemini_synthesis_configured() is False
    status = fallback.synthesis_fallback_runtime_status()
    assert status["status"] == "stripped"
    assert status["enabled"] is False
    assert status["brain"] == "cursor_composer_mcp_only"
    try:
        fallback.run_gemini_synthesis_turn("should not run")
        raise AssertionError("run_gemini_synthesis_turn must raise")
    except fallback.SynthesisFallbackError as exc:
        assert exc.category == "stripped"
