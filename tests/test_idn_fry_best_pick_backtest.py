"""Integration test for fry best-pick historical backtest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alpha" / "scripts"))

REPORT = REPO / "backtests/outputs/idn_fry_best_pick_backtest/latest.json"


@pytest.mark.integration
def test_best_pick_backtest_report_exists():
    if not REPORT.exists():
        from idn_fry_best_pick_backtest_lib import build_best_pick_backtest

        build_best_pick_backtest(top_k=3)
    rep = json.loads(REPORT.read_text(encoding="utf-8"))
    assert rep["meta"]["n_best_pick_trades"] >= 1000
    pick = rep["strategies"]["pick_trigger_hold_14d"]
    bench = rep["strategies"]["bench_all_t1_hold_14d"]
    assert pick["n"] < bench["n"]
    assert pick["pop_within_window_pct"] >= bench["pop_within_window_pct"] - 2
    assert rep["reliability"]["verdict"]


def test_simulate_skips_sink_incubation():
    import pandas as pd
    from idn_fry_best_pick_backtest_lib import _simulate

    panel = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=8, freq="B"),
            "close": [100, 99, 90, 91, 92, 93, 94, 95],
            "return_1d": [0.0, -0.01, -0.10, 0.01, 0.01, 0.01, 0.01, 0.01],
        }
    )
    paths = {"X.JK": panel}
    out = _simulate("X.JK", pd.Timestamp("2026-01-01"), paths, strategy="incubate_d3_hold_11d")
    assert out and out.get("skipped") and out.get("reason") == "sink_during_incubation"
