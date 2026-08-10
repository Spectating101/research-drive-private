"""A coverage gap must become a collection route, not just a diagnosis.

Discover could already say "geography and time_range are missing", and
POST /library/discover/collect could already acquire from a named source.
Nothing joined them, so the researcher was told what they lacked and left to
guess which of 25 declared sources supplies it.
"""

from __future__ import annotations

import json

from scripts.research_data_mcp.gap_routes import (
    load_sources,
    parse_routes,
    unmet_dimensions,
)


def _repo(tmp_path, sources):
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "databank_source_map.json").write_text(
        json.dumps({"sources": sources}), encoding="utf-8")
    return tmp_path


def test_unmet_includes_unverifiable_not_just_failed():
    """A dimension nobody could verify is exactly what needs a route."""
    a = {"assessment_basis": {"dimension_status": {
        "unit": "supported", "geography": "not_supported",
        "time_range": "unknown", "frequency": "unverified"}}}
    assert unmet_dimensions(a) == ["frequency", "geography", "time_range"]


def test_fully_covered_needs_no_routes():
    a = {"assessment_basis": {"dimension_status": {"unit": "supported"}}}
    assert unmet_dimensions(a) == []


def test_sources_load_from_mapping_or_list(tmp_path):
    assert "crsp_moveit" in load_sources(_repo(tmp_path, {"crsp_moveit": {"access_mode": "materialized_bulk"}}))
    assert "lseg_edp" in load_sources(_repo(tmp_path, [{"id": "lseg_edp", "access_mode": "materialized_instant"}]))


def test_undeclared_sources_are_dropped():
    """Proposing a source the desk has no route to is worse than proposing none."""
    out = parse_routes(
        "geography | crsp_moveit | covers US\ngeography | bloomberg_terminal | not ours",
        ["geography"], {"crsp_moveit"})
    assert [r["source_id"] for r in out] == ["crsp_moveit"]


def test_routes_for_unrequested_dimensions_are_dropped():
    out = parse_routes("frequency | crsp_moveit | unrelated", ["geography"], {"crsp_moveit"})
    assert out == []


def test_duplicate_routes_collapse():
    out = parse_routes(
        "geography | crsp_moveit | a\ngeography | crsp_moveit | b", ["geography"], {"crsp_moveit"})
    assert len(out) == 1


def test_licensed_sources_are_offered_as_a_request_not_a_click(tmp_path):
    """'Add to collection' must not promise what an entitlement gate blocks."""
    from scripts.research_data_mcp import gap_routes

    root = _repo(tmp_path, {
        "crsp_moveit": {
            "label": "CRSP MOVEit",
            "access_mode": "materialized_bulk",
            "capabilities": ["daily_prices"],
            "geographies": ["US"],
        },
        "wrds_crsp_compustat": {
            "label": "WRDS CRSP/Compustat",
            "access_mode": "planned",
            "capabilities": ["daily_prices", "fundamentals"],
            "geographies": ["US"],
        },
    })
    out = gap_routes.routes_for_gaps(
        "US equity returns",
        {"assessment_basis": {"dimension_status": {"geography": "not_supported"}}},
        root,
    )
    by = {r["source_id"]: r for r in out["routes"]}
    assert by["crsp_moveit"]["action"] == "collect"
    assert by["crsp_moveit"]["label"] == "CRSP MOVEit"
    assert by["wrds_crsp_compustat"]["action"] == "request_access"
    assert by["wrds_crsp_compustat"]["label"] == "WRDS CRSP/Compustat"


def test_unassessed_question_is_not_reported_as_nothing_missing(tmp_path):
    """Not knowing and having everything must not share an answer.

    "patent citation networks for innovation research" returned no gaps against
    a catalog holding no patent data, because the requirement was never
    established. That reads to a researcher as "you have this".
    """
    from scripts.research_data_mcp.gap_routes import routes_for_gaps

    root = _repo(tmp_path, {"gdelt": {"access_mode": "materialized_bulk"}})
    out = routes_for_gaps(
        "patent citation networks",
        {"assessment_status": "insufficient_requirement", "verdict": None},
        root,
    )
    assert out["reason"] == "requirement_not_established"
    assert out["routes"] == []
    assert "not a statement that the data is held" in out["detail"]


