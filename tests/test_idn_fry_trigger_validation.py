"""Robust validation tests for fry trigger → pop mechanics.

Uses on-disk research artifacts when present; unit tests run without full panel.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alpha" / "scripts"))

from idn_fry_robust_empirics_lib import (  # noqa: E402
    _apply_cut,
    cluster_bootstrap_rate,
    indicator_scan,
    proportion_inference,
    wilson_ci,
)

FRY_DIR = REPO / "data_lake/research_panels/idn_fry_episode"
ROBUST_REPORT = FRY_DIR / "robust_empirics_report.json"
BACKTEST_REPORT = REPO / "backtests/outputs/idn_fry_backtest/latest.json"
TRIGGER_PARQUET = FRY_DIR / "trigger_enriched.parquet"


@pytest.fixture(scope="module")
def robust_report() -> dict:
    if not ROBUST_REPORT.exists():
        pytest.skip("robust_empirics_report.json not built — run run_idn_fry_robust_empirics.py")
    return json.loads(ROBUST_REPORT.read_text())


@pytest.fixture(scope="module")
def backtest_report() -> dict:
    if not BACKTEST_REPORT.exists():
        pytest.skip("fry backtest report missing — run run_idn_fry_backtest.py")
    return json.loads(BACKTEST_REPORT.read_text())


def test_wilson_ci_sanity():
    lo, hi = wilson_ci(200, 1000)
    assert 0.17 < lo < 0.24
    assert 0.20 < hi < 0.27


def test_proportion_inference_empty():
    out = proportion_inference(pd.Series(dtype=float))
    assert out["sufficient"] is False


def test_apply_cut_missing_column_returns_false_mask():
    df = pd.DataFrame({"return_5d": [-0.1, 0.0]})
    mask = _apply_cut(df, {"col": "near_support_60d", "op": "eq", "thr": 1})
    assert not mask.any()


def test_indicator_scan_on_synthetic():
    n = 200
    df = pd.DataFrame(
        {
            "got_pop": [1] * 80 + [0] * 120,
            "return_5d": [-0.15] * 80 + [0.02] * 120,
            "vol_ratio_20d": [2.0] * n,
            "dd_60d": [-0.3] * n,
            "yahoo_symbol": ["A.JK"] * n,
        }
    )
    baseline = proportion_inference(df["got_pop"])
    rows = indicator_scan(df, baseline["rate_pct"] / 100.0)
    deep = next(r for r in rows if r["indicator_id"] == "return_5d_lte_neg12")
    assert deep["pop_rate_pct"] > baseline["rate_pct"]
    assert deep["n"] >= 30


def test_cluster_bootstrap_rate_synthetic():
    df = pd.DataFrame(
        {
            "got_pop": [1, 0, 1, 0, 1, 0] * 30,
            "yahoo_symbol": ["A.JK"] * 90 + ["B.JK"] * 90,
        }
    )
    out = cluster_bootstrap_rate(df, "got_pop")
    assert out["sufficient"]
    assert 0 < out["rate_pct"] < 100


@pytest.mark.integration
def test_robust_report_baseline_and_verdict(robust_report: dict):
    meta = robust_report["meta"]
    summary = robust_report["mechanism_summary"]
    assert meta["n_triggers"] >= 8000
    assert 20 <= meta["baseline_pop_rate_pct"] <= 28
    assert summary["robustness_verdict"] in (
        "robust_strong",
        "robust_moderate",
        "partially_robust_monitor",
        "fragile_insufficient",
    )


@pytest.mark.integration
def test_robust_fdr_indicators_beat_baseline(robust_report: dict):
    baseline = robust_report["meta"]["baseline_pop_rate_pct"]
    sig = [r for r in robust_report["indicator_scan"] if r.get("fdr_significant_5pct")]
    assert len(sig) >= 3
    top = max(sig, key=lambda r: r["pop_rate_pct"])
    assert top["pop_rate_pct"] > baseline + 10
    assert top["lift_vs_baseline"] >= 1.5
    assert top["indicator_id"] in ("return_5d_lte_neg12", "dd_60d_lte_neg30", "return_5d_lte_neg8")


@pytest.mark.integration
def test_robust_best_oos_rule_holds(robust_report: dict):
    rule = robust_report["mechanism_summary"]["best_oos_rule"]
    baseline = robust_report["meta"]["baseline_pop_rate_pct"]
    assert rule["era"] == "oos_holdout"
    assert rule["n"] >= 200
    assert rule["rate_pct"] > baseline
    assert rule["lift_vs_baseline"] >= 1.5
    assert rule["cluster_bootstrap"]["cluster_boot_ci_95_low_pct"] > baseline_lo(
        robust_report["meta"]["baseline_pop_rate_pct"]
    )
    assert rule.get("oos_beats_insample") is True


def baseline_lo(baseline_pct: float) -> float:
    return baseline_pct - 2


@pytest.mark.integration
def test_robust_placebo_lift(robust_report: dict):
    p = robust_report["placebo_baselines"]
    assert p["lift_trigger_vs_fry_placebo"] > 1.2
    assert p["fry_trigger_got_pop_episode"]["rate_pct"] > p["fry_nontrigger_vol_dd_placebo"]["rate_pct"]
    assert p["fry_nontrigger_vol_dd_placebo"]["rate_pct"] > p["standard_vol_dd_signature"]["rate_pct"]


@pytest.mark.integration
def test_robust_logistic_oos_auc(robust_report: dict):
    auc = robust_report["mechanism_summary"]["logistic_oos_auc"]
    assert 0.55 <= auc <= 0.85


@pytest.mark.integration
def test_robust_drawdown_vol_oos_beats_quiet(robust_report: dict):
    rules = {r["rule_id"]: r for r in robust_report["composite_rules"] if r["era"] == "oos_holdout"}
    vol = rules["core_drawdown_vol"]["rate_pct"]
    quiet_ind = next(
        r for r in robust_report["indicator_scan"] if r["indicator_id"] == "trigger_quiet_only"
    )
    assert vol > quiet_ind["pop_rate_pct"] + 5


@pytest.mark.integration
def test_robust_survival_deep_dd_faster_than_all(robust_report: dict):
    surv = robust_report["survival_curves"]
    all_d7 = next(c for c in surv["all_triggers"] if c["day"] == 7)["cum_pop_rate_pct"]
    deep_d7 = next(c for c in surv["deep_dd_return5d_lte_8"] if c["day"] == 7)["cum_pop_rate_pct"]
    assert deep_d7 > all_d7


@pytest.mark.integration
def test_backtest_trigger_entry_not_the_play(backtest_report: dict):
    """T1 precision ~ base rate OOS; hold-from-trigger loses vs random fry."""
    acc = backtest_report["headline"]["guess_accuracy_oos_t1_pop30d"]
    assert acc["rule_precision_pct"] < acc["random_matched_p95_precision_pct"] + 5
    strat = backtest_report["headline"]["strategy_vs_random_hold5d"]
    assert strat["t1_hold_5d_mean_pct"] < strat["random_fry_hold_5d_mean_pct"]
    assert strat["oracle_capture_pop_day_move_pct"] > 10


@pytest.mark.integration
def test_trigger_enriched_schema():
    if not TRIGGER_PARQUET.exists():
        pytest.skip("trigger_enriched.parquet missing")
    t = pd.read_parquet(TRIGGER_PARQUET)
    required = {"return_5d", "vol_ratio_20d", "got_pop", "trigger_cause", "dd_60d"}
    assert required.issubset(t.columns)
    assert len(t) >= 8000
    pop_by_cause = t.groupby("trigger_cause")["got_pop"].mean()
    assert pop_by_cause.get("drawdown_vol_spike", 0) > pop_by_cause.get("quiet_accumulation", 1)
