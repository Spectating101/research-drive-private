"""High-value desk additions — registry, CRSP manifest, macro panel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_high_value_backlog_config():
    path = REPO / "config/desk_high_value_additions.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    ids = {i["id"] for i in doc["items"]}
    assert "crsp_moveit_manifest" in ids
    assert "public_macro_ff_panel" in ids


def test_registry_has_crsp_and_macro_cards():
    reg = json.loads((REPO / "config/research_query_registry.json").read_text(encoding="utf-8"))
    ids = {d["dataset_id"] for d in reg["datasets"]}
    for did in (
        "crsp_us_stock_daily_ciz",
        "compustat_na_fundamentals_annual",
        "public_macro_ff_factors_daily",
        "refinitiv_entity_market_spine_expanded",
    ):
        assert did in ids


def test_partitions_crsp_compustat():
    parts = json.loads((REPO / "config/collection_partitions.json").read_text(encoding="utf-8"))
    pids = {p["id"] for p in parts["partitions"]}
    assert "reference.crsp-moveit" in pids
    assert "reference.compustat-capitaliq" in pids


def test_queue_has_crsp_manifest_task():
    q = json.loads((REPO / "config/data_collection_queue.json").read_text(encoding="utf-8"))
    ids = {t["id"] for t in q["tasks"]}
    assert "crsp_moveit_manifest" in ids
    assert "crsp_moveit_sync_priority" in ids
    task = next(t for t in q["tasks"] if t["id"] == "crsp_moveit_manifest")
    assert task["enabled"] is True
