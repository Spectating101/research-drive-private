"""Sandboxed production lifecycle for a researcher-approved Synthesis output."""

from __future__ import annotations

import json
from pathlib import Path


def test_approved_synthesis_lifecycle_reaches_registered_only_after_readback(
    tmp_path: Path,
):
    from scripts.research_data_mcp.gateway import ResearchDataGateway
    from scripts.research_data_mcp.synthesis_thread_store import SynthesisThreadStore
    from scripts.yzu_cluster.jobs import YzuJobStore
    from scripts.yzu_cluster.runtime_adapter import ClusterRuntimeAdapter

    repo = Path(__file__).resolve().parents[1] / "drive"
    config = tmp_path / "config"
    config.mkdir()
    registry_path = config / "research_query_registry.json"
    registry_path.write_text(
        (repo / "config/research_query_registry.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    gateway = ResearchDataGateway(repo, registry_path=registry_path)
    # Keep the real validator/executor configuration, but isolate every mutable
    # lifecycle store and make registry readback come from the sandbox.
    gateway.repo_root = tmp_path
    gateway.registry_path = registry_path
    gateway._synthesis_threads_store = SynthesisThreadStore(tmp_path / "threads.sqlite3")
    orchestrator = gateway.orchestrator
    orchestrator.store = YzuJobStore(tmp_path / "jobs.sqlite3")
    orchestrator.runtime = ClusterRuntimeAdapter(orchestrator.store.path, orchestrator.cfg)

    output_id = "synthesis_neutral_issuer_week_v2"
    thread = gateway.synthesis_thread_create(
        objective="Construct a defensible issuer-week synthesis panel.",
        title="Sandbox production lifecycle",
        required_grain="issuer-week",
        state={
            "required_grain": "issuer-week",
            "materialisation": "not_materialised",
            "nodes": [
                {
                    "id": "held",
                    "type": "source",
                    "layer": "evidence",
                    "label": "Held weekly panel",
                    "status": "held",
                    "dataset_id": "stablecoin_trust_engagement_weekly",
                    "grain": "entity-week",
                },
                {
                    "id": "out",
                    "type": "output",
                    "layer": "output",
                    "label": "issuer_week_panel",
                    "status": "planned",
                    "materialisation": "not_materialised",
                },
            ],
            "edges": [],
            "spec": {"grain": "issuer-week"},
        },
    )
    thread_id = thread["id"]
    execution_spec = {
        "input_dataset_id": "stablecoin_trust_engagement_weekly",
        "output_dataset_id": output_id,
        "group_by": [],
        "metrics": [{"function": "count", "as": "row_count"}],
        "transforms": [],
    }

    proposed = gateway.synthesis_thread_propose_state(
        thread_id,
        proposal_id="sandbox-v2",
        title="Aggregate held panel into issuer-week output",
        summary="Review-only execution proposal.",
        operations=[{"op": "append_activity", "message": "Sandbox execution proposed."}],
        execution_spec=execution_spec,
    )
    proposal = (proposed["state"] or {}).get("proposal")
    assert proposal and proposal["execution_preflight"]["ok"] is True

    accepted = gateway.synthesis_thread_apply_patch(
        thread_id,
        decision="accept",
        proposal_id=proposal["id"],
        proposal_hash=proposal["proposal_hash"],
    )
    assert accepted["state"].get("accepted_spec_hash")

    submitted = gateway.synthesis_thread_submit_execution(thread_id)
    job = submitted["job"]
    assert job["status"] == "pending_approval"
    assert gateway.synthesis_thread_submit_execution(thread_id)["idempotent"] is True
    assert gateway.synthesis_thread_materialisation(thread_id)["materialisation"] == "not_materialised"

    approved = gateway.approve_yzu_job(job["id"])
    assert approved["status"] == "queued"

    completed = orchestrator.store.update(
        job["id"],
        "completed",
        {
            "rows": 42,
            "materialized": {"dataset_id": output_id},
            "output_manifest_id": "manifest-sandbox-2",
            "drive_finalize": {"ok": True},
            "registry_promotion": [{"dataset_id": output_id}],
        },
    )
    # Worker completion alone cannot upgrade the Synthesis lifecycle.
    assert gateway.synthesis_thread_materialisation(thread_id)["materialisation"] == "not_materialised"

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["datasets"].append(
        {
            "dataset_id": output_id,
            "title": "Sandbox issuer-week synthesis output",
            "canonical_remote": f"gdrive://sandbox/{output_id}",
            "field_coverage": "query-ready",
            "analysis_readiness": "instant",
            "materialization": {"query_ready": True},
        }
    )
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    registered = gateway.synthesis_thread_record_execution(thread_id, completed)
    final = gateway.synthesis_thread_materialisation(thread_id)
    assert registered["state"]["execution"]["status"] == "registered"
    assert registered["state"]["execution"]["manifest_id"] == "manifest-sandbox-2"
    assert final["materialisation"] == "registered"
    assert final["output_registered"] is True
    assert final["output_dataset_id"] == output_id
