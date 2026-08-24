"""Desk runtime — activity tracking, index prep, fleet yield."""

from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.research_data_mcp.desk_runtime import (
    desk_is_active,
    fleet_should_yield,
    prepare_desk_indexes,
    runtime_status,
    touch_desk_activity,
)


def test_touch_desk_activity_marks_active(tmp_path: Path):
    touch_desk_activity(tmp_path, route="/library/search")
    assert desk_is_active(tmp_path) is True
    doc = json.loads((tmp_path / "data_lake/procurement_memory/desk_active.json").read_text())
    assert doc["route"] == "/library/search"


def test_desk_inactive_after_window(tmp_path: Path, monkeypatch):
    touch_desk_activity(tmp_path)
    path = tmp_path / "data_lake/procurement_memory/desk_active.json"
    doc = json.loads(path.read_text())
    doc["last_touch"] = time.time() - 400
    path.write_text(json.dumps(doc))
    monkeypatch.setenv("DESK_ACTIVE_WINDOW_SECONDS", "180")
    assert desk_is_active(tmp_path) is False


def test_fleet_should_yield_when_desk_active(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DESK_FLEET_YIELD", "1")
    touch_desk_activity(tmp_path)
    assert fleet_should_yield(tmp_path) is True


def test_fleet_yield_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DESK_FLEET_YIELD", "0")
    touch_desk_activity(tmp_path)
    assert fleet_should_yield(tmp_path) is False


def test_prepare_desk_indexes_sets_ready(tmp_path: Path, monkeypatch):
    curated = tmp_path / "data_lake/dataset_catalog/index_v3/curated_topic_fts.sqlite3"
    curated.parent.mkdir(parents=True, exist_ok=True)
    curated.write_bytes(b"sqlite")

    monkeypatch.setattr(
        "scripts.data_catalog.build_curated_topic_fts.ensure_curated_topic_fts",
        lambda _repo: curated,
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.datacite_vault_search.set_prepared_curated_index",
        lambda _path: None,
    )
    monkeypatch.setattr(
        "scripts.data_catalog.build_scrape_snippet_fts.snippet_index_path",
        lambda _repo: tmp_path / "missing_scrape.sqlite3",
    )

    meta = prepare_desk_indexes(tmp_path)
    assert meta["ready"] is True
    assert meta["interactive_vault"] == "nvme_only"
    status = runtime_status(tmp_path)
    assert status["indexes"]["ready"] is True
