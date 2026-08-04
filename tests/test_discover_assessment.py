"""Focused contract tests for deterministic Discover evidence assessment."""

from __future__ import annotations

from types import SimpleNamespace

from scripts.research_data_mcp import requirement_extraction
from scripts.research_data_mcp.requirement_extraction import ground_check
from scripts.research_data_mcp.discover_assessment import (
    assess_held_evidence,
    draft_requirement_from_question,
    evidence_state,
    normalize_requirement,
)


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


def test_question_drafts_only_explicit_requirement_patterns():
    """Geography resolves to ISO3 so it can be compared against observed coverage.

    Coverage declarations carry ISO3 codes profiled from stored files, so a
    drafted display name like "Taiwan" could never match one. Drafting the code
    is what makes the comparison meaningful instead of guaranteed to fail.
    """
    normalized = normalize_requirement({"question": "Daily Taiwan firm-day returns and volume, 2020-2022 earnings"})
    assert normalized["unit"] == {"value": "firm_day", "provenance": "drafted"}
    assert normalized["universe/geography"] == {"value": ["TWN"], "provenance": "drafted"}
    assert normalized["time_range"] == {"value": {"start": "2020", "end": "2022"}, "provenance": "drafted"}
    assert normalized["frequency"] == {"value": "daily", "provenance": "drafted"}
    assert normalized["fields"] == {"value": ["return", "volume"], "provenance": "drafted"}
    assert normalized["event_type"] == {"value": ["earnings"], "provenance": "drafted"}


def test_every_named_geography_is_kept_not_just_the_first():
    """A second constraint must not be silently discarded.

    The previous drafter broke on first match, so "Taiwan and Japan" constrained
    only on Taiwan. The dropped constraint was never checked, which can yield
    `covered` for evidence satisfying neither.
    """
    normalized = normalize_requirement({"question": "Taiwan and Japan governance disclosures"})
    assert normalized["universe/geography"]["value"] == ["JPN", "TWN"]
    assert "governance_disclosure" in normalized["event_type"]["value"]


def test_geographies_outside_the_old_hardcoded_table_resolve():
    """Korea and Indonesia are in this faculty's declared domains but drafted nothing before."""
    assert normalize_requirement(
        {"question": "Korean chaebol firm returns"})["universe/geography"]["value"] == ["KOR"]
    assert normalize_requirement(
        {"question": "Indonesian IDX listed firms"})["universe/geography"]["value"] == ["IDN"]


def test_region_expands_to_member_codes_present_in_the_corpus():
    """A region becomes codes, narrowed to what the corpus actually holds."""
    rows = [{
        "dataset_id": "panel",
        "coverage_metadata": {"universe/geography": {"value": ["JPN", "TWN"], "evidence": "observed"}},
    }]
    normalized = normalize_requirement({"question": "Asia country data"}, rows)
    assert normalized["universe/geography"]["value"] == ["JPN", "TWN"]


def test_units_come_from_registry_grains_not_a_fixed_table():
    rows = [{"dataset_id": "p", "grain": "issuer_quarter"}]
    normalized = normalize_requirement({"question": "issuer quarter governance data"}, rows)
    assert normalized["unit"]["value"] == "issuer_quarter"


def test_ambiguous_question_dimensions_remain_unspecified():
    normalized = normalize_requirement({"question": "Can we study firms and performance over time?"})
    assert all(item == {"value": None, "provenance": "unspecified"} for item in normalized.values())


def test_assessment_uses_existing_catalog_q_search():
    gateway = Gateway([])
    out = assess_held_evidence(gateway, question="Taiwan firm-day returns")
    assert gateway.last_kwargs["q"] == "Taiwan firm-day returns"
    assert gateway.last_kwargs["limit"] == 100
    assert out["requirement"]["unit"]["provenance"] == "drafted"


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


def test_evidence_wrapped_claim_is_not_a_false_negative():
    """An evidence-carrying declaration must be read by its asserted value.

    Reviewed/migrated labels record why a dimension is claimed
    ({"value": ..., "basis": ..., "evidence": ...}). Comparing that envelope
    instead of the value turned an exact match into `not_supported` -- a false
    clean negative, worse than `insufficient_metadata` because it asserts a
    check ran and failed when the declaration actually satisfies the need.
    """
    row = {
        "dataset_id": "wrapped",
        "materialization": {"query_ready": True, "query_verified": True},
        "coverage_metadata": {
            "frequency": {"value": "weekly", "basis": "observed_from_file",
                          "evidence": "median gap 7d between consecutive dates"},
            "time_range": {"value": {"start": "2018", "end": "2026"},
                           "basis": "observed_from_file", "evidence": "week_end spans 2018..2026"},
        },
    }
    req = requirement(frequency="weekly", time_range={"start": "2018", "end": "2026"})
    out = assess_held_evidence(Gateway([row]), question="weekly 2018-2026", requirement=req)
    assert out["verdict"] == "covered"
    assert out["assessment_basis"]["dimension_status"]["frequency"] == "supported"
    assert out["assessment_basis"]["dimension_status"]["time_range"] == "supported"


def test_wrapped_and_bare_claims_agree():
    """The envelope must not change the verdict relative to a bare value."""
    req = requirement(frequency="weekly")
    mat = {"query_ready": True, "query_verified": True}
    bare = {"dataset_id": "bare", "materialization": mat,
            "coverage_metadata": {"frequency": "weekly"}}
    wrapped = {"dataset_id": "wrapped", "materialization": mat,
               "coverage_metadata": {"frequency": {"value": "weekly", "evidence": "e"}}}
    a = assess_held_evidence(Gateway([bare]), question="weekly", requirement=req)
    b = assess_held_evidence(Gateway([wrapped]), question="weekly", requirement=req)
    assert a["verdict"] == b["verdict"] == "covered"


