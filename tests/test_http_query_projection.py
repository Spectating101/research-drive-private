from types import SimpleNamespace

from scripts.research_data_mcp import http_router


class _Gateway:
    repo_root = "/tmp/research-drive-test"

    def list_datasets(self, **params):
        assert params["limit"] == 200
        return {
            "datasets": [
                {
                    "dataset_id": "sample",
                    "readiness_note": (
                        "missing panel file: "
                        "/mnt/research-data/private/tree/panel.parquet"
                    ),
                    "quarantine": {
                        "path": "/mnt/research-data/private/quarantine/panel.parquet",
                        "manifest": "/mnt/research-data/private/quarantine/manifest.json",
                        "reason": "schema mismatch",
                    },
                }
            ],
            "total": 1,
        }

    def describe_dataset(self, dataset_id):
        assert dataset_id == "sample"
        return {
            "dataset_id": dataset_id,
            "local_path": "/home/user/private.csv",
            "quarantine": {
                "path": "/mnt/research-data/private/quarantine/panel.parquet",
                "reason": "schema mismatch",
            },
        }

    def query_dataset(self, dataset_id, params):
        assert dataset_id == "sample"
        assert params == {"limit": 1}
        return {
            "dataset_id": dataset_id,
            "rows": [
                {
                    "source_file": "/mnt/research-data/private/tree/panel.parquet",
                    "public_route": "/api/v1/observations",
                    "url": "https://example.test/data.csv",
                    "structured": {"label": "kept", "local_path": "/home/user/private.csv"},
                }
            ],
            "meta": {
                "canonical_remote": "gdrive:Machine_Archive/private",
                "returned": 1,
            },
        }


def test_researcher_query_projection_hides_host_storage_topology():
    projected = http_router._researcher_query_projection(
        {
            "rows": [
                {
                    "source_file": "/mnt/research-data/private/tree/panel.parquet",
                    "attachment": "file:///tmp/private/report.csv",
                    "public_route": "/api/v1/observations",
                }
            ],
            "meta": {"local_root": "/srv/research", "returned": 1},
        }
    )

    assert projected == {
        "rows": [
            {
                "source_file": "panel.parquet",
                "attachment": "report.csv",
                "public_route": "/api/v1/observations",
            }
        ],
        "meta": {"returned": 1},
    }


def test_http_query_handler_projects_rows_without_changing_gateway_query():
    stack = SimpleNamespace(gateway=_Gateway())

    response = http_router._dispatch(
        "GET",
        "/query/sample",
        {"limit": "1"},
        {},
        stack,
    )

    assert response["status"] == 200
    assert response["body"]["rows"][0] == {
        "source_file": "panel.parquet",
        "public_route": "/api/v1/observations",
        "url": "https://example.test/data.csv",
        "structured": {"label": "kept"},
    }
    assert response["body"]["meta"] == {"returned": 1}


def test_http_dataset_handlers_project_nested_storage_topology():
    stack = SimpleNamespace(gateway=_Gateway())

    listing = http_router._dispatch("GET", "/datasets", {}, {}, stack)
    detail = http_router._dispatch("GET", "/datasets/sample", {}, {}, stack)

    assert listing["status"] == 200
    assert listing["body"] == {
        "datasets": [
            {
                "dataset_id": "sample",
                "readiness_note": "missing panel file: panel.parquet",
                "quarantine": {
                    "path": "panel.parquet",
                    "manifest": "manifest.json",
                    "reason": "schema mismatch",
                },
            }
        ],
        "total": 1,
    }
    assert detail["status"] == 200
    assert detail["body"] == {
        "dataset_id": "sample",
        "quarantine": {"path": "panel.parquet", "reason": "schema mismatch"},
    }
