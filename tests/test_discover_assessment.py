"""Focused contract tests for deterministic Discover evidence assessment."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

from scripts.research_data_mcp.discover_assessment import assess_held_evidence, evidence_state, normalize_requirement


class Gateway:
    def __init__(self, rows):
        self.rows = rows

    def list_datasets(self, **kwargs):
        self.last_kwargs = kwargs
        return {"datasets": self.rows}


def requirement(**dimensions):
    return {key: {"value": value, "provenance": "explicit"} for key, value in dimensions.items()}


def supported_row(**coverage):
    return {
        "dataset_id": "held_panel",
        "name": "Held panel",
        "analysis_readiness": "instant",
        "materialization": {"query_ready": True, "query_verified": True},
        "coverage_metadata": coverage,
    }


def test_fully_supported_requirement_is_covered():
    req = requirement(unit="firm_day", geography="Taiwan", fields=["ret", "volume"])
    row = supported_row(unit="firm_day", geography="Taiwan", fields=["ret", "volume", "market_cap"])
    out = assess_held_evidence(Gateway([row]), question="Taiwan firm returns", requirement=req)
    assert out["verdict"] == "covered"
    assert out["gap"] is None
    assert out["held_evidence"][0]["dataset_id"] == "held_panel"


def test_question_is_drafted_by_the_model_without_a_static_vocabulary(monkeypatch):
    captured = {}

    def model(prompt):
        captured["prompt"] = prompt
        return '{"unit":"firm_day","universe/geography":"Taiwan","time_range":{"start":"2020","end":"2022"},"frequency":"daily","fields":["return","volume"],"event_type":"earnings"}'

    monkeypatch.setattr("scripts.research_data_mcp.discover_assessment._run_requirement_model", model)
    normalized = normalize_requirement({"question": "Daily Taiwan firm-day returns and volume, 2020-2022 earnings"})
    assert normalized["unit"] == {"value": "firm_day", "provenance": "drafted"}
    assert normalized["universe/geography"] == {"value": "Taiwan", "provenance": "drafted"}
    assert normalized["time_range"] == {"value": {"start": "2020", "end": "2022"}, "provenance": "drafted"}
    assert normalized["frequency"] == {"value": "daily", "provenance": "drafted"}
    assert normalized["fields"] == {"value": ["return", "volume"], "provenance": "drafted"}
    assert normalized["event_type"] == {"value": "earnings", "provenance": "drafted"}
    assert "Do not infer proxies" in captured["prompt"]


def test_unavailable_model_leaves_question_dimensions_unspecified(monkeypatch):
    def unavailable(prompt):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("scripts.research_data_mcp.discover_assessment._run_requirement_model", unavailable)
    normalized = normalize_requirement({"question": "Can we study firms and performance over time?"})
    assert all(item == {"value": None, "provenance": "unspecified"} for item in normalized.values())


def test_assessment_uses_existing_catalog_q_search_and_model_draft(monkeypatch):
    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_assessment._run_requirement_model",
        lambda prompt: '{"unit":"firm_day"}',
    )
    gateway = Gateway([])
    out = assess_held_evidence(gateway, question="Taiwan firm-day returns")
    assert gateway.last_kwargs["q"] == "Taiwan firm-day returns"
    assert gateway.last_kwargs["limit"] == 100
    assert out["requirement"]["unit"]["provenance"] == "drafted"


def test_explicit_requirement_does_not_call_the_model(monkeypatch):
    def should_not_run(prompt):
        raise AssertionError("explicit requirement must remain authoritative")

    monkeypatch.setattr("scripts.research_data_mcp.discover_assessment._run_requirement_model", should_not_run)
    normalized = normalize_requirement(requirement(unit="firm_day", geography="Taiwan", time_range={"start": "2020", "end": "2022"}, frequency="daily", fields=["return"], event_type="earnings"))
    assert normalized["unit"]["value"] == "firm_day"


def test_requirement_model_timeout_is_sanitised(monkeypatch):
    from scripts.research_data_mcp import discover_assessment

    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(discover_assessment.shutil, "which", lambda name: "/safe/cursor-agent")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(["cursor-agent", "-p", "sensitive prompt"], 12)

    monkeypatch.setattr(discover_assessment.subprocess, "run", timeout)
    try:
        discover_assessment._run_requirement_model("sensitive prompt")
    except RuntimeError as exc:
        assert str(exc) == "model timed out"
    else:
        raise AssertionError("expected model timeout")


def test_partial_requirement_reports_one_precise_gap():
    req = requirement(unit="firm_day", geography="Taiwan", event_type="earnings")
    row = supported_row(unit="firm_day", geography="Taiwan")
    out = assess_held_evidence(Gateway([row]), question="Taiwan earnings", requirement=req)
    assert out["verdict"] is None
    assert out["assessment_status"] == "insufficient_metadata"
    assert out["gap"]["dimension"] == "event_type"
    assert out["gap"]["status"] == "unknown"


def test_no_material_held_support_is_not_covered():
    req = requirement(event_type="earthquake", geography="Japan")
    row = supported_row(event_type="earnings", geography="Taiwan")
    out = assess_held_evidence(Gateway([row]), question="Japan earthquakes", requirement=req)
    assert out["verdict"] == "not_covered"
    assert out["assessment_status"] == "assessed"
    assert out["held_evidence"] == []
    assert out["gap"]["dimension"] == "universe/geography"


def test_conflicting_legacy_readiness_is_preserved():
    row = supported_row(unit="firm_day")
    row["evidence_coverage"] = {"unit": "security_day"}
    row["field_coverage"] = "query-ready"
    out = assess_held_evidence(Gateway([row]), question="firm panel", requirement=requirement(unit="firm_day"))
    assert out["verdict"] is None
    assert out["assessment_status"] == "insufficient_metadata"
    state = out["assessment_basis"]["dimension_status"]
    assert state["unit"] == "conflicting"
    record = out["held_evidence"][0]
    assert record["evidence_state"]["coverage"]["status"] == "conflicting"
    assert record["evidence_state"]["legacy"]["analysis_readiness"] == "instant"
    assert record["evidence_state"]["field_coverage"]["value"] == "query-ready"


def test_missing_coverage_metadata_never_becomes_verified():
    row = {"dataset_id": "legacy", "analysis_readiness": "instant", "materialization": {"query_ready": True}}
    out = assess_held_evidence(Gateway([row]), question="firm panel", requirement=requirement(unit="firm_day"))
    # No candidate declared coverage metadata at all for the requested dimension —
    # this is an absence of data, not a checked-and-failed result, so it must not
    # be reported as `not_covered`.
    assert out["verdict"] is None
    assert out["assessment_status"] == "insufficient_metadata"
    assert out["assessment_basis"]["dimension_status"]["unit"] == "unknown"
    assert out["assessment_basis"]["uncovered_candidate_ids"] == ["legacy"]


def test_not_covered_requires_a_declared_mismatch_not_just_absence():
    """A declared mismatch is `not_covered`; absent metadata has no verdict."""
    req = requirement(event_type="earthquake", geography="Japan")
    declared_mismatch_row = supported_row(event_type="earnings", geography="Taiwan")
    out = assess_held_evidence(Gateway([declared_mismatch_row]), question="Japan earthquakes", requirement=req)
    assert out["verdict"] == "not_covered"
    assert out["assessment_basis"]["uncovered_candidate_ids"] == []

    undeclared_row = {"dataset_id": "no_metadata", "materialization": {"query_ready": True}}
    out2 = assess_held_evidence(Gateway([undeclared_row]), question="Japan earthquakes", requirement=req)
    assert out2["verdict"] is None
    assert out2["assessment_status"] == "insufficient_metadata"
    assert out2["assessment_basis"]["uncovered_candidate_ids"] == ["no_metadata"]


def test_insufficient_metadata_with_zero_candidates_considered():
    out = assess_held_evidence(Gateway([]), question="Japan earthquakes", requirement=requirement(geography="Japan"))
    assert out["verdict"] is None
    assert out["assessment_status"] == "insufficient_metadata"
    assert out["assessment_basis"]["catalog_candidates_considered"] == 0
    assert out["assessment_basis"]["uncovered_candidate_ids"] == []


def test_query_ready_declaration_is_not_observed_query_proof():
    row = {
        "dataset_id": "declared_only",
        "materialization": {"query_ready": True},
        "coverage_metadata": {"unit": "firm_day"},
    }
    assert evidence_state(row)["materialization"]["status"] == "query_ready_declared"
    out = assess_held_evidence(Gateway([row]), question="firm panel", requirement=requirement(unit="firm_day"))
    assert out["verdict"] is None
    assert out["assessment_status"] == "insufficient_metadata"
    assert out["assessment_basis"]["dimension_status"]["unit"] == "unverified"
    assert out["held_evidence"][0]["dataset_id"] == "declared_only"
    assert "usability is unverified" in out["held_evidence"][0]["contribution"]


def test_coverage_mismatch_is_not_mislabeled_as_unverified():
    row = {
        "dataset_id": "wrong_grain",
        "materialization": {"query_ready": True},
        "coverage_metadata": {"unit": "country_day"},
    }
    out = assess_held_evidence(Gateway([row]), question="firm panel", requirement=requirement(unit="firm_day"))
    assert out["assessment_basis"]["dimension_status"]["unit"] == "not_supported"
    assert out["held_evidence"] == []


def test_distributed_support_is_neutral_until_compatibility_is_proven():
    req = requirement(unit="firm_day", event_type="earnings")
    rows = [supported_row(unit="firm_day"), supported_row(event_type="earnings")]
    out = assess_held_evidence(Gateway(rows), question="firm earnings", requirement=req)
    assert out["verdict"] is None
    assert out["assessment_status"] == "insufficient_metadata"
    assert out["gap"]["dimension"] == "assembly"
    assert out["assessment_basis"]["assembly_status"] == "unknown"


def test_promoter_query_smoke_is_observed_query_proof():
    row = {
        "dataset_id": "promoted_panel",
        "analysis_readiness": "query_ready",
        "source_access_mode": "materialized_query_ready",
        "query_smoke": {"ok": True, "rows": 3},
        "coverage_metadata": {"unit": "firm_day"},
    }
    state = evidence_state(row)
    assert state["materialization"]["status"] == "verified"

    out = assess_held_evidence(
        Gateway([row]),
        question="firm panel",
        requirement=requirement(unit="firm_day"),
    )
    assert out["assessment_status"] == "assessed"
    assert out["verdict"] == "covered"


def test_time_ranges_compare_real_boundaries_not_lexical_strings():
    row = supported_row(
        time_range={"start": "2020-01-01", "end": "2022-12-31"}
    )
    out = assess_held_evidence(
        Gateway([row]),
        question="firm panel 2020-2022",
        requirement=requirement(
            time_range={"start": "2020", "end": "2022"}
        ),
    )
    assert out["verdict"] == "covered"


def test_equivalent_field_order_does_not_create_a_conflict():
    row = supported_row(fields=["return", "volume"])
    row["evidence_coverage"] = {"fields": ["volume", "return"]}
    out = assess_held_evidence(
        Gateway([row]),
        question="returns and volume",
        requirement=requirement(fields=["return", "volume"]),
    )
    assert out["verdict"] == "covered"
    assert (
        out["held_evidence"][0]["evidence_state"]["coverage"]["status"]
        == "documented"
    )


def test_http_route_contract(monkeypatch):
    from scripts.research_data_mcp.http_router import ROUTE_CATALOG, handle_post

    captured = {}
    stack = SimpleNamespace(gateway=SimpleNamespace(repo_root="/tmp", discover_assessment=lambda question, requirement, limit: captured.update(question=question, requirement=requirement, limit=limit) or {"verdict": "not_covered"}))
    monkeypatch.setattr("scripts.research_data_mcp.http_router._activity", lambda *args, **kwargs: None, raising=False)
    out = handle_post("/library/discover/assessment", {"question": "Need a panel", "requirement": requirement(unit="firm_day")}, stack)
    assert out == {"status": 200, "body": {"verdict": "not_covered"}}
    assert captured["question"] == "Need a panel"
    assert captured["requirement"]["unit"]["value"] == "firm_day"
    assert any(row["path"] == "/library/discover/assessment" and row["method"] == "POST" for row in ROUTE_CATALOG)
