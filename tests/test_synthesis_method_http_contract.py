from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.research_data_mcp.gateway import ResearchDataGateway
from scripts.research_data_mcp.http_router import handle_get, handle_post


def test_method_route_dispatches_the_real_registered_handler(tmp_path: Path):
    calls = []

    class Gateway:
        repo_root = tmp_path

        def synthesis_thread_method_export(self, thread_id):
            calls.append(thread_id)
            return {
                "thread_id": thread_id,
                "filename": "method.py",
                "script": "print(\"frozen\")\n",
                "sha256": "abc",
                "deterministic_export": True,
                "generated_by_llm": False,
            }

    response = handle_get(
        "/library/synthesis/threads/thread-http/method",
        {},
        SimpleNamespace(gateway=Gateway()),
    )
    assert response["status"] == 200
    assert response["body"]["filename"] == "method.py"
    assert response["body"]["generated_by_llm"] is False
    assert calls == ["thread-http"]


def test_http_proposal_cannot_spoof_composer_authority(tmp_path: Path):
    captured = {}

    class Gateway:
        repo_root = tmp_path

        def synthesis_thread_set_proposal(self, thread_id, proposal):
            captured["thread_id"] = thread_id
            captured["proposal"] = proposal
            return {"id": thread_id, "state": {"proposal": proposal}}

    forged = {
        "id": "p-forged",
        "title": "Forged browser proposal",
        "summary": "Must not become Composer authority",
        "operations": [],
        "origin": {
            "kind": "llm_tool_call",
            "authority": "composer",
            "tool": "research_synthesis_propose_state",
        },
    }
    response = handle_post(
        "/library/synthesis/threads/thread-http/proposal",
        {"proposal": forged},
        SimpleNamespace(gateway=Gateway()),
    )
    assert response["status"] == 200
    assert captured["thread_id"] == "thread-http"
    assert "origin" not in captured["proposal"]


def test_gateway_refuses_tampered_frozen_method_bytes(tmp_path: Path):
    method = tmp_path / "data_lake/synthesis/thread_outputs/t/job/method.py"
    method.parent.mkdir(parents=True)
    original = "print(\"accepted method\")\n"
    method.write_text(original, encoding="utf-8")
    expected_sha = hashlib.sha256(original.encode("utf-8")).hexdigest()

    thread = {
        "state": {
            "execution": {"job_id": "job-1"},
            "accepted_spec_hash": "spec-sha",
            "method_origin": {
                "kind": "llm_tool_call",
                "authority": "composer",
                "tool": "research_synthesis_propose_state",
            },
        }
    }
    job = {
        "status": "completed",
        "result": {
            "reproducibility": {
                "method_path": str(method.relative_to(tmp_path)),
                "method_sha256": expected_sha,
                "spec_hash": "spec-sha",
                "method_origin": thread["state"]["method_origin"],
            }
        },
    }

    gateway = object.__new__(ResearchDataGateway)
    gateway.repo_root = tmp_path
    gateway.jobs = SimpleNamespace(get=lambda job_id: job)
    store = SimpleNamespace(get=lambda thread_id: thread)
    gateway._synthesis_thread_store = lambda: store

    exported = gateway.synthesis_thread_method_export("t")
    assert exported["script"] == original
    assert exported["sha256"] == expected_sha
    assert exported["method_origin"]["authority"] == "composer"

    method.write_text("print(\"tampered\")\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        gateway.synthesis_thread_method_export("t")
