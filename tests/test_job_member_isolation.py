from __future__ import annotations

import pytest

from scripts.research_data_mcp.desk_auth import desk_principal_context
from scripts.research_data_mcp.desk_principal import DeskPrincipal
from scripts.research_data_mcp.jobs import JobService


ALICE = DeskPrincipal("alice", "alice@example.test", "Alice", "member")
BOB = DeskPrincipal("bob", "bob@example.test", "Bob", "member")
OPERATOR = DeskPrincipal("operator", "operator@example.test", "Operator", "operator")


class FakeOrchestrator:
    def __init__(self):
        self.jobs = []

    def validate_plan(self, plan):
        return dict(plan, launchable=True)

    def submit(self, title, plan, request, auto_approve=False):
        job = {
            "job_id": f"job-{len(self.jobs) + 1}",
            "title": title,
            "plan": plan,
            "request": dict(request),
            "status": "pending",
        }
        self.jobs.append(job)
        return job

    def get_job(self, job_id):
        return next(job for job in self.jobs if job["job_id"] == job_id)

    def list_jobs(self, limit, status=""):
        rows = [job for job in self.jobs if not status or job["status"] == status]
        return rows[:limit]


def test_member_jobs_are_owned_and_history_is_isolated(monkeypatch):
    monkeypatch.setattr(
        "scripts.research_data_mcp.execution_policy.enforce_execution_submit",
        lambda plan, request, auto_approve=False: (plan, auto_approve),
    )
    service = JobService(FakeOrchestrator())
    with desk_principal_context(ALICE):
        alice_job = service.submit("Alice source", {"job_type": "source_probe"})["job"]
        assert alice_job["request"]["owner_id"] == "alice"
    with desk_principal_context(BOB):
        bob_job = service.submit("Bob source", {"job_type": "source_probe"})["job"]
        assert [job["job_id"] for job in service.list()["jobs"]] == [bob_job["job_id"]]
        with pytest.raises(KeyError):
            service.get(alice_job["job_id"])
    with desk_principal_context(ALICE):
        assert [job["job_id"] for job in service.list()["jobs"]] == [alice_job["job_id"]]
    with desk_principal_context(OPERATOR):
        assert {job["job_id"] for job in service.list()["jobs"]} == {
            alice_job["job_id"], bob_job["job_id"]
        }
