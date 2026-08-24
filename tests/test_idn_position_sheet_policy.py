from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alpha" / "scripts"))

from idn_retail_gdelt_lib import (  # noqa: E402
    cap_single_name_weights,
    filter_retail_symbols,
)


def test_cap_single_name_weights_moves_excess_to_cash():
    w = {"JSMR.JK": 0.68, "BBCA.JK": 0.06, "CASH": 0.08}
    why = {"JSMR.JK": "retail", "BBCA.JK": "bank", "CASH": "base"}
    out_w, out_why, meta = cap_single_name_weights(w, why, max_weight=0.25)
    assert out_w["JSMR.JK"] == pytest.approx(0.25)
    assert out_w["BBCA.JK"] == pytest.approx(0.06)
    assert out_w["CASH"] == pytest.approx(0.08 + 0.43)
    assert meta["capped"][0]["symbol"] == "JSMR.JK"


def test_filter_retail_symbols_prefer_ranks_validated_banks():
    scores = {
        "JSMR.JK": {"available": True, "mention_rows_sum": 5, "score": 5.0},
        "BBCA.JK": {"available": True, "mention_rows_sum": 2, "score": 2.0},
    }
    out, report = filter_retail_symbols(["JSMR.JK", "BBCA.JK"], scores, mode="prefer")
    assert out[0] == "BBCA.JK"
    assert report["action"] == "prefer_ranked"


def test_filter_retail_symbols_require_fail_open_when_empty():
    scores = {
        "JSMR.JK": {"available": True, "mention_rows_sum": 0, "active_days": 0, "score": 0.0},
    }
    out, report = filter_retail_symbols(["JSMR.JK"], scores, mode="require", min_mention_rows=1)
    assert out == ["JSMR.JK"]
    assert report["action"] == "fail_open_require_empty"


def test_filter_bandar_require_fail_open_when_no_confirmed():
    scores = {
        "JSMR.JK": {"available": True, "mention_rows_sum": 5, "score": 5.0},
        "BBCA.JK": {"available": True, "mention_rows_sum": 2, "score": 2.0},
    }
    bandar = {
        "JSMR.JK": {"confirmed": False, "rejected": True, "score": -2.0},
        "BBCA.JK": {"confirmed": False, "rejected": False, "score": 0.0},
    }
    out, report = filter_retail_symbols(
        ["JSMR.JK", "BBCA.JK"],
        scores,
        mode="off",
        bandar_scores=bandar,
        bandar_mode="require",
    )
    assert out == ["BBCA.JK", "JSMR.JK"]
    assert report["bandar_action"] == "fail_open_bandar_require_empty"


def test_filter_bandar_prefer_ranks_confirmed_first():
    scores = {
        "JSMR.JK": {"available": True, "mention_rows_sum": 10, "score": 10.0},
        "BBCA.JK": {"available": True, "mention_rows_sum": 1, "score": 1.0},
    }
    bandar = {
        "JSMR.JK": {"confirmed": False, "rejected": False, "score": 0.0},
        "BBCA.JK": {"confirmed": True, "rejected": False, "score": 2.5},
    }
    out, _ = filter_retail_symbols(
        ["JSMR.JK", "BBCA.JK"],
        scores,
        mode="off",
        bandar_scores=bandar,
        bandar_mode="prefer",
    )
    assert out[0] == "BBCA.JK"


def test_entity_cache_builds_idn_subset(tmp_path, monkeypatch):
    import pandas as pd
    from idn_panel_cache import refresh_entity_idn_cache, load_entity_idn_daily

    source = tmp_path / "entity.parquet"
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-01"]),
            "yahoo_symbol": ["BBCA.JK", "AAPL"],
            "entity_mention_rows": [3, 99],
        }
    )
    df.to_parquet(source, index=False)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_path = cache_dir / "gdelt_entity_daily_idn.parquet"

    import idn_panel_cache as ipc

    monkeypatch.setattr(ipc, "ENTITY_SOURCE", source)
    monkeypatch.setattr(ipc, "ENTITY_IDN_CACHE", cache_path)
    monkeypatch.setattr(ipc, "CACHE_DIR", cache_dir)

    refresh_entity_idn_cache(force=True)
    out = load_entity_idn_daily(force_refresh=False)
    assert list(out["yahoo_symbol"]) == ["BBCA.JK"]
    assert int(out["entity_mention_rows"].iloc[0]) == 3


def test_platform_integration_idn_retail_policy():
    cfg = json.loads((REPO / "alpha" / "config" / "platform_integration.json").read_text(encoding="utf-8"))
    idn = cfg["idn_sleeve"]
    assert idn["max_single_name_weight"] == 0.25
    assert idn["gdelt_retail_filter"] == "prefer"
    assert idn["bandar_confirm"] == "prefer"
    assert idn["max_tilt_symbols"] == 12
    assert idn["signal_universe"] == "tradable"
    assert idn["operator_brief"] is False


def test_unified_cycle_idn_sheet_cmd_includes_retail_policy_flags():
    import subprocess

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "alpha" / "scripts" / "run_unified_platform_cycle.py"),
            "--dry-run",
            "--skip-fetch",
            "--skip-global",
            "--skip-news",
            "--skip-audit",
            "--force-idn-sheet",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": f"{REPO / 'kernel'}:{REPO / 'alpha'}:{REPO}"},
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    manifest = json.loads((REPO / "backtests/outputs/platform/latest.json").read_text(encoding="utf-8"))
    step = next(s for s in manifest["steps"] if s["label"] == "idn_weekly_sheet")
    cmd = " ".join(step["cmd"])
    assert "--max-single-name-weight" in cmd and "0.25" in cmd
    assert "--gdelt-retail-filter" in cmd and "prefer" in cmd
    assert "--bandar-confirm" in cmd and "prefer" in cmd
    assert "--max-tilt-symbols" in cmd and "12" in cmd
    assert "--signal-universe" in cmd and "tradable" in cmd