def test_genuinely_complete_coverage_still_reports_nothing_missing(tmp_path):
    from scripts.research_data_mcp.gap_routes import routes_for_gaps

    root = _repo(tmp_path, {"gdelt": {"access_mode": "materialized_bulk"}})
    out = routes_for_gaps(
        "covered question",
        {"assessment_status": "assessed", "verdict": "covered",
         "assessment_basis": {"dimension_status": {"unit": "supported"}}},
        root,
    )
    assert out["reason"] == "nothing_missing"


def test_sources_block_uses_label_capabilities_and_geography():
    """Blank descriptions were the grounding failure behind junk polling routes."""
    from scripts.research_data_mcp.gap_routes import _sources_block

    block = _sources_block({
        "crsp_moveit": {
            "label": "CRSP MOVEit Cloud",
            "access_mode": "materialized_bulk",
            "capabilities": ["daily_prices", "index_pit_survivorship"],
            "geographies": ["US"],
        }
    })
    assert "CRSP MOVEit Cloud" in block
    assert "daily_prices" in block
    assert "covers: US" in block
    assert "name" not in block  # must not depend on a key the map does not have


def test_polling_short_circuits_without_model(tmp_path, monkeypatch):
    """Unserviceable questions must not wait on a model call the FE will time out."""
    from scripts.research_data_mcp import gap_routes

    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("model must not be called when nothing is plausible")

    root = _repo(tmp_path, {
        "crsp_moveit": {
            "label": "CRSP MOVEit",
            "access_mode": "materialized_bulk",
            "capabilities": ["daily_prices"],
            "geographies": ["US"],
        },
    })
    monkeypatch.setattr(
        "scripts.research_data_mcp.requirement_extraction.run_cursor_prompt", boom,
    )
    out = gap_routes.routes_for_query("US Polling data", root)
    assert out == {"routes": [], "reason": "no_route_found"}
    assert called["n"] == 0



def test_none_response_is_no_route_found(tmp_path, monkeypatch):
    """Deterministic path: when nothing is plausible, empty — model unused."""
    from scripts.research_data_mcp import gap_routes

    root = _repo(tmp_path, {
        "crsp_moveit": {
            "label": "CRSP MOVEit",
            "access_mode": "materialized_bulk",
            "capabilities": ["daily_prices"],
            "geographies": ["US"],
        }
    })
    out = gap_routes.routes_for_query("US Polling data", root)
    assert out == {"routes": [], "reason": "no_route_found"}


def test_taiwan_prices_keeps_declared_price_source(tmp_path):
    from scripts.research_data_mcp import gap_routes

    root = _repo(tmp_path, {
        "lseg_edp": {
            "label": "LSEG Workspace / EDP",
            "access_mode": "materialized_instant",
            "capabilities": ["daily_prices", "fundamentals"],
            "geographies": ["Taiwan", "US"],
            "provider": "LSEG",
        },
        "gdelt": {
            "label": "GDELT news graph",
            "access_mode": "materialized_bulk",
            "capabilities": ["entity_news_shocks"],
            "geographies": ["Asia_multi_13"],
        },
    })
    out = gap_routes.routes_for_query("Taiwan listed firm daily prices", root)
    assert out["reason"] == "ok"
    assert [r["source_id"] for r in out["routes"]] == ["lseg_edp"]


def test_route_plausible_units():
    from scripts.research_data_mcp.gap_routes import route_plausible

    price = {
        "label": "CRSP MOVEit",
        "capabilities": ["daily_prices"],
        "geographies": ["US"],
    }
    assert route_plausible("US Polling data", price) is False
    assert route_plausible("Taiwan listed firm daily prices", {
        "label": "LSEG EDP",
        "capabilities": ["daily_prices"],
        "geographies": ["Taiwan"],
    }) is True
    assert route_plausible("anything", {"label": "", "capabilities": []}) is False
