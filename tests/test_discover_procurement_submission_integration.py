from __future__ import annotations

import threading

import scripts.research_data_mcp.jobs as jobs_module
from scripts.research_data_mcp.jobs import JobService
from scripts.research_data_mcp.procurement_execution_contract import compile_procurement_execution_plan


class DurableOrchestratorDouble:
    """Model the existing idempotent orchestrator boundary without network I/O."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.create_count = 0
        self._lock = threading.Lock()

    def validate_plan(self, plan):
        return {**plan, "launchable": True}

    def get_job(self, job_id):
        with self._lock:
            job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def submit(self, title, plan, request, *, auto_approve=False):
        key = str(request.get("idempotency_key") or "")
        with self._lock:
            existing = self.jobs.get(key)
            if existing is not None:
                return existing
            self.create_count += 1
            job = {
                "id": key,
                "title": title,
                "status": "pending_approval",
                "plan": dict(plan),
                "request": dict(request),
            }
            self.jobs[key] = job
            return job


def compiled_http_plan():
    return compile_procurement_execution_plan(
        {
            "job_type": "http_manifest",
            "title": "Acquire governance evidence",
            "research_need": "Need verified issuer-quarter governance fields",
            "items": [{"url": "https://example.test/governance.csv"}],
            "launchable": True,
            "requires_approval": True,
        }
    )


def test_compiled_procurement_contract_survives_into_single_durable_approval_job(monkeypatch):
    monkeypatch.setattr(jobs_module, "owner_id_for_create", lambda: "")
    monkeypatch.setattr(jobs_module, "require_owner", lambda owner_id, object_id: None)

    orchestrator = DurableOrchestratorDouble()
    service = JobService(orchestrator)
    plan = compiled_http_plan()

    first = service.submit(
        "Acquire governance evidence",
        plan,
        {
            "source": "discover_intent",
            "discover_intent_id": "intent-integration",
            "route_id": "route-a",
            "research_need": "Need verified issuer-quarter governance fields",
        },
        auto_approve=False,
    )

    # A second tab may have a different selected route by the time its request
    # lands. The intent itself remains one collection authority, so it must
    # recover the first durable job instead of compiling/submitting a second one.
    replay = service.submit(
        "Acquire governance evidence via alternate route",
        compiled_http_plan(),
        {
            "source": "discover_intent",
            "discover_intent_id": "intent-integration",
            "route_id": "route-b",
            "research_need": "Need verified issuer-quarter governance fields",
        },
        auto_approve=False,
    )

    assert orchestrator.create_count == 1
    assert first["job"]["id"] == replay["job"]["id"] == "discover-submit:intent-integration"
    assert replay["idempotent_replay"] is True

    stored = first["job"]["plan"]
    execution = stored["cluster_execution"]
    summary = execution["engineering_summary"]

    assert summary["status"] == "compiled"
    assert summary["primitive"] == "http_manifest"
    # Internal execution authority stays explicit/technical, while the compact
    # researcher-facing summary intentionally compresses it to "runtime".
    assert execution["placement"]["authority"] == "cluster_runtime"
    assert summary["placement"] == "runtime"
    assert summary["preflight"] == "recommended"
    assert summary["post_acquisition_reassessment"] is True
    assert stored["requires_approval"] is True
    assert first["job"]["status"] == "pending_approval"

    # The retry returns the original selected route/job; route mutation after the
    # first durable insert cannot mutate execution authority in place.
    assert replay["job"]["request"]["route_id"] == "route-a"
