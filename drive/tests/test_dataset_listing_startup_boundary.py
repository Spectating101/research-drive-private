from pathlib import Path

from scripts.research_data_mcp import search


class _Engine:
    def list_datasets(self):
        return [
            {
                "dataset_id": "held_panel",
                "display_name": "Held panel",
                "analysis_readiness": "instant",
                "materialization": {"query_ready": True},
            }
        ]


def test_dataset_listing_does_not_recompute_partition_lanes(monkeypatch):
    service = object.__new__(search.SearchService)
    service.engine = _Engine()
    service.registry_path = Path("registry.json")
    service.repo_root = Path(".")
    monkeypatch.setattr(service, "_maybe_reload_registry", lambda: None)
    monkeypatch.setattr(service, "_receipt_rows", lambda: [])

    observed = {}

    def inventory(rows, **kwargs):
        observed.update(kwargs)
        return {
            "version": 1,
            "registry_revision": {"fingerprint": "test"},
            "totals": {
                "registered": len(rows),
                "visible_to_desk": len(rows),
                "excluded_operational_test": 0,
            },
        }

    monkeypatch.setattr(search, "build_inventory_summary", inventory)

    result = service.list_datasets()

    assert result["datasets"][0]["dataset_id"] == "held_panel"
    assert observed["include_partition_lanes"] is False
