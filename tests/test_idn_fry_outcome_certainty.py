"""Tests for fry outcome certainty and ARA alert sleeve."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alpha" / "scripts"))

from idn_fry_ara_alert_lib import classify_ara_pop_event, scan_ara_pop_alerts  # noqa: E402
from idn_fry_outcome_certainty_lib import _outcome_block, build_outcome_certainty_report  # noqa: E402

CERT_JSON = REPO / "data_lake/research_panels/idn_fry_episode/fry_outcome_certainty_report.json"


def test_classify_ara_limit():
    out = classify_ara_pop_event({"return_1d": 0.25, "is_ara_day": 1, "bandar_lite_label": "chase_into_spike"})
    assert out["is_ara_pop"] is True
    assert out["ara_class"] == "ara_limit_hit"


def test_classify_not_pop():
    out = classify_ara_pop_event({"return_1d": 0.02, "is_ara_day": 0})
    assert out["is_ara_pop"] is False


def test_scan_ara_alert_on_watched_symbol():
    panel = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-01", "2026-06-02", "2026-06-01", "2026-06-02"]),
            "yahoo_symbol": ["A.JK", "A.JK", "B.JK", "B.JK"],
            "name_type": ["fry"] * 4,
            "return_1d": [-0.09, 0.26, -0.02, 0.03],
            "return_5d": [-0.10, -0.10, -0.02, -0.02],
            "vol_ratio_20d": [2.0, 2.0, 1.2, 1.2],
            "bandar_lite_label": ["squeeze_from_drawdown"] * 4,
            "cs_move_pct_rank": [0.2, 0.99, 0.5, 0.5],
            "is_ara_day": [0, 1, 0, 0],
        }
    )
    alerts = scan_ara_pop_alerts(panel, as_of=pd.Timestamp("2026-06-02"), watch_symbols={"A.JK"})
    assert len(alerts) == 1
    assert alerts[0]["yahoo_symbol"] == "A.JK"
    assert alerts[0]["ara_class"] == "ara_limit_hit"


def test_outcome_block_synthetic_menu():
    sub = pd.DataFrame(
        {
            "outcome_class": ["pop_first"] * 3 + ["flat_noise"] * 5 + ["sink_only"] * 2,
            "cum_30d_pct": [8.0, 6.0, 12.0, 0.0, 1.0, -1.0, 2.0, 0.5, -12.0, -14.0],
            "cum_5d_pct": [0.0] * 10,
            "max_dd_from_trigger_pct": [-5.0] * 10,
            "pop_return_1d_pct": [15.0, 14.0, 16.0] + [None] * 7,
            "trigger_to_pop_days": [5, 7, 6] + [None] * 7,
        }
    )
    block = _outcome_block(sub)
    assert block["pop_any_rate_pct"] == 30.0
    assert block["non_pop_breakdown_pct"]["stagnant_flat"] == 50.0
    assert block["non_pop_breakdown_pct"]["sink_before_pop"] == 20.0


@pytest.mark.integration
def test_certainty_report_on_disk():
    if not CERT_JSON.exists():
        pytest.skip("run run_idn_fry_outcome_certainty.py first")
    rep = json.loads(CERT_JSON.read_text(encoding="utf-8"))
    t1 = rep["t1_deep_dd_vol"]
    nb = t1["non_pop_breakdown_pct"]
    assert t1["n"] >= 2000
    assert t1["pop_any_rate_pct"] >= 35
    assert nb["stagnant_flat"] >= 30
    assert nb["sink_before_pop"] + nb["grind_bleed"] <= 25
    assert rep["certainty_verdict"]["verdict"] in ("solid_watchlist_not_hold", "understood_with_caveats")
    med = t1.get("median_non_pop_cum_30d_pct")
    assert med is not None and med > -10
