#!/usr/bin/env python3
"""An answer needs a recorded query tool call. Prose alone is not evidence."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drive"))

from scripts.research_data_mcp.discover_composer import verified_answer  # noqa: E402

ANSWER = {
    "answer": {
        "text": "1,043 distinct tickers, earliest 2015-01-05.",
        "from": ["twse_daily_quotes"],
        "via": "research_query_dataset",
    }
}
HELD = ["twse_daily_quotes", "refinitiv_risk_tape_daily"]


def test_answer_survives_when_the_query_tool_actually_ran():
    out = verified_answer(ANSWER, ["research_discover_desk", "research_query_dataset"], HELD)
    assert out is not None
    assert out["text"].startswith("1,043 distinct tickers")
    assert out["from"] == ["twse_daily_quotes"]
    assert out["via"] == "research_query_dataset"


def test_answer_is_dropped_when_no_query_tool_ran():
    assert verified_answer(ANSWER, ["research_discover_desk", "cursor_composer"], HELD) is None


def test_answer_is_dropped_when_claimed_tool_was_not_called():
    # Self-reported provenance must match what was observed. A model that
    # misreports which tool it used is not a model to trust the number from.
    assert verified_answer(ANSWER, ["research_analyze_dataset"], HELD) is None
    assert verified_answer(ANSWER, ["research_describe_dataset"], HELD) is None


def test_answer_cannot_cite_a_dataset_the_desk_does_not_hold():
    invented = {"answer": {**ANSWER["answer"], "from": ["compustat_na_fundamentals_annual"]}}
    assert verified_answer(invented, ["research_query_dataset"], HELD) is None


def test_empty_or_missing_answer_is_none():
    assert verified_answer({}, ["research_query_dataset"], HELD) is None
    assert verified_answer(None, ["research_query_dataset"], HELD) is None
    blank = {"answer": {"text": "   ", "from": ["twse_daily_quotes"]}}
    assert verified_answer(blank, ["research_query_dataset"], HELD) is None


def test_analyze_dataset_also_counts_as_evidence():
    via_analyze = {"answer": {**ANSWER["answer"], "via": "research_analyze_dataset"}}
    out = verified_answer(via_analyze, ["research_analyze_dataset"], HELD)
    assert out is not None
    assert out["via"] == "research_analyze_dataset"
