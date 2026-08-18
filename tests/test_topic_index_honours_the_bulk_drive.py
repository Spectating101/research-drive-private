#!/usr/bin/env python3
"""Two resolvers for one index means the good one is invisible.

topic_index_paths.topic_index_root() honours DATACITE_TOPIC_INDEX_ON_BULK and finds the
external drive. build_curated_topic_fts hardcoded repo_root for both its output and its
JSONL sources, and datacite_vault_search reads through the builder — so the flag had no
effect, the builder rebuilt from a 40KB stub, and the desk searched 40 rows while a
134MB / 60,571-row index sat on the drive beside 96MB of sources.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.data_catalog import build_curated_topic_fts as bld
from scripts.data_catalog.topic_index_paths import topic_index_root


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("DATACITE_TOPIC_INDEX_ON_BULK", raising=False)
    monkeypatch.delenv("DATACITE_TOPIC_INDEX_ROOT", raising=False)
    monkeypatch.delenv("RESEARCH_BULK_ROOT", raising=False)


def _fake_bulk(tmp_path: Path) -> Path:
    """A bulk root shaped like the real one: marker file plus data_lake."""
    root = tmp_path / "bulk" / "sharpe-renaissance"
    (root / "data_lake/dataset_catalog/_topic_index").mkdir(parents=True)
    (root / ".sharpe_research_bulk").write_text("", encoding="utf-8")
    return root


def test_output_path_follows_the_same_resolver_as_the_reader(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "data_lake/dataset_catalog").mkdir(parents=True)
    bulk = _fake_bulk(tmp_path)
    monkeypatch.setenv("RESEARCH_BULK_ROOT", str(bulk))
    monkeypatch.setenv("DATACITE_TOPIC_INDEX_ON_BULK", "1")

    expected = topic_index_root(repo) / "curated.sqlite3"
    assert bld.topic_index_path(repo) == expected, (
        f"builder writes {bld.topic_index_path(repo)} while the reader looks in {expected}"
    )
    assert "bulk" in str(bld.topic_index_path(repo))


def test_sources_are_read_from_the_bulk_drive_too(tmp_path, monkeypatch):
    """A stub curated_live on the NVMe must not be preferred over 96MB on the drive."""
    repo = tmp_path / "repo"
    (repo / "data_lake/dataset_catalog/curated_live").mkdir(parents=True)
    bulk = _fake_bulk(tmp_path)
    (bulk / "data_lake/dataset_catalog/curated").mkdir(parents=True)
    monkeypatch.setenv("RESEARCH_BULK_ROOT", str(bulk))
    monkeypatch.setenv("DATACITE_TOPIC_INDEX_ON_BULK", "1")

    root = bld.curated_source_root(repo)
    assert str(bulk) in str(root), f"sources resolved to {root}"


def test_without_the_flag_nothing_moves(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "data_lake/dataset_catalog").mkdir(parents=True)
    assert bld.topic_index_path(repo) == (
        repo.resolve() / "data_lake/dataset_catalog/_topic_index/curated.sqlite3"
    )
    assert bld.curated_source_root(repo) == repo.resolve() / "data_lake/dataset_catalog"
