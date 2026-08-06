"""is_question_like lives on discover_composer; catalog_select LLM reader deleted."""

from __future__ import annotations

from scripts.research_data_mcp.discover_composer import is_question_like


def test_is_question_like():
    assert is_question_like("daily country-level news shock data for Taiwan and Japan")
    assert is_question_like("what data can I use to study de-pegs")
    assert not is_question_like("stablecoin")
    assert not is_question_like("CRSP daily")
    assert not is_question_like("gdelt")
    assert not is_question_like("")
