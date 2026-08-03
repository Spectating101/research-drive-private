from pathlib import Path

import pytest

from scripts.research_data_mcp.unified_search import filter_query_relevant_rows


REPO = Path(__file__).resolve().parents[1]


def test_unified_search_drops_available_but_unrelated_rows_for_keeling_curve():
    query = "What public monthly atmospheric CO₂ measurements can I use to illustrate the Keeling Curve?"
    rows = [
        {"title": "Google BigQuery on-chain transfers", "description": "Public crypto transaction data"},
        {"title": "CoinGecko market archive", "description": "Daily crypto prices"},
        {"title": "NOAA atmospheric CO2", "description": "Monthly Mauna Loa Keeling Curve measurements"},
    ]
    kept = filter_query_relevant_rows(rows, query)
    assert [row["title"] for row in kept] == ["NOAA atmospheric CO2"]
    assert kept[0]["query_relevance"] >= 1.0


def test_compound_need_requires_two_terms_not_generic_growth():
    rows = [
        {"title": "NHANES infant growth measurements"},
        {"title": "Stablecoin Trust-Engagement Weekly Panel", "recommended_use": "study market growth"},
    ]
    assert [row["title"] for row in filter_query_relevant_rows(rows, "infant growth measurements by month")] == [
        "NHANES infant growth measurements"
    ]


def test_named_geography_is_required_not_a_ranking_bonus():
    rows = [
        {"title": "Taiwan MOPS governance filings"},
        {"title": "SEC EDGAR governance filings", "description": "United States companies"},
    ]
    assert [row["title"] for row in filter_query_relevant_rows(rows, "MOPS Taiwan governance filings")] == [
        "Taiwan MOPS governance filings"
    ]


def test_two_letter_us_constraint_drops_irish_polling():
    rows = [
        {"title": "Irish Polling Indicator"},
        {"title": "American National Election Studies polling data"},
    ]
    assert [row["title"] for row in filter_query_relevant_rows(rows, "US polling data")] == [
        "American National Election Studies polling data"
    ]


def test_identifier_abbreviation_is_not_mistaken_for_indonesia():
    rows = [{"title": "Entity ID mapping crosswalk"}]
    assert [row["title"] for row in filter_query_relevant_rows(rows, "dataset ID mapping")] == [
        "Entity ID mapping crosswalk"
    ]


def test_united_kingdom_is_not_mistaken_for_united_states():
    rows = [
        {"title": "British Election Study polling"},
        {"title": "United States election polling"},
    ]
    assert [row["title"] for row in filter_query_relevant_rows(rows, "United Kingdom election polling")] == [
        "British Election Study polling"
    ]


@pytest.mark.parametrize(
    "query,required,forbidden",
    [
        (
            "infant growth measurements by month",
            {"nhanes"},
            {"stablecoin", "etherscan", "coingecko"},
        ),
        (
            "MOPS Taiwan governance filings",
            {"taiwan", "mops"},
            {"sec edgar", "irish"},
        ),
        (
            "What public monthly atmospheric CO₂ measurements can I use to illustrate the Keeling Curve?",
            set(),
            {"stablecoin", "etherscan", "coingecko", "bigquery"},
        ),
    ],
)
def test_real_registry_federation_obeys_compound_and_geography_constraints(
    query: str, required: set[str], forbidden: set[str]
) -> None:
    from scripts.research_data_mcp.gateway import ResearchDataGateway

    gateway = ResearchDataGateway(REPO / "drive")
    out = gateway.unified_dataset_search(
        query,
        limit=12,
        include_hf=False,
        include_datacite=False,
    )
    titles = " ".join(str(row.get("title") or "") for row in (out.get("rows") or [])).lower()
    assert all(term in titles for term in required), (query, titles)
    assert not any(term in titles for term in forbidden), (query, titles)
