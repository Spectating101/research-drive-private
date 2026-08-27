from __future__ import annotations

import threading

import pytest

from scripts.research_data_mcp.discover_intent_store import DiscoverIntentStore
from scripts.research_data_mcp.gateway import ResearchDataGateway


def _route(route_id: str, url: str) -> dict:
    return {
        "id": route_id,
        "title": f"Probe {route_id}",
        "summary": f"Inspect {route_id} before collection.",
        "url": url,
        "collect_plan": {
            "title": f"Probe {route_id}",
            "job_type": "source_probe",
            "url": url,
            "launchable": True,
            "requires_approval": True,
        },
    }


def _proposal(proposal_id: str, routes: list[dict], recommended: str | None = None) -> dict:
    return {
        "id": proposal_id,
        "summary": f"Sourcing proposal {proposal_id}",
        "routes": routes,
        "recommended_route_id": recommended or routes[0]["id"],
    }


def _accept(store: DiscoverIntentStore, intent_id: str, proposal: dict) -> dict:
    proposed = store.set_proposal(intent_id, proposal)
    snapshot = proposed["state"]["proposal"]
    return store.review_proposal(
        intent_id,
        decision="accept",
        proposal_id=snapshot["id"],
        proposal_hash=snapshot["proposal_hash"],
    )


class _BlockingJobs:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls: list[dict] = []
        self.jobs: dict[str, dict] = {}

    def submit(self, title, plan, request=None, *, auto_approve=False):
        request = dict(request or {})
        self.calls.append({"title": title, "plan": dict(plan), "request": request})
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test did not release submit")
        return self._put(title, plan, request)

    def _put(self, title, plan, request):
        job_id = str(request.get("idempotency_key") or "")
        job = self.jobs.get(job_id)
        if job is None:
            job = {
                "id": job_id,
                "title": title,
                "status": "pending_approval",
                "plan": dict(plan),
                "request": dict(request),
                "result": {},
            }
            self.jobs[job_id] = job
        return {"job": dict(job), "plan": dict(plan)}

    def get(self, job_id):
        return dict(self.jobs[str(job_id)])


class _ReplayJobs(_BlockingJobs):
    def submit(self, title, plan, request=None, *, auto_approve=False):
        request = dict(request or {})
        self.calls.append({"title": title, "plan": dict(plan), "request": request})
        return self._put(title, plan, request)


class _FailingJobs:
    def __init__(self) -> None:
        self.calls = 0

    def submit(self, *_args, **_kwargs):
        self.calls += 1
        raise RuntimeError("queue unavailable")

    def get(self, job_id):
        raise KeyError(job_id)


def _gateway(store: DiscoverIntentStore, jobs) -> ResearchDataGateway:
    gateway = object.__new__(ResearchDataGateway)
    gateway._discover_intents_store = store
    gateway.jobs = jobs
    return gateway


def test_new_proposal_invalidates_previously_reviewed_routes(tmp_path):
    store = DiscoverIntentStore(tmp_path / "discover-intents.sqlite3")
    intent = store.create(research_need="Need governance evidence")
    route_a = _route("route-a", "https://example.com/a")
    route_b = _route("route-b", "https://example.com/b")

    reviewed = _accept(store, intent["id"], _proposal("proposal-a", [route_a], "route-a"))
    assert reviewed["state"]["selected_route_id"] == "route-a"

    refreshed = store.set_proposal(intent["id"], _proposal("proposal-b", [route_b], "route-b"))

    assert refreshed["state"]["status"] == "proposal_ready"
    assert refreshed["state"]["routes"] == []
    assert refreshed["state"]["selected_route_id"] == ""


def test_pending_replacement_proposal_cannot_submit_superseded_route(tmp_path):
    store = DiscoverIntentStore(tmp_path / "discover-intents.sqlite3")
    intent = store.create(research_need="Need governance evidence")
    route_a = _route("route-a", "https://example.com/a")
    route_b = _route("route-b", "https://example.com/b")
    _accept(store, intent["id"], _proposal("proposal-a", [route_a], "route-a"))
    store.set_proposal(intent["id"], _proposal("proposal-b", [route_b], "route-b"))

    jobs = _FailingJobs()
    gateway = _gateway(store, jobs)

    with pytest.raises(ValueError, match="review|ready"):
        gateway.discover_intent_submit_collection(intent["id"])
    assert jobs.calls == 0


