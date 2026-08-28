from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest


class FakeGateway:
    def __init__(self, repo_root: Path, datasets: dict[str, dict]):
        self.repo_root = repo_root
        self._datasets = datasets

    def describe_dataset(self, dataset_id: str):
        if dataset_id not in self._datasets:
            raise KeyError(dataset_id)
        return dict(self._datasets[dataset_id])


def _dataset(dataset_id: str, *, local_path: str = "", readiness: str = "instant") -> dict:
    return {
        "dataset_id": dataset_id,
        "name": dataset_id.replace("_", " ").title(),
        "local_path": local_path,
        "analysis_readiness": readiness,
        "source": "test-source",
        "source_url": f"https://example.test/{dataset_id}",
        "grain": "state-day",
        "coverage": "2020-2026",
        "join_keys": ["state", "date"],
    }


def test_package_includes_only_verified_local_bytes_and_records_every_other_state(tmp_path, monkeypatch):
    from scripts.research_data_mcp.library_packages import prepare_library_package

    held = tmp_path / "data_lake/held"
    held.mkdir(parents=True)
    csv_path = held / "wildfire.csv"
    csv_path.write_text("state,date,fires\nCA,2026-08-01,12\n", encoding="utf-8")
    monkeypatch.setenv("RESEARCH_PACKAGE_ROOT", str(tmp_path / "packages"))

    gateway = FakeGateway(
        tmp_path,
        {
            "wildfire": _dataset("wildfire", local_path="data_lake/held/wildfire.csv"),
            "polling": _dataset("polling", readiness="dry_run"),
        },
    )
    out = prepare_library_package(
        gateway,
        research_need="US polling and forest fire evidence",
        dataset_ids=["wildfire", "polling", "missing"],
    )

    assert out["status"] == "ready"
    assert out["sufficiency_claim"] is False
    assert out["data_file_count"] == 1
    assert [row["dataset_id"] for row in out["included"]] == ["wildfire"]
    assert [row["dataset_id"] for row in out["metadata_only"]] == ["polling"]
    assert out["metadata_only"][0]["reason"] == "no_exportable_local_file"
    assert out["excluded"] == [{"dataset_id": "missing", "reason": "not_registered", "detail": "'missing'"}]

    package_dir = tmp_path / "packages" / out["package_id"]
    archive = package_dir / out["archive"]["name"]
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert "README.md" in names
        assert "manifest.json" in names
        assert "data/wildfire/wildfire.csv" in names
        assert "metadata/wildfire.json" in names
        assert "metadata/polling.json" in names
        assert "access/polling.json" in names
        assert not any(name.startswith("data/polling/") for name in names)
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["sufficiency_claim"] is False
        assert manifest["included"][0]["files"][0]["checksum"].startswith("sha256:")
        readme = zf.read("README.md").decode("utf-8")
        assert "Held does not mean downloadable" in readme
        assert "does not establish" in readme


def test_package_size_ceiling_is_explicit_not_misreported_as_missing_file(tmp_path, monkeypatch):
    from scripts.research_data_mcp.library_packages import prepare_library_package

    held = tmp_path / "data_lake/held"
    held.mkdir(parents=True)
    path = held / "large.csv"
    path.write_bytes(b"x" * 128)
    monkeypatch.setenv("RESEARCH_PACKAGE_ROOT", str(tmp_path / "packages"))
    gateway = FakeGateway(tmp_path, {"large": _dataset("large", local_path="data_lake/held/large.csv")})

    out = prepare_library_package(gateway, dataset_ids=["large"], max_total_bytes=64)
    assert out["status"] == "metadata_only"
    assert out["data_file_count"] == 0
    assert out["metadata_only"][0]["reason"] == "package_size_limit"
    assert out["archive"]["bytes"] > 0


def test_package_rejects_escape_paths_even_when_the_file_exists(tmp_path, monkeypatch):
    from scripts.research_data_mcp.library_packages import prepare_library_package

    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "secret.csv"
    outside.write_text("secret\n1\n", encoding="utf-8")
    monkeypatch.setenv("RESEARCH_PACKAGE_ROOT", str(tmp_path / "packages"))
    gateway = FakeGateway(repo, {"escape": _dataset("escape", local_path="../secret.csv")})

    out = prepare_library_package(gateway, dataset_ids=["escape"])
    assert out["status"] == "metadata_only"
    assert out["metadata_only"][0]["reason"] == "unverified_export_path"
    package_dir = tmp_path / "packages" / out["package_id"]
    with zipfile.ZipFile(package_dir / out["archive"]["name"]) as zf:
        assert not any(name.startswith("data/") for name in zf.namelist())


def test_identical_request_reuses_exact_archive_and_file_change_creates_new_identity(tmp_path, monkeypatch):
    from scripts.research_data_mcp.library_packages import prepare_library_package

    held = tmp_path / "data_lake/held"
    held.mkdir(parents=True)
    path = held / "polls.csv"
    path.write_text("date,pct\n2026-08-01,51\n", encoding="utf-8")
    monkeypatch.setenv("RESEARCH_PACKAGE_ROOT", str(tmp_path / "packages"))
    gateway = FakeGateway(tmp_path, {"polls": _dataset("polls", local_path="data_lake/held/polls.csv")})

    first = prepare_library_package(gateway, research_need="US polling", dataset_ids=["polls"])
    second = prepare_library_package(gateway, research_need="US polling", dataset_ids=["polls"])
    assert first["reused"] is False
    assert second["reused"] is True
    assert second["package_id"] == first["package_id"]
    assert second["archive"]["checksum"] == first["archive"]["checksum"]
    assert second["manifest"]["prepared_at"] == first["manifest"]["prepared_at"]

    path.write_text("date,pct\n2026-08-01,52\n", encoding="utf-8")
    changed = prepare_library_package(gateway, research_need="US polling", dataset_ids=["polls"])
    assert changed["package_id"] != first["package_id"]
    assert changed["reused"] is False


def test_package_lookup_rejects_traversal_and_returns_durable_download_record(tmp_path, monkeypatch):
    from scripts.research_data_mcp.library_packages import get_library_package, prepare_library_package

    held = tmp_path / "data_lake/held"
    held.mkdir(parents=True)
    path = held / "polls.csv"
    path.write_text("date,pct\n2026-08-01,51\n", encoding="utf-8")
    monkeypatch.setenv("RESEARCH_PACKAGE_ROOT", str(tmp_path / "packages"))
    gateway = FakeGateway(tmp_path, {"polls": _dataset("polls", local_path="data_lake/held/polls.csv")})
    made = prepare_library_package(gateway, dataset_ids=["polls"])

    fetched = get_library_package(tmp_path, made["package_id"])
    assert fetched["package_id"] == made["package_id"]
    assert fetched["download_path"].endswith("/download")
    assert Path(fetched["_archive_file"]).is_file()

    with pytest.raises(KeyError):
        get_library_package(tmp_path, "../escape")
