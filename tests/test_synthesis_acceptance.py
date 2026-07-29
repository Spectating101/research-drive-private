"""Deterministic grading for adversarial Synthesis first turns."""

from __future__ import annotations

import json
from pathlib import Path


def _case():
    return {
        "id": "idn",
        "title": "IDN construct",
        "expected_asset_groups": [
            ["jkse pit", "point-in-time jkse"],
            ["microstructure", "idn fry"],
        ],
        "required_risk_groups": [
            ["survivorship"],
            ["entity mapping"],
            ["retail ident", "retail-facing"],
        ],
    }


def test_accepts_a_grounded_provisional_first_turn():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_response

    result = {
        "action": "composer",
        "reply": (
            "Provisionally, this is a latent retail-facing coordination proxy, not an "
            "identity measure. JKSE PIT supplies the historical universe and IDN FRY "
            "microstructure supplies candidate synchronized-flow components. The design "
            "must preserve survivorship limitations and entity mapping uncertainty, and "
            "must not treat retail identities as verified. Which coordination horizon "
            "should be primary: same-day, two-day, or one-week?"
        ),
        "artifacts": {"action": "composer"},
    }
    evaluated = evaluate_response(_case(), result)

    assert evaluated["outcome"] == "passed"
    assert all(check["ok"] for check in evaluated["checks"])


def test_provider_failure_is_not_scored_as_reasoning_failure():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_response

    result = {
        "action": "composer_error",
        "reply": "The Synthesis agent did not return a usable reasoning turn.",
        "artifacts": {"action": "composer_error", "error": "internal error"},
    }
    evaluated = evaluate_response(_case(), result)

    assert evaluated["outcome"] == "provider_failed"
    assert evaluated["provider_error"] == "internal error"
    assert evaluated["provider_chain"]["primary"] == "cursor_composer"
    assert evaluated["provider_chain"]["fallback"] == ""
    assert evaluated["checks"] == []


def test_provider_failure_reports_the_fallback_chain():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_response

    result = {
        "action": "composer_error",
        "reply": "The Synthesis agent did not return a usable reasoning turn.",
        "artifacts": {
            "action": "composer_error",
            "brain": "cursor_composer",
            "error": "internal error",
            "fallback": "gemini_failed",
            "fallback_error_category": "authentication",
        },
    }
    evaluated = evaluate_response(_case(), result)

    assert evaluated["outcome"] == "provider_failed"
    assert evaluated["provider_chain"] == {
        "primary": "cursor_composer",
        "primary_error": "internal error",
        "fallback": "gemini_failed",
        "fallback_error_category": "authentication",
    }


def test_rejects_inventory_dump_and_missing_clarification():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_response

    result = {
        "action": "composer",
        "reply": (
            "Available datasets include JKSE PIT and IDN FRY microstructure. "
            "They are ready to use. Open Library for more details. "
            "This answer has no construct interpretation, survivorship discussion, "
            "entity mapping limitation, or clarification."
        ),
        "artifacts": {"action": "composer"},
    }
    evaluated = evaluate_response(_case(), result)

    assert evaluated["outcome"] == "contract_failed"
    checks = {row["name"]: row for row in evaluated["checks"]}
    assert checks["one_clarification_question"]["ok"] is False
    assert checks["explicit_validity_risks"]["ok"] is False


def test_rejects_false_execution_claim():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_response

    result = {
        "action": "composer",
        "reply": (
            "Provisionally, JKSE PIT and IDN FRY microstructure could support the proxy. "
            "Survivorship, entity mapping, and unverified retail identities remain risks. "
            "We have materialized the final dataset and it is now query-ready. "
            "Which horizon should be primary?"
        ),
        "artifacts": {"action": "composer"},
    }
    evaluated = evaluate_response(_case(), result)
    checks = {row["name"]: row for row in evaluated["checks"]}

    assert evaluated["outcome"] == "contract_failed"
    assert checks["no_execution_claim"]["ok"] is False


def test_case_file_is_complete_and_non_mutating():
    from scripts.research_data_mcp.synthesis_acceptance import load_cases

    cases = load_cases()
    assert len(cases) >= 5
    assert len({row["id"] for row in cases}) == len(cases)
    for row in cases:
        request = row["request"].lower()
        assert row["retrieval_query"]
        assert row["expected_asset_groups"]
        assert row["required_risk_groups"]
        assert any(term in request for term in ("do not", "don't"))
        assert not any(
            phrase in request
            for phrase in ("approve and run", "auto-approve", "submit execution")
        )


def test_battery_classifies_transport_failure(monkeypatch, tmp_path: Path):
    from scripts.research_data_mcp import synthesis_acceptance

    case_path = tmp_path / "cases.json"
    case_path.write_text(
        json.dumps({"cases": [{**_case(), "request": "Do not execute."}]}),
        encoding="utf-8",
    )

    def fail_session(self):
        raise OSError("offline")

    monkeypatch.setattr(
        synthesis_acceptance.SynthesisAcceptanceClient,
        "open_session",
        fail_session,
    )
    report = synthesis_acceptance.run_battery(
        "http://127.0.0.1:9",
        cases_path=case_path,
    )

    assert report["outcome"] == "transport_failed"
    assert report["cases"] == []


def test_preflight_combines_search_details_and_synthesis_profiles(monkeypatch):
    from scripts.research_data_mcp.synthesis_acceptance import (
        SynthesisAcceptanceClient,
    )

    client = SynthesisAcceptanceClient("http://example.test")

    def fake_get(path, query):
        if path == "/library/search":
            return {
                "rows": [
                    {
                        "dataset_id": "mops_governance_panel",
                        "title": "Taiwan MOPS governance misconduct panel",
                    }
                ]
            }
        if path == "/datasets/mops_governance_panel":
            return {
                "dataset_id": "mops_governance_panel",
                "description": "Official governance filings and disclosures.",
            }
        if path == "/library/synthesis/profiles":
            return {
                "profiles": [
                    {
                        "title": "Governance intervention pattern",
                        "description": "Point-in-time filing-date construction.",
                    }
                ]
            }
        raise AssertionError(path)

    monkeypatch.setattr(client, "_get", fake_get)
    preflight = client.preflight_case(
        {
            "retrieval_query": "Taiwan MOPS governance",
            "expected_asset_groups": [
                ["mops"],
                ["filing", "disclosure"],
                ["point-in-time"],
            ],
        }
    )
    assert preflight["ok"] is True
    assert preflight["detail_count"] == 1
    assert preflight["profile_count"] == 1
