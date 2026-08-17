"""What the catalogue claims and what the storage holds must be compared both ways.

Acquisition and cataloguing kept separate books. 32 of 33 directories under
data_lake/procured had no registry row — SEC EDGAR filings and Taiwan exchange
feeds, correctly fetched, content-addressed and manifested, invisible to the desk.
Meanwhile 34 of 35 procured rows in the registry pointed at nothing. The registry
declared 35 slugs, the disk held 33, and the overlap was one.

Neither direction alone finds that. Checking registry-to-bytes finds the phantoms;
only walking the storage finds the orphans.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.research_data_mcp.synthesis.integrity_sweep import landings, reconcile


def _repo(tmp_path: Path, datasets: list[dict]) -> Path:
    (tmp_path / "drive/config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "drive/config/research_query_registry.json").write_text(
        json.dumps({"datasets": datasets}), encoding="utf-8")
    return tmp_path


def _land(repo: Path, slug: str, *, dataset_id: str | None = None, url: str = "https://example.org/x",
          payload: str = "a,b\n1,2\n") -> Path:
    """Write a landing the way the collector does: CURRENT.json plus a revision."""
    directory = repo / "data_lake/procured" / slug
    revision = directory / "revisions/rev_abc123"
    revision.mkdir(parents=True, exist_ok=True)
    (revision / "data.csv").write_text(payload, encoding="utf-8")
    (revision / "manifest.json").write_text(json.dumps({
        "manifest_id": f"collection_manifest_{slug}", "job_id": "abc123",
        "plan": {"job_type": "http_manifest", "url": url},
        "validation": {"ok": True, "file_count": 1, "total_bytes": len(payload)},
    }), encoding="utf-8")
    (directory / "CURRENT.json").write_text(json.dumps({
        "dataset_id": dataset_id or slug, "revision_id": "rev_abc123", "job_id": "abc123",
        "file_count": 1, "content_sha256": ["deadbeef"],
    }), encoding="utf-8")
    return directory


def test_a_landing_reports_what_it_says_about_itself(tmp_path):
    repo = _repo(tmp_path, [])
    _land(repo, "twse_feed", url="https://openapi.twse.com.tw/v1")
    found = landings(repo)
    assert len(found) == 1
    item = found[0]
    assert item["declared_dataset_id"] == "twse_feed"
    assert item["source_url"] == "https://openapi.twse.com.tw/v1"
    assert item["job_type"] == "http_manifest"
    assert item["validated"] is True
    assert item["revision"] == "rev_abc123"
    assert item["data_files"] == 1
    assert item["bytes"] > 0


def test_a_landing_with_no_registry_row_is_an_orphan(tmp_path):
    repo = _repo(tmp_path, [])
    _land(repo, "sec_edgar")
    report = reconcile(repo)
    assert [o["declared_dataset_id"] for o in report["orphans"]] == ["sec_edgar"]
    assert report["orphan_bytes"] > 0


def test_a_landing_the_registry_knows_about_is_not_an_orphan(tmp_path):
    """The landing declares its own id; that is what the comparison uses."""
    repo = _repo(tmp_path, [{"dataset_id": "sec_edgar", "local_path": "data_lake/procured/sec_edgar"}])
    _land(repo, "sec_edgar")
    assert reconcile(repo)["orphans"] == []


def test_the_declared_id_wins_over_the_directory_name(tmp_path):
    """A landing may sit in a differently-named directory; CURRENT.json is authoritative."""
    repo = _repo(tmp_path, [{"dataset_id": "real_id", "local_path": "data_lake/procured/odd_dir"}])
    _land(repo, "odd_dir", dataset_id="real_id")
    assert reconcile(repo)["orphans"] == []


def test_a_registry_row_with_nothing_behind_it_is_a_phantom(tmp_path):
    repo = _repo(tmp_path, [{"dataset_id": "never_landed",
                             "local_path": "data_lake/procured/never_landed"}])
    report = reconcile(repo)
    assert [p["dataset_id"] for p in report["phantoms"]] == ["never_landed"]


def test_both_failures_are_reported_from_one_pass(tmp_path):
    """The real registry had 34 phantoms and 32 orphans at the same time."""
    repo = _repo(tmp_path, [{"dataset_id": "phantom_row",
                             "local_path": "data_lake/procured/phantom_row"}])
    _land(repo, "orphan_landing")
    report = reconcile(repo)
    assert [p["dataset_id"] for p in report["phantoms"]] == ["phantom_row"]
    assert [o["declared_dataset_id"] for o in report["orphans"]] == ["orphan_landing"]


def test_an_empty_landing_is_not_reported_as_a_held_holding(tmp_path):
    """Two coingecko landings hold zero bytes; claiming them as findable data would
    repeat the mistake this check exists to catch."""
    repo = _repo(tmp_path, [])
    directory = repo / "data_lake/procured/empty_landing"
    directory.mkdir(parents=True)
    (directory / "CURRENT.json").write_text(json.dumps({"dataset_id": "empty_landing"}), encoding="utf-8")
    assert reconcile(repo)["orphans"] == []


def test_reconciliation_registers_nothing(tmp_path):
    """Deciding an orphan deserves a row is the operator's call, not this code's."""
    repo = _repo(tmp_path, [])
    _land(repo, "sec_edgar")
    before = (repo / "drive/config/research_query_registry.json").read_text()
    reconcile(repo)
    assert (repo / "drive/config/research_query_registry.json").read_text() == before


def test_a_repo_with_no_landing_directory_reports_none(tmp_path):
    assert landings(_repo(tmp_path, [])) == []


def test_a_directory_of_many_files_is_held_not_absent(tmp_path):
    """gdelt_asia_daily_country_panel holds 1,415 files and read as absent.

    The synthesis resolver refuses a directory with several data files because it
    must not guess which one a spec meant. That is right for "which file do I
    read" and wrong for "do we hold this", and conflating them hid 4,320 files.
    """
    from scripts.research_data_mcp.synthesis.integrity_sweep import check_dataset

    repo = _repo(tmp_path, [])
    panel = repo / "data_lake/news_shock/processed/run_a"
    panel.mkdir(parents=True)
    for name in ("panel.csv", "urls.csv", "extra.json"):
        (panel / name).write_text("a,b\n1,2\n", encoding="utf-8")

    out = check_dataset(repo, {"dataset_id": "panel", "local_path": "data_lake/news_shock/processed"})
    assert out["status"] == "held_not_single_file"
    assert out["data_files"] == 3
    assert out["bytes"] > 0
    assert "not addressable as a single file" in out["detail"]


def test_a_genuinely_missing_directory_is_still_absent(tmp_path):
    from scripts.research_data_mcp.synthesis.integrity_sweep import check_dataset

    repo = _repo(tmp_path, [])
    out = check_dataset(repo, {"dataset_id": "gone", "local_path": "data_lake/not_there"})
    assert out["status"] == "absent"


def test_an_empty_directory_is_absent_not_held(tmp_path):
    from scripts.research_data_mcp.synthesis.integrity_sweep import check_dataset

    repo = _repo(tmp_path, [])
    (repo / "data_lake/hollow").mkdir(parents=True)
    out = check_dataset(repo, {"dataset_id": "hollow", "local_path": "data_lake/hollow"})
    assert out["status"] == "absent"


def test_a_single_readable_file_is_still_readable(tmp_path):
    """The new branch must not swallow the ordinary case."""
    import pandas as pd

    from scripts.research_data_mcp.synthesis.integrity_sweep import check_dataset

    repo = _repo(tmp_path, [])
    (repo / "data").mkdir(parents=True)
    pd.DataFrame({"a": [1, 2, 3]}).to_parquet(repo / "data/one.parquet")
    out = check_dataset(repo, {"dataset_id": "one", "local_path": "data/one.parquet"})
    assert out["status"] == "readable"
    assert out["rows"] == 3
