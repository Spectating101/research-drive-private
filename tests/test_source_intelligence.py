import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "drive/scripts/research_data_mcp/source_intelligence_store.py"
SPEC = importlib.util.spec_from_file_location("source_intelligence_store", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)

SourceIntelligenceStore = MODULE.SourceIntelligenceStore


def test_need_shortlist_ranks_evidence_backed_finance_offerings(tmp_path):
    store = SourceIntelligenceStore(tmp_path / "source_intelligence.sqlite3")
    need = store.create_need(
        {
            "title": "Point-in-time Taiwan issuer fundamentals",
            "universe": "Taiwan listed issuers",
            "market": "TW",
            "frequency": "quarterly",
            "point_in_time_required": True,
            "fields": ["revenue", "filing_date"],
        }
    )

    store.record_offering(
        need["id"],
        {
            "candidate_key": "source:twse-filings",
            "title": "TWSE filings",
            "coverage": {"market": "TW", "start": "2010-01-01", "frequency": "quarterly"},
            "fields": ["revenue", "filing_date"],
            "point_in_time": {"status": "verified", "revision_policy": "filing_date"},
            "access": {"route": "public_connector", "status": "verified"},
            "evidence": [{"kind": "probe", "status": "verified", "observed_at": "2026-07-23T00:00:00Z"}],
        },
    )
    store.record_offering(
        need["id"],
        {
            "candidate_key": "source:generic-fundamentals",
            "title": "Generic fundamentals",
            "coverage": {"market": "global", "start": "2015-01-01", "frequency": "annual"},
            "fields": ["revenue"],
            "point_in_time": {"status": "unknown"},
            "access": {"route": "credential_review", "status": "unknown"},
            "evidence": [],
        },
    )

    shortlist = store.shortlist(need["id"])

    assert shortlist["need"]["id"] == need["id"]
    assert shortlist["offerings"][0]["candidate_key"] == "source:twse-filings"
    assert shortlist["offerings"][0]["fit"]["point_in_time"]["state"] == "verified"
    assert shortlist["offerings"][1]["fit"]["access"]["state"] == "unknown"


def test_rejection_and_collection_outcome_become_source_feedback(tmp_path):
    store = SourceIntelligenceStore(tmp_path / "source_intelligence.sqlite3")
    need = store.create_need({"title": "Issuer returns"})
    offering = store.record_offering(
        need["id"],
        {
            "candidate_key": "source:issuer-prices",
            "title": "Issuer prices",
            "coverage": {},
            "fields": ["close"],
            "point_in_time": {"status": "inferred"},
            "access": {"route": "public_connector", "status": "verified"},
        },
    )

    store.reject_offering(need["id"], offering["id"], "Survivorship risk is not acceptable.")
    store.record_collection_outcome(
        offering["id"],
        {"status": "failed", "reason": "coverage gap", "observed_at": "2026-07-23T00:00:00Z"},
    )

    shortlist = store.shortlist(need["id"])
    row = shortlist["offerings"][0]
    assert row["decision"]["state"] == "rejected"
    assert row["reliability"]["recent_failure_reason"] == "coverage gap"


def test_selected_route_is_a_durable_researcher_decision(tmp_path):
    store = SourceIntelligenceStore(tmp_path / "source_intelligence.sqlite3")
    need = store.create_need({"title": "Issuer returns"})
    offering = store.record_offering(
        need["id"],
        {
            "candidate_key": "source:issuer-prices",
            "title": "Issuer prices",
            "coverage": {},
            "fields": ["close"],
            "point_in_time": {"status": "inferred"},
            "access": {"route": "public_connector", "status": "verified"},
        },
    )

    selected = store.select_route(
        need["id"],
        offering["id"],
        route={"kind": "public_connector", "connector_id": "issuer_prices"},
        rationale="Best available observed route for this universe.",
    )

    assert selected["decision"]["state"] == "selected"
    assert selected["decision"]["route"]["connector_id"] == "issuer_prices"


def test_selected_route_can_link_approval_gated_collection_job(tmp_path):
    store = SourceIntelligenceStore(tmp_path / "source_intelligence.sqlite3")
    need = store.create_need({"title": "Issuer returns"})
    offering = store.record_offering(
        need["id"],
        {
            "candidate_key": "source:issuer-prices",
            "title": "Issuer prices",
            "coverage": {},
            "fields": ["close"],
            "point_in_time": {"status": "inferred"},
            "access": {"route": "public_connector", "status": "verified"},
        },
    )
    store.select_route(
        need["id"],
        offering["id"],
        route={"kind": "public_connector", "connector_id": "issuer_prices"},
        rationale="Best available observed route for this universe.",
    )
    linked = store.link_job(need["id"], offering["id"], {"id": "job_abc", "status": "pending_approval"})
    assert linked["decision"]["collection"]["job_id"] == "job_abc"
    assert store.find_offering_id_by_job("job_abc") == offering["id"]

    store.record_collection_outcome(
        offering["id"],
        {"status": "registered", "reason": "registered as ds_issuer", "job_id": "job_abc"},
    )
    shortlist = store.shortlist(need["id"])
    row = shortlist["offerings"][0]
    assert row["reliability"]["successful_runs"] == 1
    assert row["reliability"]["state"] == "observed"
