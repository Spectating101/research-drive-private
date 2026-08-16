"""A registry entry is a claim; only opening the file settles it."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.research_data_mcp.synthesis.integrity_sweep import check_dataset, sweep


def _repo(tmp_path: Path, datasets: list[dict]) -> Path:
    (tmp_path / "drive/config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "drive/config/research_query_registry.json").write_text(
        json.dumps({"datasets": datasets}), encoding="utf-8")
    return tmp_path


def test_a_readable_dataset_reports_its_real_shape(tmp_path):
    repo = _repo(tmp_path, [{"dataset_id": "good", "local_path": "data/good.parquet"}])
    pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}).to_parquet(repo / "data/good.parquet")
    out = check_dataset(repo, {"dataset_id": "good", "local_path": "data/good.parquet"})
    assert out["status"] == "readable"
    assert out["rows"] == 3
    assert out["columns"] == 2
    assert out["bytes"] > 0


def test_a_corrupt_parquet_with_valid_magic_is_caught(tmp_path):
    """The real failure: correct PAR1 at both ends, undeserialisable footer.

    The footer is the last 8 bytes (length + magic) preceded by the thrift
    metadata. Damage there is what us_sp500_yfinance_daily has. Damage in the
    padding between pages is not detectable by reading and is not claimed to be.
    """
    repo = _repo(tmp_path, [{"dataset_id": "bad", "local_path": "data/bad.parquet"}])
    path = repo / "data/bad.parquet"
    pd.DataFrame({"a": range(200)}).to_parquet(path)
    raw = bytearray(path.read_bytes())
    footer_len = int.from_bytes(raw[-8:-4], "little")
    start = len(raw) - 8 - footer_len
    raw[start:start + footer_len] = b"\x00" * footer_len
    path.write_bytes(bytes(raw))
    assert bytes(raw[:4]) == b"PAR1" and bytes(raw[-4:]) == b"PAR1"

    out = check_dataset(repo, {"dataset_id": "bad", "local_path": "data/bad.parquet"})
    assert out["status"] == "unreadable"
    assert out["detail"]


def test_a_zero_byte_file_is_not_called_readable(tmp_path):
    repo = _repo(tmp_path, [{"dataset_id": "hollow", "local_path": "data/hollow.csv"}])
    (repo / "data/hollow.csv").write_bytes(b"")
    out = check_dataset(repo, {"dataset_id": "hollow", "local_path": "data/hollow.csv"})
    assert out["status"] == "empty"


def test_a_file_that_parses_to_no_rows_is_reported(tmp_path):
    """Two registered scrapes do exactly this — headers, no data."""
    repo = _repo(tmp_path, [{"dataset_id": "headers", "local_path": "data/headers.csv"}])
    (repo / "data/headers.csv").write_text("a,b\n", encoding="utf-8")
    out = check_dataset(repo, {"dataset_id": "headers", "local_path": "data/headers.csv"})
    assert out["status"] == "empty"
    assert "zero rows" in out["detail"]


def test_a_missing_file_is_absent_not_corrupt(tmp_path):
    repo = _repo(tmp_path, [{"dataset_id": "gone", "local_path": "data/gone.parquet"}])
    out = check_dataset(repo, {"dataset_id": "gone", "local_path": "data/gone.parquet"})
    assert out["status"] == "absent"
    assert out["detail"]


def test_the_sweep_counts_every_registered_entry(tmp_path):
    repo = _repo(tmp_path, [
        {"dataset_id": "good", "local_path": "data/good.parquet"},
        {"dataset_id": "gone", "local_path": "data/gone.parquet"},
        {"dataset_id": "hollow", "local_path": "data/hollow.csv"},
    ])
    pd.DataFrame({"a": [1, 2]}).to_parquet(repo / "data/good.parquet")
    (repo / "data/hollow.csv").write_bytes(b"")

    report = sweep(repo)
    assert report["registered"] == 3
    assert report["counts"]["readable"] == 1
    assert report["counts"]["absent"] == 1
    assert report["counts"]["empty"] == 1
    assert report["readable_rows"] == 2
    assert {r["dataset_id"] for r in report["corrupt"]} == {"hollow"}


def test_the_sweep_can_be_limited_to_named_datasets(tmp_path):
    repo = _repo(tmp_path, [
        {"dataset_id": "good", "local_path": "data/good.parquet"},
        {"dataset_id": "gone", "local_path": "data/gone.parquet"},
    ])
    pd.DataFrame({"a": [1]}).to_parquet(repo / "data/good.parquet")
    assert sweep(repo, only=["good"])["registered"] == 1


def test_the_sweep_never_edits_the_files_it_reads(tmp_path):
    repo = _repo(tmp_path, [{"dataset_id": "good", "local_path": "data/good.parquet"}])
    path = repo / "data/good.parquet"
    pd.DataFrame({"a": [1, 2, 3]}).to_parquet(path)
    before = path.read_bytes()
    sweep(repo, deep=True)
    assert path.read_bytes() == before
