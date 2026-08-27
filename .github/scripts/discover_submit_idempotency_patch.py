from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match in {path}, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_count(path: str, old: str, new: str, expected: int, label: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{label}: expected {expected} matches in {path}, found {count}")
    p.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    "drive/scripts/research_data_mcp/discover_intent_store.py",
    '''    def link_job(self, intent_id: str, job: dict[str, Any]) -> dict[str, Any]:\n        current = self.get(intent_id)\n        state = _clone(current["state"])\n        collection = dict(state.get("collection") or {})\n        if collection.get("job_id"):\n            raise ValueError("Discover intent already has a collection job")\n        collection.update({"job_id": str(job.get("id") or ""), "status": str(job.get("status") or "pending_approval")})\n        state["collection"] = collection\n        state["status"] = "pending_approval"\n        out = self._save(intent_id, state)\n        self._event(intent_id, "job_linked", {"job_id": collection["job_id"]})\n        return out\n''',
    '''    def link_job(self, intent_id: str, job: dict[str, Any]) -> dict[str, Any]:\n        current = self.get(intent_id)\n        state = _clone(current["state"])\n        collection = dict(state.get("collection") or {})\n        job_id = str(job.get("id") or "").strip()\n        if not job_id:\n            raise ValueError("collection job id is required")\n        existing_job_id = str(collection.get("job_id") or "").strip()\n        if existing_job_id:\n            # Job creation is idempotent at the cluster boundary. Replaying the\n            # same consequence must therefore also be idempotent at the intent\n            # boundary; only a genuinely different job is a conflict.\n            if existing_job_id == job_id:\n                return current\n            raise ValueError("Discover intent already has a different collection job")\n        collection.update({\n            "job_id": job_id,\n            "status": str(job.get("status") or "pending_approval"),\n        })\n        state["collection"] = collection\n        state["status"] = "pending_approval"\n        out = self._save(intent_id, state)\n        self._event(intent_id, "job_linked", {"job_id": collection["job_id"]})\n        return out\n''',
    "make intent job linking idempotent",
)

# YzuOrchestrator already provides atomic deterministic-id submission with
# SQLite uniqueness and same-request verification. Bind one job identity to one
# Discover intent in both crafted and catalog acquisition paths.
replace_count(
    "drive/scripts/research_data_mcp/gateway.py",
    '''                    "source": "discover_intent",\n                    "discover_intent_id": intent_id,\n                    "research_need": intent.get("research_need") or "",\n''',
    '''                    "source": "discover_intent",\n                    "discover_intent_id": intent_id,\n                    "idempotency_key": f"discover:{intent_id}",\n                    "research_need": intent.get("research_need") or "",\n''',
    1,
    "crafted Discover submit idempotency key",
)
replace_count(
    "drive/scripts/research_data_mcp/gateway.py",
    '''        submitted = self.jobs.submit(plan.get("title") or intent.get("title") or "Discover collection", plan, {"source": "discover_intent", "discover_intent_id": intent_id, "research_need": intent.get("research_need") or "", "route_id": selected_id, "connector_id": connector_id}, auto_approve=False)\n''',
    '''        submitted = self.jobs.submit(plan.get("title") or intent.get("title") or "Discover collection", plan, {"source": "discover_intent", "discover_intent_id": intent_id, "idempotency_key": f"discover:{intent_id}", "research_need": intent.get("research_need") or "", "route_id": selected_id, "connector_id": connector_id}, auto_approve=False)\n''',
    1,
    "catalog Discover submit idempotency key",
)

Path("tests/test_discover_submit_idempotency.py").write_text(r'''from __future__ import annotations

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
''', encoding="utf-8")

print("Applied Discover server-side idempotency and regression tests")