def test_proposal_cannot_replace_an_intent_after_collection_submission(tmp_path):
    store = DiscoverIntentStore(tmp_path / "discover-intents.sqlite3")
    intent = store.create(research_need="Need governance evidence")
    route_a = _route("route-a", "https://example.com/a")
    _accept(store, intent["id"], _proposal("proposal-a", [route_a], "route-a"))
    store.link_job(intent["id"], {"id": f"discover:{intent['id']}", "status": "pending_approval"})

    with pytest.raises(ValueError, match="collection|submitted"):
        store.set_proposal(
            intent["id"],
            _proposal("proposal-b", [_route("route-b", "https://example.com/b")], "route-b"),
        )


def test_route_cannot_change_while_submission_is_in_flight(tmp_path):
    store = DiscoverIntentStore(tmp_path / "discover-intents.sqlite3")
    intent = store.create(research_need="Need governance evidence")
    route_a = _route("route-a", "https://example.com/a")
    route_b = _route("route-b", "https://example.com/b")
    _accept(store, intent["id"], _proposal("proposal-a", [route_a, route_b], "route-a"))

    jobs = _BlockingJobs()
    gateway = _gateway(store, jobs)
    result: list[dict] = []
    errors: list[Exception] = []

    def submit() -> None:
        try:
            result.append(gateway.discover_intent_submit_collection(intent["id"]))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=submit, daemon=True)
    thread.start()
    assert jobs.entered.wait(timeout=5), "submission did not reach queue boundary"

    try:
        with pytest.raises(ValueError, match="submission|collection"):
            store.select_route(intent["id"], "route-b")
    finally:
        jobs.release.set()
        thread.join(timeout=5)

    assert errors == []
    assert len(result) == 1
    final = store.get(intent["id"])
    assert final["state"]["selected_route_id"] == "route-a"
    assert final["state"]["collection"]["job_id"] == f"discover:{intent['id']}"
    assert jobs.calls[0]["request"]["route_id"] == "route-a"


def test_queue_failure_does_not_leave_intent_permanently_submitting(tmp_path):
    store = DiscoverIntentStore(tmp_path / "discover-intents.sqlite3")
    intent = store.create(research_need="Need governance evidence")
    route_a = _route("route-a", "https://example.com/a")
    _accept(store, intent["id"], _proposal("proposal-a", [route_a], "route-a"))

    jobs = _FailingJobs()
    gateway = _gateway(store, jobs)

    with pytest.raises(RuntimeError, match="queue unavailable"):
        gateway.discover_intent_submit_collection(intent["id"])

    after = store.get(intent["id"])
    assert after["state"]["status"] == "ready_for_review"
    assert after["state"]["selected_route_id"] == "route-a"
    assert after["state"]["collection"]["job_id"] == ""
    assert after["state"]["collection"]["status"] == "not_started"


def test_retry_recovers_job_created_before_intent_link(tmp_path, monkeypatch):
    """A crash after queue creation must converge onto the same consequence."""
    store = DiscoverIntentStore(tmp_path / "discover-intents.sqlite3")
    intent = store.create(research_need="Need governance evidence")
    route_a = _route("route-a", "https://example.com/a")
    _accept(store, intent["id"], _proposal("proposal-a", [route_a], "route-a"))

    jobs = _ReplayJobs()
    gateway = _gateway(store, jobs)
    real_link = store.link_job
    link_calls = 0

    def fail_first_link(intent_id, job):
        nonlocal link_calls
        link_calls += 1
        if link_calls == 1:
            raise RuntimeError("intent database interrupted after queue commit")
        return real_link(intent_id, job)

    monkeypatch.setattr(store, "link_job", fail_first_link)

    with pytest.raises(RuntimeError, match="database interrupted"):
        gateway.discover_intent_submit_collection(intent["id"])

    stranded = store.get(intent["id"])
    assert stranded["state"]["status"] == "submitting"
    assert stranded["state"]["collection"]["status"] == "submitting"
    assert stranded["state"]["collection"]["job_id"] == ""
    assert len(jobs.jobs) == 1

    recovered = gateway.discover_intent_submit_collection(intent["id"])
    expected_job = f"discover:{intent['id']}"
    assert recovered["job"]["id"] == expected_job
    assert len(jobs.jobs) == 1
    assert {call["request"]["route_id"] for call in jobs.calls} == {"route-a"}
    final = store.get(intent["id"])
    assert final["state"]["status"] == "pending_approval"
    assert final["state"]["collection"]["job_id"] == expected_job
