from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alpha"))
sys.path.insert(0, str(REPO / "kernel"))

from src.research.beta_core import STRATEGY_ID, apply_beta_fallback, beta_core_weights


def test_beta_core_weights_sum_to_one():
    w = beta_core_weights()
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert "BTC-USD" not in w and "ETH-USD" not in w
    assert w["BIL"] > 0


def test_beta_core_respects_available_universe():
    w = beta_core_weights(available={"BIL", "SPY", "GLD"})
    assert set(w) <= {"BIL", "SPY", "GLD"}
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_apply_beta_fallback_clears_prior_flag():
    signal = {
        "strategy": "alpha_eventproxy_cfg12",
        "weights": {"BTC-USD": 0.5, "ETH-USD": 0.5},
        "promotion_gate": {"passed": False, "reasons": ["PBO high"]},
    }
    apply_beta_fallback(signal, reasons=["PBO high"], available={"BIL", "SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC"})
    assert signal["strategy"] == STRATEGY_ID
    assert signal["alpha_book"] == "beta"
    assert signal["promotion_gate"]["kept_prior_weights"] is False
    assert signal["promotion_gate"]["fallback"] == STRATEGY_ID
    assert "BTC-USD" not in signal["weights"]
    assert signal["promotion_gate"]["rejected_weights"]["BTC-USD"] == 0.5
