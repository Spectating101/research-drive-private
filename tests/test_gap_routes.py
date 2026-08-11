"""Contracts for model-mediated Discover collection options."""
from __future__ import annotations

import json
from types import SimpleNamespace

from scripts.research_data_mcp.gap_routes import GapRouteModelUnavailable, routes_for_gaps


def _assessment(status="assessed", dimension_status=None):
    return {
        "assessment_status": status,
        "assessment_basis": {"dimension_status": dimension_status or {"unit": "not_supported"}},
        "verdict": "not_covered",
    }


def _write_sources(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "databank_source_map.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "public_source",
                        "label": "Public filings archive",
                        "provider": "Example archive",
                        "access_mode": "procurement_catalog",
                        "notes": "Declared collection route.",
                    },
                    {
                        "id": "licensed_source",
                        "label": "Licensed archive",
                        "provider": "Example vendor",
                        "access_mode": "planned",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


def test_routes_are_model_selected_but_limited_to_declared_source_ids(tmp_path):
    _write_sources(tmp_path)

    out = routes_for_gaps(
        "Need an issuer-day panel",
        _assessment(),
        tmp_path,
        run_model=lambda prompt, model, timeout: (
            "unit | public_source | Declared archive offers the needed observation grain\n"
            "unit | invented_source | Must be rejected"
        ),
    )

    assert out["reason"] == "ok"
    assert out["routes"] == [
        {
            "dimension": "unit",
            "source_id": "public_source",
            "reason": "Declared archive offers the needed observation grain",
            "label": "Public filings archive",
            "provider": "Example archive",
            "access_mode": "procurement_catalog",
            "actionable": True,
            "action": "collect",
        }
    ]


def test_model_cannot_add_unknown_dimension_or_turn_a_planned_source_into_collect(tmp_path):
    _write_sources(tmp_path)
    out = routes_for_gaps(
        "Need issuer data",
        _assessment(),
        tmp_path,
        run_model=lambda prompt, model, timeout: "geography | public_source | invalid dimension\nunit | licensed_source | access requires review",
    )
    assert len(out["routes"]) == 1
    assert out["routes"][0]["source_id"] == "licensed_source"
    assert out["routes"][0]["action"] == "request_access"
    assert out["routes"][0]["actionable"] is False


def test_unavailable_model_returns_no_route_instead_of_a_heuristic(tmp_path):
    _write_sources(tmp_path)

    def unavailable(prompt, model, timeout):
        raise GapRouteModelUnavailable("provider unavailable")

    out = routes_for_gaps("Need issuer data", _assessment(), tmp_path, run_model=unavailable)
    assert out["routes"] == []
    assert out["reason"] == "backend_unavailable: provider unavailable"


def test_route_model_budget_stays_inside_the_frontend_request_budget(tmp_path):
    _write_sources(tmp_path)
    observed = {}

    def model(prompt, model_name, timeout):
        observed["timeout"] = timeout
        return "unit | public_source | Declared source"

    routes_for_gaps("Need issuer data", _assessment(), tmp_path, run_model=model)
    assert observed["timeout"] == 12.0


def test_unassessed_requirement_never_calls_the_model(tmp_path):
    _write_sources(tmp_path)

    def should_not_run(prompt, model, timeout):
        raise AssertionError("unassessed requirements must not be routed")

    out = routes_for_gaps("Need issuer data", _assessment("insufficient_requirement"), tmp_path, run_model=should_not_run)
    assert out["reason"] == "requirement_not_established"
    assert out["routes"] == []


def test_http_route_requires_the_assessment_returned_to_the_researcher():
    from scripts.research_data_mcp.http_router import ROUTE_CATALOG, handle_post

    stack = SimpleNamespace(gateway=SimpleNamespace(repo_root="/tmp"))
    out = handle_post("/library/discover/routes", {"question": "Need a panel"}, stack)
    assert out["status"] == 400
    assert "assessment is required" in out["body"]["message"]
    assert any(row["path"] == "/library/discover/routes" and row["method"] == "POST" for row in ROUTE_CATALOG)
