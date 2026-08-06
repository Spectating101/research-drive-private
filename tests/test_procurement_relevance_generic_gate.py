"""L0 vault relevance — generic-only coincidence must not pollute held lists."""

from __future__ import annotations

from scripts.research_data_mcp.procurement_search import (
    distinctive_topic_tokens,
    query_topic_tokens,
    relevance_score,
    score_row,
)


def test_asia_gdelt_query_has_distinctive_anchors():
    q = "Asia daily country news shock panel GDELT"
    topic = query_topic_tokens(q)
    assert {"asia", "country", "news", "shock", "gdelt"}.issubset(topic)
    dist = distinctive_topic_tokens(q)
    assert {"asia", "shock", "gdelt"}.issubset(dist)
    assert "country" not in dist
    assert "news" not in dist


def test_keeling_correction_prose_does_not_match_asia_news():
    """Historical failure: meaning_about said 'not a country-level daily news panel'."""
    q = "Asia daily country news shock panel GDELT"
    qtok = query_topic_tokens(q)
    keeling = {
        "dataset_id": "procured_0fc91835df",
        "kind": "local_registry",
        "local_ready": True,
        "display_name": "Mauna Loa Monthly CO2 Record",
        "title": "Mauna Loa Monthly CO2 Record",
        "meaning_about": (
            "Despite the current name, this appears to be the Mauna Loa monthly atmospheric "
            "CO2 dataset, not a country-level daily news panel."
        ),
        "keywords": ["co2", "keeling-curve", "mauna-loa"],
    }
    assert relevance_score(keeling, qtok) == 0.0
    assert score_row(keeling, q) < 1.0


def test_gdelt_asia_panel_still_matches_asia_news():
    q = "Asia daily country news shock panel GDELT"
    qtok = query_topic_tokens(q)
    gdelt = {
        "dataset_id": "gdelt_asia_daily_country_panel",
        "kind": "local_registry",
        "local_ready": True,
        "display_name": "Daily news shock panel for Asian countries (GDELT)",
        "title": "Daily news shock panel for Asian countries (GDELT)",
        "meaning_about": "Country-day panel from GDELT news graph focused on Asia.",
        "keywords": ["gdelt", "asia", "news", "shock", "country"],
    }
    assert relevance_score(gdelt, qtok) >= 3.0
    assert score_row(gdelt, q) >= 5.0


def test_clean_keeling_face_still_matches_co2_query():
    q = "Keeling Curve CO2 Mauna Loa"
    qtok = query_topic_tokens(q)
    keeling = {
        "dataset_id": "procured_0fc91835df",
        "kind": "local_registry",
        "local_ready": True,
        "display_name": "Mauna Loa Monthly CO2 Record",
        "meaning_about": (
            "Monthly atmospheric CO2 concentrations measured at the Mauna Loa Observatory "
            "— the classic Keeling Curve series."
        ),
        "keywords": ["co2", "keeling-curve", "mauna-loa"],
        "aliases": ["Keeling Curve", "Mauna Loa CO2"],
    }
    assert relevance_score(keeling, qtok) >= 2.0
    assert score_row(keeling, q) >= 5.0


def test_generic_only_query_still_allows_generic_hits():
    """Queries with no distinctive anchors keep generic overlap scoring."""
    q = "country news"
    qtok = query_topic_tokens(q)
    assert distinctive_topic_tokens(q) == set()
    row = {
        "title": "Country news intensity panel",
        "description": "Daily country-level news measures",
    }
    assert relevance_score(row, qtok) >= 2.0
