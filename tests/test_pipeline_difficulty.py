from scripts.research_data_mcp.pipeline_difficulty import (
    load_pipeline_benchmark_cases,
    observed_pipeline_tier,
    tier_from_access_tier,
)
from scripts.research_data_mcp.registry_access import QUERY_GUARDED, QUERY_INSTANT


def test_benchmark_cases_have_no_preset_tiers() -> None:
    for row in load_pipeline_benchmark_cases():
        assert "tier" not in row
        assert row.get("query")


def test_tier_from_access_tier() -> None:
    assert tier_from_access_tier(QUERY_INSTANT) == "T1_instant"
    assert tier_from_access_tier(QUERY_GUARDED) == "T3_guarded_remote"


def test_observed_tier_bigquery_dry_run() -> None:
    workflow = {"discover": {"bigquery_hints": [{"registry_id": "ethereum_usdt_transfers"}]}}
    ft = {"bigquery_dry_run": {"meta": {"within_execution_guard": True, "mode": "dry_run"}}}
    assert observed_pipeline_tier(workflow, ft) == "T3_guarded_remote"


def test_observed_tier_instant_rows() -> None:
    workflow = {"discover": {"candidates": [{"dataset_id": "some_panel"}]}}
    ft = {"sample_query": {"rows": [{"x": 1}]}}
    assert observed_pipeline_tier(workflow, ft) == "T1_instant"


def test_observed_tier_local_ready_vault() -> None:
    workflow = {
        "index_miss": False,
        "strong_local_hit": True,
        "discover": {
            "candidates": [
                {
                    "dataset_id": "example_layer",
                    "local_ready": True,
                    "collect_via": "local_open",
                }
            ]
        },
    }
    ft = {}
    assert observed_pipeline_tier(workflow, ft) == "T2_vault"
