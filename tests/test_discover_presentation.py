"""Discover must not render rows a researcher cannot act on.

A live query returned 13 rows: three had an empty dataset_id (titles present,
nothing to open, collect or assess) and one dataset appeared twice under two
different titles, because dedupe keyed on the row rather than the dataset.
Both render as clickable cards that do nothing.
"""

from __future__ import annotations

from scripts.research_data_mcp.gateway import _presentable_candidates


def test_duplicate_dataset_rows_collapse_even_with_different_titles():
    out = _presentable_candidates([
        {"dataset_id": "a", "title": "Asia Entity-to-Ticker Mapping Layer"},
        {"dataset_id": "a", "title": "Asia entity-to-ticker mapping layer for ..."},
    ])
    assert len(out) == 1


def test_rows_without_an_id_are_dropped():
    out = _presentable_candidates([{"dataset_id": "", "title": "GDELT Asia Daily Country Panel"}])
    assert out == []


def test_external_candidates_survive_without_a_dataset_id():
    """A DOI or URL row is procurable even though it is not yet in the registry."""
    out = _presentable_candidates([
        {"dataset_id": "", "doi": "10.5281/zenodo.1", "title": "external"},
        {"dataset_id": "", "url": "https://example.org/d", "title": "external2"},
    ])
    assert len(out) == 2


def test_order_is_preserved():
    out = _presentable_candidates([{"dataset_id": "a"}, {"dataset_id": "b"}, {"dataset_id": "a"}])
    assert [c["dataset_id"] for c in out] == ["a", "b"]


def test_non_dict_rows_are_ignored():
    assert _presentable_candidates([None, "x", {"dataset_id": "a"}]) == [{"dataset_id": "a"}]
