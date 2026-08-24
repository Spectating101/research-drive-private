from __future__ import annotations

import pytest

from scripts.research_data_mcp.discover_intent_store import DiscoverIntentStore


def _proposal(*, proposal_id: str = "routes-v1") -> dict:
    return {
        "id": proposal_id,
        "summary": "Use the public historical table for the primary collection.",
        "recommended_route_id": "bigquery",
        "routes": [
            {
                "id": "bigquery",
                "title": "Public historical table",
                "connector_id": "src_test_bigquery",
                "candidate_key": "candidate:test",
                "coverage": "2017 onward",
                "grain": "daily",
                "access": "query billed",
                "destination": "collection/acquired/chain",
            },
            {"id": "api", "title": "Targeted API", "limitation": "historical depth unverified"},
        ],
    }


def test_review_requires_exact_proposal_revision_and_persists_routes(tmp_path):
    store = DiscoverIntentStore(tmp_path / "discover.sqlite3")
    intent = store.create(research_need="Historical stablecoin activity before 2021")
    proposed = store.set_proposal(intent["id"], _proposal())
    proposal = proposed["state"]["proposal"]

    with pytest.raises(ValueError, match="changed"):
        store.review_proposal(intent["id"], decision="accept", proposal_id=proposal["id"], proposal_hash="stale")

    accepted = store.review_proposal(
        intent["id"],
        decision="accept",
        proposal_id=proposal["id"],
        proposal_hash=proposal["proposal_hash"],
    )
    assert accepted["state"]["status"] == "ready_for_review"
    assert accepted["state"]["selected_route_id"] == "bigquery"
    assert accepted["state"]["proposal"] is None


def test_route_cannot_change_or_link_twice_after_collection_submission(tmp_path):
    store = DiscoverIntentStore(tmp_path / "discover.sqlite3")
    intent = store.create(research_need="Need a source")
    proposed = store.set_proposal(intent["id"], _proposal())
    proposal = proposed["state"]["proposal"]
    accepted = store.review_proposal(
        intent["id"], decision="accept", proposal_id=proposal["id"], proposal_hash=proposal["proposal_hash"]
    )
    linked = store.link_job(accepted["id"], {"id": "job-1", "status": "pending_approval"})
    assert linked["state"]["collection"]["job_id"] == "job-1"
    with pytest.raises(ValueError, match="cannot change"):
        store.select_route(intent["id"], "api")
    with pytest.raises(ValueError, match="already has"):
        store.link_job(intent["id"], {"id": "job-2"})


def test_proposal_rejects_unbounded_or_duplicated_routes(tmp_path):
    store = DiscoverIntentStore(tmp_path / "discover.sqlite3")
    intent = store.create(research_need="Need a source")
    bad = _proposal()
    bad["routes"] = [bad["routes"][0]] * 9
    with pytest.raises(ValueError, match="between 1 and 8"):
        store.set_proposal(intent["id"], bad)
