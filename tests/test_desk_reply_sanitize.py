from scripts.research_data_mcp.desk_reply_sanitize import sanitize_desk_reply


def test_sanitize_strips_paths_and_caps_length() -> None:
    raw = (
        "You have TWSE data.\n"
        "Path: data_lake/official_disclosures/taiwan_twse/\n"
        "`twse_openapi_taiwan_market_layer` is ready.\n"
        + " ".join(["word"] * 250)
    )
    out = sanitize_desk_reply(raw, first_turn=True)
    assert "data_lake/" not in out
    assert "twse_openapi" not in out
    assert len(out.split()) < 220
    assert "sample query" in out.lower()
