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
