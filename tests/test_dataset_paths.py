"""Resolve the bytes a registry entry names, or say precisely why not."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis.dataset_paths import (
    data_roots,
    resolve_dataset_file,
)


def _parquet(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"a": [1]}).to_parquet(path)
    return path


def test_local_path_file_resolves(tmp_path):
    _parquet(tmp_path / "data/x.parquet")
    found, reason = resolve_dataset_file(tmp_path, {"dataset_id": "d", "local_path": "data/x.parquet"})
    assert found and found.name == "x.parquet" and reason is None


def test_run_stamped_local_file_resolves(tmp_path):
    _parquet(tmp_path / "data/lake/run7/processed/sec.parquet")
    found, _ = resolve_dataset_file(tmp_path, {
        "dataset_id": "sec", "local_root": "data/lake",
        "default_run_id": "run7", "local_file": "processed/sec.parquet"})
    assert found and "run7" in str(found)


def test_local_file_without_run_id_resolves(tmp_path):
    _parquet(tmp_path / "data/lake/processed/sec.parquet")
    found, _ = resolve_dataset_file(tmp_path, {
        "dataset_id": "sec", "local_root": "data/lake", "local_file": "processed/sec.parquet"})
    assert found is not None


def test_shared_root_returns_the_named_file_not_a_neighbour(tmp_path):
    """Ten datasets share refinitiv_backfill; the wrong file is worse than none."""
    _parquet(tmp_path / "data/lake/processed/aaa_first_alphabetically.parquet")
    _parquet(tmp_path / "data/lake/processed/security_master.parquet")
    found, _ = resolve_dataset_file(tmp_path, {
        "dataset_id": "sm", "local_root": "data/lake", "local_file": "processed/security_master.parquet"})
    assert found.name == "security_master.parquet"


def test_ambiguous_directory_is_refused_by_name(tmp_path):
    _parquet(tmp_path / "data/lake/a.parquet")
    _parquet(tmp_path / "data/lake/b.parquet")
    found, reason = resolve_dataset_file(tmp_path, {"dataset_id": "d", "local_root": "data/lake"})
    assert found is None
    assert "refusing to guess" in reason and "2" in reason


def test_single_file_directory_is_unambiguous(tmp_path):
    _parquet(tmp_path / "data/lake/only.parquet")
    found, _ = resolve_dataset_file(tmp_path, {"dataset_id": "d", "local_root": "data/lake"})
    assert found and found.name == "only.parquet"


def test_data_outside_the_repo_resolves_via_configured_roots(tmp_path):
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    _parquet(elsewhere / "data_lake/set/f.parquet")
    src = {"dataset_id": "d", "local_root": "data_lake/set", "local_file": "f.parquet"}
    assert resolve_dataset_file(repo, src)[0] is None
    found, _ = resolve_dataset_file(repo, src, roots=data_roots(repo, [str(elsewhere)]))
    assert found is not None


def test_missing_root_names_the_roots_it_searched(tmp_path):
    found, reason = resolve_dataset_file(tmp_path, {"dataset_id": "d", "local_root": "nope/here"})
    assert found is None
    assert "not under any data root" in reason
    assert "RESEARCH_DATA_ROOTS" in reason


def test_named_file_absent_is_distinct_from_missing_root(tmp_path):
    (tmp_path / "data/lake").mkdir(parents=True)
    found, reason = resolve_dataset_file(tmp_path, {
        "dataset_id": "d", "local_root": "data/lake", "local_file": "gone.parquet"})
    assert found is None
    assert "does not contain gone.parquet" in reason


def test_no_address_declared_is_its_own_reason(tmp_path):
    found, reason = resolve_dataset_file(tmp_path, {"dataset_id": "d"})
    assert found is None
    assert "declares no local_path or local_root" in reason


def test_repo_root_wins_over_configured_roots(tmp_path):
    repo = tmp_path / "repo"
    other = tmp_path / "other"
    _parquet(repo / "data/x.parquet")
    _parquet(other / "data/x.parquet")
    found, _ = resolve_dataset_file(repo, {"dataset_id": "d", "local_path": "data/x.parquet"},
                                    roots=data_roots(repo, [str(other)]))
    assert str(found).startswith(str(repo))


def test_env_unset_keeps_prior_behaviour(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEARCH_DATA_ROOTS", raising=False)
    roots = data_roots(tmp_path)
    assert all(str(r).startswith(str(tmp_path)) for r in roots)
