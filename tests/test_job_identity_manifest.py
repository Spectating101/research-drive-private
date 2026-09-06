from __future__ import annotations


def test_registration_manifest_proof_is_exposed_as_job_identity():
    from scripts.research_data_mcp.job_identity import enrich_job_identity

    job = {
        "id": "registered-manifest",
        "status": "completed",
        "request": {"candidate_key": "url:https://example.com/data.csv"},
        "plan": {},
        "result": {
            "registry_promotion": [{"dataset_id": "research_dataset"}],
            "registration_evidence": {
                "dataset_id": "research_dataset",
                "registry_id": "research_dataset",
                "manifest_id": "collection_manifest_research_dataset",
                "archive_verified": True,
                "registry_readback_verified": True,
            },
        },
    }

    enriched = enrich_job_identity(job)

    assert enriched["registered_dataset_id"] == "research_dataset"
    assert enriched["output_manifest_id"] == "collection_manifest_research_dataset"


def test_manifest_identity_remains_null_without_explicit_proof():
    from scripts.research_data_mcp.job_identity import enrich_job_identity

    enriched = enrich_job_identity(
        {
            "id": "no-manifest",
            "status": "completed",
            "request": {},
            "plan": {},
            "result": {"registration_evidence": {"dataset_id": "research_dataset"}},
        }
    )

    assert enriched["output_manifest_id"] is None
