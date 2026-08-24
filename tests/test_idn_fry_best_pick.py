"""Tests for gated fry best-pick radar."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alpha" / "scripts"))

from idn_fry_best_pick_lib import PickCandidate, evaluate_gates, pick_best_fry_candidates, rank_score  # noqa: E402


def _row(**kw):
    base = {
        "yahoo_symbol": "TEST.JK",
        "name_type": "fry",
        "return_5d": -0.10,
        "vol_ratio_20d": 2.2,
        "return_1d": -0.02,
        "bandar_lite_label": "squeeze_from_drawdown",
        "pop_trigger_cause": "drawdown_vol_spike",
        "sink_risk_tier": "low",
        "action_score": 60,
        "multi_year_pop_score": 1.5,
        "symbol_pop_prior_wf": 30.0,
        "as_of": "2026-07-01",
    }
    base.update(kw)
    return base


def test_quiet_only_fails_hard_gate():
    gates = evaluate_gates(
        _row(bandar_lite_label="quiet_volume_build", return_5d=-0.02, vol_ratio_20d=1.2),
        dead_syms=set(),
        sym_prior=0.3,
    )
    assert any(g.gate_id == "not_quiet_only" and not g.passed for g in gates)


def test_t1_passes_core_gates():
    gates = evaluate_gates(_row(), dead_syms=set(), sym_prior=0.3)
    hard = {g.gate_id: g.passed for g in gates if g.hard}
    assert hard["t1_deep_dd_vol"]
    assert hard["not_quiet_only"]
    assert hard["sink_risk_not_high"]


def test_dead_name_fails():
    gates = evaluate_gates(_row(), dead_syms={"TEST.JK"}, sym_prior=0.3)
    assert any(g.gate_id == "not_dead_name" and not g.passed for g in gates)


def test_pick_best_ranks_top():
    wl = [_row(yahoo_symbol="A.JK"), _row(yahoo_symbol="B.JK", return_5d=-0.05, vol_ratio_20d=1.2, action_score=10)]
    rep = pick_best_fry_candidates(wl, top_k=2)
    assert rep["n_scanned"] == 2
    assert rep["n_pass"] >= 1
    if rep["top_picks"]:
        assert rep["top_picks"][0]["pick_rank"] == 1
