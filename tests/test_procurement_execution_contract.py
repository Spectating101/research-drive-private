from __future__ import annotations

import pytest

from scripts.research_data_mcp.craft_collect import craft_collect_plan
from scripts.research_data_mcp.procurement_execution_contract import compile_procurement_execution_plan
from scripts.yzu_cluster.interop_contract import InteropStore


def test_source_probe_compiles_runtime_owned_placement():
    plan = compile_procurement_execution_plan(
        {
            "title": "Probe source",
            "job_type": "source_probe",
            "url": "https://example.com/data",
            "research_need": "Need a public source for issuer governance fields",
        }
    )

    assert plan["required_capabilities"] == ["http"]
    assert plan["resource_requirements"] == {"cpu_cores": 0.25, "memory_mb": 128.0}
    assert plan["max_attempts"] == 2
    assert plan["cluster_execution"]["placement"] == {
        "authority": "cluster_runtime",
        "worker_bound": False,
        "required_capabilities": ["http"],
        "resource_requirements": {"cpu_cores": 0.25, "memory_mb": 128.0},
    }
    assert [stage["id"] for stage in plan["cluster_execution"]["stages"]] == ["probe"]
    assert plan["cluster_execution"]["evidence_acceptance"]["gap_closure"] == "not_proven_by_collection"


def test_http_manifest_uses_bounded_parallelism_without_binding_workers():
    plan = compile_procurement_execution_plan(
        {
            "title": "Collect files",
            "job_type": "http_manifest",
            "items": [
                {"url": f"https://example.com/file-{idx}.csv", "filename": f"file-{idx}.csv"}
                for idx in range(9)
            ],
            "research_need": "Need daily observations",
        }
    )

    assert plan["required_capabilities"] == ["http"]
    assert plan["shards"] == 4
    assert plan["per_node_workers"] == 2
    assert plan["cluster_execution"]["parallelism"] == {
        "mode": "manifest_shards",
        "hint": 4,
        "item_count": 9,
        "binding": "runtime_only",
    }
    assert plan["cluster_execution"]["placement"]["worker_bound"] is False
    assert "worker_id" not in plan
    assert "pool" not in plan


def test_known_transfer_size_becomes_bounded_disk_and_network_requirement():
    plan = compile_procurement_execution_plan(
        {
            "title": "Bounded collect",
            "job_type": "http_manifest",
            "items": [
                {"url": "https://example.com/a.csv", "expected_bytes": 10 * 1024 * 1024},
                {"url": "https://example.com/b.csv", "content_length": 6 * 1024 * 1024},
            ],
        }
    )

    estimate = plan["cluster_execution"]["resource_estimate"]
    assert estimate["status"] == "bounded"
    assert estimate["transfer_mb"] == 16.0
    assert plan["resource_requirements"]["network_mb"] >= 17
    assert plan["resource_requirements"]["disk_mb"] >= 84


def test_unknown_transfer_does_not_invent_transfer_reservations():
    plan = compile_procurement_execution_plan(
        {
            "title": "Unknown size",
            "job_type": "http_manifest",
            "items": [{"url": "https://example.com/a.csv"}],
        }
    )

    assert plan["cluster_execution"]["resource_estimate"] == {
        "status": "baseline_only",
        "transfer_bytes": None,
        "source": "unmeasured",
    }
    assert plan["resource_requirements"] == {"cpu_cores": 0.5, "memory_mb": 256.0}


def test_scraper_requires_browser_and_preserves_larger_baseline():
    plan = compile_procurement_execution_plan(
        {
            "title": "Browser collect",
            "job_type": "scraper_run",
            "script_key": "generic_url_scrape",
            "url": "https://example.com/dashboard",
            "resource_requirements": {"memory_mb": 2048},
        }
    )

    assert plan["required_capabilities"] == ["browser"]
    assert plan["resource_requirements"] == {
        "cpu_cores": 1.0,
        "memory_mb": 2048.0,
        "disk_mb": 256.0,
    }
    assert plan["max_attempts"] == 2


@pytest.mark.parametrize("binding", [
    {"worker_id": "lab-7"},
    {"assigned_worker": "lab-7"},
    {"pool": "windows_lab"},
])
def test_compiler_rejects_model_side_worker_or_pool_binding(binding):
    with pytest.raises(ValueError, match="runtime owns|runtime owns worker placement|cannot bind pool"):
        compile_procurement_execution_plan(
            {
                "title": "Bad binding",
                "job_type": "http_manifest",
                "items": [{"url": "https://example.com/a.csv"}],
                **binding,
            }
        )


def test_contract_hash_is_deterministic_and_changes_with_material_requirements():
    base = {
        "title": "Stable plan",
        "job_type": "http_manifest",
        "items": [{"url": "https://example.com/a.csv"}],
    }
    one = compile_procurement_execution_plan(base)
    two = compile_procurement_execution_plan(base)
    larger = compile_procurement_execution_plan({**base, "resource_requirements": {"memory_mb": 4096}})

    assert one["cluster_execution"]["contract_hash"] == two["cluster_execution"]["contract_hash"]
    assert one["cluster_execution"]["contract_hash"] != larger["cluster_execution"]["contract_hash"]


def test_craft_path_emits_compiled_cluster_contract():
    crafted = craft_collect_plan(
        research_need="Need a public daily market file",
        url="https://example.com/market.csv",
    )
    plan = crafted["plan"]

    assert plan["job_type"] == "http_manifest"
    assert plan["required_capabilities"] == ["http"]
    assert plan["cluster_execution"]["placement"]["authority"] == "cluster_runtime"
    assert plan["cluster_execution"]["evidence_acceptance"]["proof_required"] is True


def test_compiled_plan_drives_real_capacity_and_capability_claiming():
    plan = compile_procurement_execution_plan(
        {
            "title": "Collect research file",
            "job_type": "http_manifest",
            "items": [{"url": "https://example.com/research.csv"}],
        }
    )
    store = InteropStore()
    try:
        store.upsert_worker(
            "small-http",
            capabilities=["http"],
            capacity={"cpu_cores": 0.25, "memory_mb": 128},
        )
        store.upsert_worker(
            "adequate-http",
            capabilities=["http"],
            capacity={"cpu_cores": 2, "memory_mb": 2048},
        )
        store.upsert_worker(
            "browser-only",
            capabilities=["browser"],
            capacity={"cpu_cores": 4, "memory_mb": 4096},
        )
        run = store.submit(
            job_id="compiled-http",
            job_type=plan["job_type"],
            required_capabilities=plan["required_capabilities"],
            resource_requirements=plan["resource_requirements"],
        )

        assert store.claim("small-http") is None
        assert store.claim("browser-only") is None
        claim = store.claim("adequate-http")
        assert claim is not None
        assert claim.run_id == run["run_id"]
        assert claim.worker_id == "adequate-http"
        reservation = store.reservation(run["run_id"])
        assert reservation is not None
        assert reservation["cpu_cores"] == 0.5
        assert reservation["memory_mb"] == 256.0
    finally:
        store.close()
