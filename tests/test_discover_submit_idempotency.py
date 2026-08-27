from __future__ import annotations

import pytest

from scripts.research_data_mcp.discover_intent_store import DiscoverIntentStore
from scripts.research_data_mcp.gateway import ResearchDataGateway


class _IdempotentFakeJobs:
    """Small test double for the already-tested orchestrator idempotency contract."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.jobs: dict[str, dict] = {}

    def submit(self, title, plan, request=None, *, auto_approve=False):
        request = dict(request or {})
        key = str(request.get("idempotency_key") or "")
        assert key
        self.calls.append({"title": title, "plan": dict(plan), "request": request, "auto_approve": auto_approve})
        job = self.jobs.get(key)
        if job is None:
            job = {
                "id": key,
                "title": title,
                "status": "pending_approval",
                "plan": dict(plan),
                "request": request,
                "result": {},
            }
            self.jobs[key] = job
        return {"job": dict(job), "plan": dict(plan)}

    def get(self, job_id):
        return dict(self.jobs[str(job_id)])


def _ready_crafted_intent(store: DiscoverIntentStore) -> dict:
    intent = store.create(research_need="Need a concrete public evidence source", title="Evidence source")
    proposed = store.set_proposal(
        intent["id"],
        {
            "id": "proposal-1",
            "summary": "Probe a concrete source before collection.",
            "routes": [
                {
                    "id": "route-1",
                    "title": "Probe example source",
                    "summary": "Classify the selected public source.",
                    "url": "https://example.com/data",
                    "collect_plan": {
                        "title": "Probe example source",
                        "job_type": "source_probe",
                        "url": "https://example.com/data",
                        "launchable": True,
                        "requires_approval": True,
                    },
                }
            ],
            "recommended_route_id": "route-1",
        },
    )
    proposal = proposed["state"]["proposal"]
    return store.review_proposal(
        intent["id"],
        decision="accept",
        proposal_id=proposal["id"],
        proposal_hash=proposal["proposal_hash"],
    )


def test_same_job_link_is_idempotent_but_different_job_conflicts(tmp_path):
    store = DiscoverIntentStore(tmp_path / "discover-intents.sqlite3")
    intent = store.create(research_need="Need evidence")

    first = store.link_job(intent["id"], {"id": "discover:one", "status": "pending_approval"})
    replay = store.link_job(intent["id"], {"id": "discover:one", "status": "pending_approval"})

    assert replay["state"]["collection"]["job_id"] == "discover:one"
    assert replay["state"]["collection"] == first["state"]["collection"]
    assert [event["kind"] for event in store.events(intent["id"])].count("job_linked") == 1

    with pytest.raises(ValueError, match="different collection job"):
        store.link_job(intent["id"], {"id": "discover:two", "status": "pending_approval"})


def test_discover_submit_replay_uses_one_intent_scoped_job_identity(tmp_path):
    store = DiscoverIntentStore(tmp_path / "discover-intents.sqlite3")
    ready = _ready_crafted_intent(store)
    jobs = _IdempotentFakeJobs()

    gateway = object.__new__(ResearchDataGateway)
    gateway._discover_intents_store = store
    gateway.jobs = jobs

    first = gateway.discover_intent_submit_collection(ready["id"])
    replay = gateway.discover_intent_submit_collection(ready["id"])

    expected_key = f"discover:{ready['id']}"
    assert first["job"]["id"] == expected_key
    assert replay["job"]["id"] == expected_key
    assert {call["request"]["idempotency_key"] for call in jobs.calls} == {expected_key}
    assert len(jobs.jobs) == 1
    assert replay["intent"]["state"]["collection"]["job_id"] == expected_key
    assert replay["intent"]["state"]["status"] == "pending_approval"
    assert [event["kind"] for event in store.events(ready["id"])].count("job_linked") == 1
