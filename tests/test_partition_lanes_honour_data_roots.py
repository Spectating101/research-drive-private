#!/usr/bin/env python3
"""A partition whose bytes live outside the served checkout is still held.

`_should_surface` keeps a vault drawer only when it has real local bytes, which is
correct — empty vendor folders must not be sold as desk capabilities. But
`_local_storage_path` resolved `legacy_local_path` against repo_root alone, and 17
of 25 configured partitions store their bytes under RESEARCH_DATA_ROOTS instead.
Those read as zero-byte and were dropped, so /library/partitions reported 2 lanes
against a registry holding 168 datasets and Library rendered an empty shelf list.

Same defect as the query engine resolving only the root it settled on: the bytes
were never missing, the search order was.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.yzu_cluster.partition_lanes import _local_storage_path, partition_lanes


@pytest.fixture(autouse=True)
def _no_ambient_roots(monkeypatch):
    monkeypatch.delenv("RESEARCH_DATA_ROOTS", raising=False)


def _write_config(repo: Path, partitions: list[dict]) -> None:
    (repo / "config").mkdir(parents=True, exist_ok=True)
    (repo / "config/collection_partitions.json").write_text(
        json.dumps({"canonical_root": "gdrive:/x", "partitions": partitions}), encoding="utf-8"
    )


def test_bytes_under_a_configured_root_are_found(tmp_path, monkeypatch):
    repo = tmp_path / "checkout"
    data = tmp_path / "elsewhere"
    (data / "data_lake/news").mkdir(parents=True)
    (data / "data_lake/news/rows.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    _write_config(repo, [])

    part = {"id": "news.gdelt", "legacy_local_path": "data_lake/news"}
    assert _local_storage_path(repo, part).exists() is False

    monkeypatch.setenv("RESEARCH_DATA_ROOTS", str(data))
    found = _local_storage_path(repo, part)
    assert found is not None and found.exists(), "configured root was not searched"
    assert found == data / "data_lake/news"


def test_repo_root_still_wins_when_both_exist(tmp_path, monkeypatch):
    repo = tmp_path / "checkout"
    data = tmp_path / "elsewhere"
    for base in (repo, data):
        (base / "data_lake/news").mkdir(parents=True)
        (base / "data_lake/news/rows.csv").write_text("a\n1\n", encoding="utf-8")
    _write_config(repo, [])
    monkeypatch.setenv("RESEARCH_DATA_ROOTS", str(data))

    part = {"id": "news.gdelt", "legacy_local_path": "data_lake/news"}
    assert _local_storage_path(repo, part) == repo / "data_lake/news"


def test_a_held_partition_surfaces_as_a_lane(tmp_path, monkeypatch):
    """The end the researcher sees: the drawer appears in Library."""
    repo = tmp_path / "checkout"
    data = tmp_path / "elsewhere"
    (data / "data_lake/news").mkdir(parents=True)
    (data / "data_lake/news/rows.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    _write_config(
        repo,
        [{
            "id": "news.gdelt",
            "domain": "news",
            "status": "held",
            "legacy_local_path": "data_lake/news",
            "professor_label": "Asia news shocks",
        }],
    )

    assert partition_lanes(repo) == [], "a drawer with no reachable bytes must not surface"

    monkeypatch.setenv("RESEARCH_DATA_ROOTS", str(data))
    lanes = partition_lanes(repo)
    assert [l.get("partition_id") for l in lanes] == ["news.gdelt"]


def test_an_absent_partition_still_does_not_surface(tmp_path, monkeypatch):
    """Widening the search must not turn a missing drawer into a held one."""
    repo = tmp_path / "checkout"
    data = tmp_path / "elsewhere"
    data.mkdir(parents=True)
    _write_config(
        repo,
        [{"id": "markets.void", "domain": "markets", "status": "held",
          "legacy_local_path": "data_lake/nothing_here"}],
    )
    monkeypatch.setenv("RESEARCH_DATA_ROOTS", str(data))
    assert partition_lanes(repo) == []


def test_shelves_fall_back_to_the_declared_domain(tmp_path):
    """professor_nav has never been populated in any config, so shelf-first nav
    rendered zero shelves over 25 partitions. `domain` is the taxonomy the
    partitions already declare — derive from it rather than ship an empty rail."""
    from scripts.yzu_cluster.partition_lanes import professor_shelves

    repo = tmp_path / "checkout"
    _write_config(
        repo,
        [
            {"id": "news.gdelt", "domain": "news", "legacy_local_path": "a"},
            {"id": "news.expanded", "domain": "news", "legacy_local_path": "b"},
            {"id": "markets.equities", "domain": "markets", "legacy_local_path": "c"},
        ],
    )
    shelves = professor_shelves(repo)
    assert [s["id"] for s in shelves] == ["markets", "news"]
    assert [s["label"] for s in shelves] == ["Markets", "News"]
    by_id = {s["id"]: s for s in shelves}
    assert by_id["news"]["partition_ids"] == ["news.gdelt", "news.expanded"]


def test_an_authored_nav_still_wins_over_the_fallback(tmp_path):
    from scripts.yzu_cluster.partition_lanes import professor_shelves

    repo = tmp_path / "checkout"
    (repo / "config").mkdir(parents=True, exist_ok=True)
    (repo / "config/collection_partitions.json").write_text(
        json.dumps({
            "partitions": [{"id": "news.gdelt", "domain": "news", "legacy_local_path": "a"}],
            "professor_nav": {"shelves": [
                {"id": "news_events", "label": "News & events", "sort": 10,
                 "partition_ids": ["news.gdelt"]}
            ]},
        }),
        encoding="utf-8",
    )
    shelves = professor_shelves(repo)
    assert [s["id"] for s in shelves] == ["news_events"]


def test_lanes_are_attributed_to_the_derived_shelves(tmp_path, monkeypatch):
    """Deriving shelves is only half the nav: a lane still needs its shelf_id, or
    every shelf renders a count of zero over lanes that plainly exist."""
    from scripts.yzu_cluster.partition_lanes import partition_lanes, professor_shelves

    repo = tmp_path / "checkout"
    data = tmp_path / "elsewhere"
    for name in ("news", "markets"):
        (data / f"data_lake/{name}").mkdir(parents=True)
        (data / f"data_lake/{name}/rows.csv").write_text("a\n1\n", encoding="utf-8")
    _write_config(
        repo,
        [
            {"id": "news.gdelt", "domain": "news", "status": "held",
             "legacy_local_path": "data_lake/news"},
            {"id": "markets.equities", "domain": "markets", "status": "held",
             "legacy_local_path": "data_lake/markets"},
        ],
    )
    monkeypatch.setenv("RESEARCH_DATA_ROOTS", str(data))

    lanes = partition_lanes(repo)
    assert {l["partition_id"]: l.get("shelf_id") for l in lanes} == {
        "news.gdelt": "news",
        "markets.equities": "markets",
    }
    shelf_ids = {s["id"] for s in professor_shelves(repo)}
    assert {l.get("shelf_id") for l in lanes} <= shelf_ids, "a lane must land on a real shelf"
