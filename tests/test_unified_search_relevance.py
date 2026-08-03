from scripts.research_data_mcp.unified_search import filter_query_relevant_rows


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
