from __future__ import annotations

from pathlib import Path


class FakeGateway:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def describe_dataset(self, dataset_id: str):
        return {
            "dataset_id": dataset_id,
            "name": "US polling panel",
            "local_path": "data_lake/polls.csv",
            "analysis_readiness": "instant",
            "source": "polling-source",
        }


def test_package_http_prepare_get_and_download(tmp_path, monkeypatch):
    from scripts.research_data_mcp.library_package_http import (
        handle_library_package_get,
        handle_library_package_post,
    )

    (tmp_path / "data_lake").mkdir()
    (tmp_path / "data_lake/polls.csv").write_text("date,pct\n2026-08-01,51\n", encoding="utf-8")
    monkeypatch.setenv("RESEARCH_PACKAGE_ROOT", str(tmp_path / "packages"))
    gateway = FakeGateway(tmp_path)

    made = handle_library_package_post(
        "/library/packages/prepare",
        {"research_need": "US polling", "dataset_ids": ["polls"]},
        gateway,
    )
    assert made["status"] == 200
    package_id = made["body"]["package_id"]
    assert made["body"]["sufficiency_claim"] is False

    fetched = handle_library_package_get(f"/library/packages/{package_id}", {}, gateway)
    assert fetched["status"] == 200
    assert fetched["body"]["package_id"] == package_id
    assert "_archive_file" not in fetched["body"]

    download = handle_library_package_get(f"/library/packages/{package_id}/download", {}, gateway)
    assert download["status"] == 200
    assert download["body"]["_file_delivery"] is True
    assert download["body"]["content_type"] == "application/zip"
    assert Path(download["body"]["file"]).is_file()


def test_package_http_rejects_non_array_ids_and_cannot_raise_server_limits(tmp_path, monkeypatch):
    from scripts.research_data_mcp import library_package_http as http

    (tmp_path / "data_lake").mkdir()
    (tmp_path / "data_lake/polls.csv").write_text("date,pct\n2026-08-01,51\n", encoding="utf-8")
    monkeypatch.setenv("RESEARCH_PACKAGE_ROOT", str(tmp_path / "packages"))
    gateway = FakeGateway(tmp_path)

    bad = http.handle_library_package_post(
        "/library/packages/prepare",
        {"dataset_ids": "polls"},
        gateway,
    )
    assert bad["status"] == 400

    made = http.handle_library_package_post(
        "/library/packages/prepare",
        {
            "dataset_ids": ["polls"],
            "max_datasets": http.DEFAULT_MAX_DATASETS + 500,
            "max_total_bytes": http.DEFAULT_MAX_TOTAL_BYTES + 999_999_999,
        },
        gateway,
    )
    assert made["status"] == 200
    assert made["body"]["data_file_count"] == 1


def test_package_http_is_not_a_catch_all(tmp_path):
    from scripts.research_data_mcp.library_package_http import (
        handle_library_package_get,
        handle_library_package_post,
    )

    gateway = FakeGateway(tmp_path)
    assert handle_library_package_get("/library/search", {}, gateway) is None
    assert handle_library_package_post("/library/search", {}, gateway) is None
