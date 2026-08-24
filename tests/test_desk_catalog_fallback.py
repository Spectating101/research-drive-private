from scripts.research_data_mcp.desk_catalog_fallback import try_inventory_fallback

SAMPLE_BRIEF = """Desk vault brief (already loaded for this chat — trust this for inventory questions).
On disk: 42 registered datasets, 8 collection partitions with local bytes.
Ready now:
- TWSE daily trading panel (query-ready)
- MOPS corporate governance extracts
- Stablecoin trust engagement derived panel
Not local yet:
- Refinitiv survivorship full history
"""


def test_inventory_fallback_matches_twse() -> None:
    reply = try_inventory_fallback("What TWSE data do we already have in the vault?", SAMPLE_BRIEF)
    assert reply
    assert "TWSE" in reply
    assert "data_lake/" not in reply


def test_inventory_fallback_no_match_returns_none() -> None:
    assert try_inventory_fallback("Rewrite this email politely.", SAMPLE_BRIEF) is None


def test_inventory_fallback_without_keywords_lists_ready() -> None:
    reply = try_inventory_fallback("What do we have in the vault already?", SAMPLE_BRIEF)
    assert reply
    assert "TWSE" in reply or "MOPS" in reply