def test_time_range_mapping_is_not_mistaken_for_an_envelope():
    """time_range is genuinely a mapping; it has no `value` key and must survive."""
    row = {"dataset_id": "tr", "materialization": {"query_ready": True, "query_verified": True},
           "coverage_metadata": {"time_range": {"start": "2010", "end": "2030"}}}
    out = assess_held_evidence(Gateway([row]), question="range",
                               requirement=requirement(time_range={"start": "2018", "end": "2026"}))
    assert out["assessment_basis"]["dimension_status"]["time_range"] == "supported"


def test_wrapped_mismatch_still_reports_not_supported():
    """Unwrapping must not turn a genuine mismatch into a pass."""
    row = {"dataset_id": "wrong", "materialization": {"query_ready": True, "query_verified": True},
           "coverage_metadata": {"frequency": {"value": "monthly", "evidence": "e"}}}
    out = assess_held_evidence(Gateway([row]), question="weekly",
                               requirement=requirement(frequency="weekly"))
    assert out["assessment_basis"]["dimension_status"]["frequency"] == "not_supported"


# --- Grounding floor over model drafting -------------------------------------
#
# Small local models invented dimensions the question never stated: a 3B emitted
# time_range 2020-2022 for a question naming no years, a 7B emitted
# frequency "daily" for three questions naming no cadence.  Frontier backends
# (composer-2.5, grok-4.5, the copilot council) did not.  The check below runs
# regardless of backend, because "we used a capable model" is a claim about the
# model, not evidence about this particular answer.

def test_invented_time_range_is_dropped():
    """A year the question never states cannot be allowed to filter the search."""
    out = ground_check(
        "Korean chaebol firm returns",
        {"time_range": {"value": {"start": "2020", "end": "2022"}, "provenance": "drafted"}},
    )
    assert "time_range" not in out


def test_stated_time_range_survives():
    out = ground_check(
        "Korean chaebol firm returns 2020 to 2022",
        {"time_range": {"value": {"start": "2020", "end": "2022"}, "provenance": "drafted"}},
    )
    assert out["time_range"]["value"] == {"start": "2020", "end": "2022"}


def test_partially_grounded_time_range_is_dropped():
    """Both endpoints must be stated; one invented bound still narrows the search."""
    out = ground_check(
        "exchange turnover since 2020",
        {"time_range": {"value": {"start": "2020", "end": "2022"}, "provenance": "drafted"}},
    )
    assert "time_range" not in out


def test_invented_frequency_is_dropped():
    """The exact fabrication a 7B model produced three times out of five."""
    out = ground_check(
        "Hong Kong and Singapore exchange turnover",
        {"frequency": {"value": "daily", "provenance": "drafted"}},
    )
    assert "frequency" not in out


def test_stated_frequency_survives():
    out = ground_check(
        "Hong Kong daily exchange turnover",
        {"frequency": {"value": "daily", "provenance": "drafted"}},
    )
    assert out["frequency"]["value"] == "daily"


def test_frequency_grounded_by_word_root_not_exact_spelling():
    """"by issuer quarter" justifies quarterly; both frontier models emitted it."""
    out = ground_check(
        "stablecoin de-peg events by issuer quarter",
        {"frequency": {"value": "quarterly", "provenance": "drafted"}},
    )
    assert out["frequency"]["value"] == "quarterly"


def test_grounding_leaves_unchecked_dimensions_alone():
    """Only the two observed failure modes are policed; the rest pass through."""
    draft = {
        "universe/geography": {"value": ["HKG", "SGP"], "provenance": "drafted"},
        "event_type": {"value": ["wash_trading"], "provenance": "drafted"},
    }
    assert ground_check("Hong Kong and Singapore exchange turnover", draft) == draft


def test_drafting_is_off_unless_explicitly_enabled():
    """Assessment must not acquire a network dependency by default."""
    assert not requirement_extraction.enabled()


def test_backend_failure_degrades_to_corpus_vocabulary(monkeypatch):
    """A slow or unreachable provider costs vocabulary reach, not the assessment."""
    monkeypatch.setattr(requirement_extraction, "enabled", lambda: True)

    def _explode(*_args, **_kwargs):
        raise requirement_extraction.ExtractionUnavailable("provider down")

    monkeypatch.setattr(requirement_extraction, "extract_requirement", _explode)
    draft = draft_requirement_from_question("Taiwan and Japan firm day returns 2020 to 2022")
    assert draft["universe/geography"]["value"] == ["JPN", "TWN"]
    assert draft["time_range"]["value"] == {"start": "2020", "end": "2022"}


def test_corpus_tokens_win_over_model_prose(monkeypatch):
    """The corpus emits registry-matchable tokens; the model emits description."""
    monkeypatch.setattr(requirement_extraction, "enabled", lambda: True)
    monkeypatch.setattr(
        requirement_extraction, "extract_requirement",
        lambda *_a, **_k: {
            "unit": {"value": "exchange-level turnover", "provenance": "drafted"},
            "event_type": {"value": ["market_activity"], "provenance": "drafted"},
        },
    )
    draft = draft_requirement_from_question("Taiwan firm day returns")
    assert draft["unit"]["value"] == "firm_day"          # corpus token, not prose
    assert draft["event_type"]["value"] == ["market_activity"]  # model filled the gap
