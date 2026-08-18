#!/usr/bin/env python3
"""The index must compound, not fork.

CollectionFlywheel appends every externally discovered dataset to
curated_live/curated_dataset_index.jsonl, which is what makes the catalogue grow with use.
curated_live_dir() hardcoded repo_root while the reader resolves through
topic_index_root(), so after the bulk mount was renamed the flywheel kept appending to a
fresh empty file on the NVMe: 40 rows accumulated there while 11,466 sat on the drive, and
search read the drive. Growth and reads pointing at different files is not a slow index,
it is two indexes.
"""

from __future__ import annotations

import pytest

from scripts.data_catalog.topic_index_paths import topic_index_root
from scripts.research_data_mcp.collection_flywheel import CollectionFlywheel


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in ("DATACITE_TOPIC_INDEX_ON_BULK", "DATACITE_TOPIC_INDEX_ROOT", "RESEARCH_BULK_ROOT"):
        monkeypatch.delenv(var, raising=False)


def _bulk(tmp_path):
    root = tmp_path / "bulk" / "sharpe-renaissance"
    (root / "data_lake/dataset_catalog/curated_live").mkdir(parents=True)
    (root / ".sharpe_research_bulk").write_text("", encoding="utf-8")
    return root


def _wheel(tmp_path):
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True, exist_ok=True)
    reg = repo / "config/research_query_registry.json"
    reg.write_text('{"datasets": []}', encoding="utf-8")
    return CollectionFlywheel(repo, reg)


def test_growth_lands_where_the_reader_looks(tmp_path, monkeypatch):
    bulk = _bulk(tmp_path)
    monkeypatch.setenv("RESEARCH_BULK_ROOT", str(bulk))
    monkeypatch.setenv("DATACITE_TOPIC_INDEX_ON_BULK", "1")
    wheel = _wheel(tmp_path)
    expected = topic_index_root(wheel.repo_root).parent / "curated_live"
    assert wheel.curated_live_dir() == expected, (
        f"flywheel writes {wheel.curated_live_dir()}, reader reads {expected}"
    )
    assert str(bulk) in str(wheel.curated_jsonl())
    assert str(bulk) in str(wheel.keys_path())


def test_without_the_flag_it_stays_on_the_repo(tmp_path):
    wheel = _wheel(tmp_path)
    assert wheel.curated_live_dir() == wheel.repo_root / "data_lake/dataset_catalog/curated_live"


def test_the_keys_file_travels_with_the_jsonl(tmp_path, monkeypatch):
    """Split key state would let the same discovery be appended twice."""
    bulk = _bulk(tmp_path)
    monkeypatch.setenv("RESEARCH_BULK_ROOT", str(bulk))
    monkeypatch.setenv("DATACITE_TOPIC_INDEX_ON_BULK", "1")
    wheel = _wheel(tmp_path)
    assert wheel.keys_path().parent == wheel.curated_jsonl().parent
