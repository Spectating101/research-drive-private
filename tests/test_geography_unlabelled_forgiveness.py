#!/usr/bin/env python3
"""An unlabelled row is not the same as a wrong-country row.

Root cause traced live: three well-tagged Refinitiv rows (relevance 15-16,
proven query-ready) declare no geography anywhere -- not in tags, not in
coverage_metadata -- so "US equity fundamentals" excluded every one of them
on missing metadata despite a near-perfect topical match. The gate treated
silence as a confirmed wrong country, the same conflation readiness_truth.py
exists to avoid for query_ready.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drive"))

from scripts.research_data_mcp.procurement_search import (  # noqa: E402
    query_geography_ok,
    row_geography_claims,
)

REFINITIV_PIT = {
    "dataset_id": "refinitiv_index_membership_pit",
    "tags": ["refinitiv", "index-membership", "point-in-time", "universe"],
    "keywords": [
        "index", "constituents", "membership", "point-in-time", "historical",
        "universe", "benchmark", "equity", "backtest", "asof",
    ],
}

QUERY = "we need US equity fundamentals and point-in-time index membership for a survivorship-free backtest"


def test_a_strong_unlabelled_match_is_no_longer_excluded():
    assert row_geography_claims(REFINITIV_PIT) == []
    assert query_geography_ok(REFINITIV_PIT, QUERY) is True


def test_a_weak_unlabelled_match_still_gets_no_free_pass():
    """The false-positive ceiling measured live: single incidental hits topped
    out at 3.0. A row that clears the geography gate purely because nothing
    was tagged, with no real topical support either, should stay excluded."""
    weak = {"dataset_id": "x", "title": "Irish Polling Indicator"}
    assert row_geography_claims(weak) == []
    assert query_geography_ok(weak, "US polling data") is False


def test_a_row_naming_a_different_real_country_is_still_excluded():
    taiwan_row = {"dataset_id": "twse_daily", "tags": ["taiwan", "twse"]}
    assert row_geography_claims(taiwan_row)
    assert query_geography_ok(taiwan_row, "Korea market data") is False


def test_a_row_matching_the_required_country_still_passes():
    us_row = {"dataset_id": "y", "tags": ["united states", "equity"]}
    assert query_geography_ok(us_row, "US equity data") is True


def test_no_geography_named_in_the_query_is_unaffected():
    assert query_geography_ok({"dataset_id": "z"}, "quarterly revenue trends") is True


def test_row_geography_claims_reports_every_matching_country_not_just_one():
    multi = {"dataset_id": "w", "tags": ["taiwan", "japan", "asia-pacific"]}
    claims = row_geography_claims(multi)
    assert len(claims) >= 2
