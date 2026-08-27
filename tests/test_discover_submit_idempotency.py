from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import scripts.research_data_mcp.discover_intent_store as intent_store_module
import scripts.research_data_mcp.jobs as jobs_module
from scripts.research_data_mcp.discover_intent_store import DiscoverIntentStore
from scripts.research_data_mcp.jobs import JobService


class FakeOrchestrator:
    """Small durable-job-store double for the JobService boundary."""

    def __init__(self) -> None:
        self.jobs: list[dict] = []
        self.submit_count = 0
        self._lock = threading.Lock()

    def validate_plan(self, plan):
        return {**plan, "launchable": True}

    def get_job(self, job_id):
        with self._lock:
            found = next((job for job in self.jobs if job.get("id") == job_id), None)
        if found is None:
            raise KeyError(job_id)
        return found

    def submit(self, title, plan, request, *, auto_approve=False):
        # Widen the pre-insert race window. The real YzuOrchestrator resolves this
        # with the SQLite job-id uniqueness constraint; this double models the
        # same durable idempotency contract.
        time.sleep(0.03)
        key = str(request.get("idempotency_key") or "")
        with self._lock:
            if key:
                existing = next((job for job in self.jobs if job.get("id") == key), None)
                if existing is not None:
                    return existing
            self.submit_count += 1
            job = {
                "id": key or f"job-{self.submit_count}",
                "title": title,
                "plan": dict(plan),
                "request": dict(request),
                "status": "pending_approval",
            }
            self.jobs.insert(0, job)
            return job

    def list_jobs(self, limit, status=""):
        with self._lock:
            rows = list(self.jobs)
        if status:
            rows = [job for job in rows if job.get("status") == status]
        return rows[:limit]


def discover_request(intent_id="intent-a", route_id="route-a", **extra):
    return {
        "source": "discover_intent",
        "discover_intent_id": intent_id,
        "route_id": route_id,
        "research_need": "Build a bounded evidence panel",
        **extra,
    }


def generic_plan():
    return {
        "job_type": "http_manifest",
        "title": "Collect public evidence",
        "items": [{"url": "https://example.test/data.csv"}],
        "launchable": True,
    }


@pytest.fixture(autouse=True)
def ownerless_test_scope(monkeypatch):
    # Idempotency is orthogonal to principal resolution. Keep these tests focused
    # on the submit boundary while still exercising the real JobService policy.
    monkeypatch.setattr(jobs_module, "owner_id_for_create", lambda: "")
    monkeypatch.setattr(jobs_module, "require_owner", lambda owner_id, object_id: None)


def test_sequential_discover_retry_returns_same_durable_job():
    orchestrator = FakeOrchestrator()
    service = JobService(orchestrator)

    first = service.submit("Collect", generic_plan(), discover_request())
    second = service.submit("Collect", generic_plan(), discover_request())

    assert orchestrator.submit_count == 1
    assert first["job"]["id"] == second["job"]["id"] == "discover-submit:intent-a"
    assert second["idempotent_replay"] is True
    assert first["job"]["request"]["idempotency_key"] == "discover-submit:intent-a"


def test_simultaneous_cross_tab_submits_create_exactly_one_job():
    orchestrator = FakeOrchestrator()
    service = JobService(orchestrator)
    barrier = threading.Barrier(2)

    def submit_once():
        barrier.wait(timeout=2)
        return service.submit("Collect", generic_plan(), discover_request())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit_once(), range(2)))

    assert orchestrator.submit_count == 1
    assert {result["job"]["id"] for result in results} == {"discover-submit:intent-a"}


def test_one_intent_cannot_create_second_job_after_route_changes():
    orchestrator = FakeOrchestrator()
    service = JobService(orchestrator)

    first = service.submit("A", generic_plan(), discover_request("intent-a", "route-a"))
    second = service.submit("B", generic_plan(), discover_request("intent-a", "route-b"))

    assert orchestrator.submit_count == 1
    assert first["job"]["id"] == second["job"]["id"] == "discover-submit:intent-a"
    assert second["idempotent_replay"] is True
    assert second["job"]["request"]["route_id"] == "route-a"


def test_distinct_intents_keep_distinct_durable_jobs():
    orchestrator = FakeOrchestrator()
    service = JobService(orchestrator)

    service.submit("A", generic_plan(), discover_request("intent-a", "route-a"))
    service.submit("B", generic_plan(), discover_request("intent-b", "route-a"))

    assert orchestrator.submit_count == 2
    assert {job["id"] for job in orchestrator.jobs} == {
        "discover-submit:intent-a",
        "discover-submit:intent-b",
    }


def test_discover_overwrites_client_chosen_idempotency_authority():
    orchestrator = FakeOrchestrator()
    service = JobService(orchestrator)

    out = service.submit(
        "Collect",
        generic_plan(),
        discover_request(idempotency_key="client-chosen-job-id"),
    )

    assert out["job"]["id"] == "discover-submit:intent-a"
    assert out["job"]["request"]["idempotency_key"] == "discover-submit:intent-a"


def test_non_discover_submissions_keep_existing_non_idempotent_behavior():
    orchestrator = FakeOrchestrator()
    service = JobService(orchestrator)
    request = {"source": "other_surface"}

    service.submit("First", generic_plan(), request)
    service.submit("Second", generic_plan(), request)

    assert orchestrator.submit_count == 2


def test_intent_link_replay_is_noop_but_conflicting_job_stays_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(intent_store_module, "owner_id_for_create", lambda owner_id="": "")
    monkeypatch.setattr(intent_store_module, "require_owner", lambda owner_id, object_id: None)

    store = DiscoverIntentStore(tmp_path / "discover.sqlite3")
    intent = store.create(research_need="Need evidence")
    job = {"id": "discover-submit:intent-a", "status": "pending_approval"}

    linked = store.link_job(intent["id"], job)
    replayed = store.link_job(intent["id"], job)

    assert linked["state"]["collection"]["job_id"] == "discover-submit:intent-a"
    assert replayed["state"]["collection"]["job_id"] == "discover-submit:intent-a"
    assert [event["kind"] for event in store.events(intent["id"])].count("job_linked") == 1

    with pytest.raises(ValueError, match="already has a collection job"):
        store.link_job(intent["id"], {"id": "different-job", "status": "pending_approval"})
