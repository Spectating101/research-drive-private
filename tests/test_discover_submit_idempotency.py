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
        # with SQLite uniqueness and returns an exact replay only when the whole
        # stored submission matches; a same-key/different-payload collision fails.
        time.sleep(0.03)
        key = str(request.get("idempotency_key") or "")
        with self._lock:
            if key:
                existing = next((job for job in self.jobs if job.get("id") == key), None)
                if existing is not None:
                    if (
                        existing.get("title") != title
                        or existing.get("plan") != plan
                        or existing.get("request") != request
                    ):
                        raise ValueError("idempotency key already exists with a different request")
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


def proposal(prefix="proposal", route_a="route-a", route_b="route-b"):
    return {
        "id": prefix,
        "summary": f"{prefix} reviewed routes",
        "routes": [
            {"id": route_a, "title": f"{route_a} title", "connector_id": f"connector-{route_a}"},
            {"id": route_b, "title": f"{route_b} title", "connector_id": f"connector-{route_b}"},
        ],
        "recommended_route_id": route_a,
    }


def reviewed_two_route_intent(store: DiscoverIntentStore) -> dict:
    intent = store.create(research_need="Need evidence")
    proposed = store.set_proposal(intent["id"], proposal())
    recorded = proposed["state"]["proposal"]
    return store.review_proposal(
        intent["id"],
        decision="accept",
        proposal_id=recorded["id"],
        proposal_hash=recorded["proposal_hash"],
    )


def winning_job(job_id="discover-submit:route-race", route_id="route-a"):
    return {
        "id": job_id,
        "title": f"Collect via {route_id}",
        "status": "pending_approval",
        "request": {"route_id": route_id, "connector_id": f"connector-{route_id}", "pipeline": "custom"},
        "plan": {
            "candidate_key": "dataset:winning",
            "destination": "data_lake/procured/winning",
            "pipeline": "custom",
        },
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


def test_simultaneous_route_mutation_recovers_the_durable_winner():
    orchestrator = FakeOrchestrator()
    service = JobService(orchestrator)
    barrier = threading.Barrier(2)

    def submit_once(route_id):
        barrier.wait(timeout=2)
        return service.submit(
            f"Collect via {route_id}",
            generic_plan(),
            discover_request("intent-race", route_id),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(submit_once, "route-a")
        second_future = pool.submit(submit_once, "route-b")
        results = [first_future.result(), second_future.result()]

    assert orchestrator.submit_count == 1
    assert {result["job"]["id"] for result in results} == {"discover-submit:intent-race"}
    winning_routes = {result["job"]["request"]["route_id"] for result in results}
    assert winning_routes in ({"route-a"}, {"route-b"})
    assert sum(bool(result.get("idempotent_replay")) for result in results) == 1


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


def test_route_selection_and_job_link_serialize_on_winning_job_route(tmp_path, monkeypatch):
    monkeypatch.setattr(intent_store_module, "owner_id_for_create", lambda owner_id="": "")
    monkeypatch.setattr(intent_store_module, "require_owner", lambda owner_id, object_id: None)

    store = DiscoverIntentStore(tmp_path / "discover-route-race.sqlite3")
    intent = reviewed_two_route_intent(store)
    barrier = threading.Barrier(2)
    select_errors: list[Exception] = []

    def select_other_route():
        barrier.wait(timeout=2)
        try:
            store.select_route(intent["id"], "route-b")
        except ValueError as exc:
            select_errors.append(exc)

    def link_winner():
        barrier.wait(timeout=2)
        store.link_job(intent["id"], winning_job())

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(select_other_route)
        second = pool.submit(link_winner)
        first.result()
        second.result()

    final = store.get(intent["id"])
    assert final["state"]["collection"]["job_id"] == "discover-submit:route-race"
    assert final["state"]["selected_route_id"] == "route-a"
    assert [event["kind"] for event in store.events(intent["id"])].count("job_linked") == 1
    assert not select_errors or "cannot change Discover decision after collection submission" in str(select_errors[0])


def test_post_submission_freezes_proposal_review_and_route_decisions(tmp_path, monkeypatch):
    monkeypatch.setattr(intent_store_module, "owner_id_for_create", lambda owner_id="": "")
    monkeypatch.setattr(intent_store_module, "require_owner", lambda owner_id, object_id: None)

    store = DiscoverIntentStore(tmp_path / "discover-terminal.sqlite3")
    intent = reviewed_two_route_intent(store)
    linked = store.link_job(intent["id"], winning_job("discover-submit:terminal"))
    assert linked["state"]["status"] == "pending_approval"

    with pytest.raises(ValueError, match="cannot change Discover decision after collection submission"):
        store.set_proposal(intent["id"], proposal("late-proposal", "route-c", "route-d"))
    with pytest.raises(ValueError, match="cannot change Discover decision after collection submission"):
        store.review_proposal(
            intent["id"],
            decision="accept",
            proposal_id="late-proposal",
            proposal_hash="stale-hash",
        )
    with pytest.raises(ValueError, match="cannot change Discover decision after collection submission"):
        store.select_route(intent["id"], "route-b")

    final = store.get(intent["id"])
    assert final["state"]["status"] == "pending_approval"
    assert final["state"]["selected_route_id"] == "route-a"
    assert final["state"]["proposal"] is None


def test_review_race_cannot_supersede_winning_job_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(intent_store_module, "owner_id_for_create", lambda owner_id="": "")
    monkeypatch.setattr(intent_store_module, "require_owner", lambda owner_id, object_id: None)

    store = DiscoverIntentStore(tmp_path / "discover-review-race.sqlite3")
    intent = reviewed_two_route_intent(store)
    proposed = store.set_proposal(intent["id"], proposal("replacement", "route-c", "route-d"))
    replacement = proposed["state"]["proposal"]
    barrier = threading.Barrier(2)
    review_errors: list[Exception] = []

    def accept_replacement():
        barrier.wait(timeout=2)
        try:
            store.review_proposal(
                intent["id"],
                decision="accept",
                proposal_id=replacement["id"],
                proposal_hash=replacement["proposal_hash"],
            )
        except ValueError as exc:
            review_errors.append(exc)

    def link_winner():
        barrier.wait(timeout=2)
        store.link_job(intent["id"], winning_job("discover-submit:review-race", "route-a"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(accept_replacement)
        second = pool.submit(link_winner)
        first.result()
        second.result()

    final = store.get(intent["id"])
    assert final["state"]["collection"]["job_id"] == "discover-submit:review-race"
    assert final["state"]["status"] == "pending_approval"
    assert final["state"]["selected_route_id"] == "route-a"
    assert final["state"]["proposal"] is None
    assert any(route.get("id") == "route-a" for route in final["state"]["routes"])
    linked_event = next(event for event in store.events(intent["id"]) if event["kind"] == "job_linked")
    assert linked_event["payload"]["route_id"] == "route-a"
    assert not review_errors or "cannot change Discover decision after collection submission" in str(review_errors[0])


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
