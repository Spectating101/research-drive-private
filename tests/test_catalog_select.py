"""Reading the whole catalog beats retrieving from it, at this catalog's size.

Measured on 16 questions: agent + full catalog answered 10/10 real questions and
correctly refused 5 of 6 traps with zero invalid ids, while local_search and
discover_search each answered 2/6 -- returning *empty* for four questions whose
answer was in the catalog. Retrieval exists to avoid reading everything; 113
datasets serialise to ~15.5 KB, so it buys nothing and costs recall.
"""

from __future__ import annotations

from scripts.research_data_mcp.catalog_select import (
    build_catalog_text,
    enabled,
    is_question_like,
    parse_selection,
)


def _rows():
    return [
        {"dataset_id": "a", "grain": "country_day", "one_line": "Daily Asia news shock panel"},
        {"dataset_id": "b", "grain": "permno_day", "one_line": "CRSP US daily equity history"},
    ]


def test_catalog_serialises_one_line_per_dataset():
    text = build_catalog_text(_rows())
    assert len(text.splitlines()) == 2
    assert "a | country_day | Daily Asia news shock panel" in text


def test_rows_without_an_id_are_skipped_not_padded():
    """An unidentifiable row cannot be returned as an answer."""
    assert len(build_catalog_text(_rows() + [{"grain": "x", "one_line": "no id"}]).splitlines()) == 2


def test_invalid_ids_are_dropped(): 
    """A plausible id the desk does not hold is worse than no answer."""
    out = parse_selection("a | good\nnot_a_real_dataset | invented\nb | also good", {"a", "b"})
    assert [s["dataset_id"] for s in out] == ["a", "b"]


def test_none_reply_selects_nothing():
    assert parse_selection("NONE", {"a", "b"}) == []


def test_duplicate_ids_are_returned_once():
    assert len(parse_selection("a | one\na | two", {"a"})) == 1


def test_fenced_or_bulleted_output_is_tolerated():
    out = parse_selection("- a | reason\n* b | reason", {"a", "b"})
    assert [s["dataset_id"] for s in out] == ["a", "b"]


# --- routing: keyword queries must not pay for a model call -------------------

def test_research_questions_route_to_the_reader():
    assert is_question_like("daily country-level news shock data for Taiwan and Japan")
    assert is_question_like("what data can I use to study de-pegs")


def test_keyword_queries_stay_on_the_fast_lexical_path():
    """These already return 5-20 results instantly; a model call would only add latency."""
    assert not is_question_like("stablecoin")
    assert not is_question_like("CRSP daily")
    assert not is_question_like("gdelt")
    assert not is_question_like("")


def test_disabled_by_default():
    assert not enabled()
