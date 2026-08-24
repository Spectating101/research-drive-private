from pathlib import Path

from scripts.research_data_mcp.partition_wiring import (
    attach_partition_to_plan,
    infer_partition_id,
    partition_id_for_dataset,
)

REPO = Path(__file__).resolve().parents[1]


def test_partition_from_registry_dataset() -> None:
    pid = partition_id_for_dataset(REPO, "mops_governance_panel")
    assert pid == "official.mops-disclosures"


def test_infer_partition_default_without_dataset() -> None:
    assert infer_partition_id("anything", repo_root=REPO) == "acquired.procured"


def test_attach_partition_from_registry_dataset_id() -> None:
    plan = attach_partition_to_plan(
        {"dataset_id": "mops_governance_panel", "job_type": "scraper_run"},
        "ignored query",
        repo_root=REPO,
    )
    assert plan["partition_id"] == "official.mops-disclosures"
