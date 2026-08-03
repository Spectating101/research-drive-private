from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alpha"))
sys.path.insert(0, str(REPO / "kernel"))

from src.research.drive_fuel import inventory_fuel, load_fuel_manifest


def test_fuel_manifest_loads():
    m = load_fuel_manifest(REPO)
    assert m.get("version") == 1
    ids = [d["dataset_id"] for d in m["datasets"]]
    assert "cross_asset_fused_primary_panel" in ids
    assert "ticker_week_entity_market_panel" in ids


def test_inventory_fuel_reports_fused_ready_or_stale():
    report = inventory_fuel(REPO, probe_http=False)
    assert report["n_datasets"] >= 8
    by_id = {r["dataset_id"]: r for r in report["datasets"]}
    fused = by_id["cross_asset_fused_primary_panel"]
    assert fused["status"] in {"ready", "stale"}
    assert fused["resolved_path"]
    assert "supply_asks" in report
