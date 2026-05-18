#!/usr/bin/env python3
"""
Signal promotion gate.

Before a candidate signal JSON can be copied to alpha_live_signal.json
(i.e., go live in paper or real trading), it must clear quantitative
thresholds backed by the research-integrity toolkit:

  - DSR (Deflated Sharpe Ratio) > min_dsr  → winner is statistically
    distinguishable from the multiple-testing null
  - PBO (Probability of Backtest Overfitting) < max_pbo → strategy
    survives combinatorially-symmetric cross-validation
  - α t-stat HAC > min_alpha_tstat → return is not purely factor exposure
  - net-of-cost monthly return after transaction costs > min_net_return

If ALL gates pass, the candidate is promoted (file copied or symlinked).
If any gate fails, the script exits non-zero with a clear reason and the
live signal is NOT touched.

Inputs the gate expects to find alongside the candidate signal:
  - A directory containing equity_curve.csv files for the full grid of
    configs the winner was selected from (for DSR + PBO).
  - The candidate's own equity_curve.csv (for factor attribution).

Usage
-----
  scripts/promote_signal.py \\
    --candidate-signal backtests/outputs/signals/alpha_new_candidate.json \\
    --candidate-curve backtests/outputs/alpha_new_candidate/equity_curve.csv \\
    --grid-dir backtests/outputs --grid-pattern "alpha_cached_*/equity_curve.csv" \\
    --live-out backtests/outputs/signals/alpha_live_signal.json \\
    [--dry-run]

Default thresholds reflect a serious-but-not-impossible bar. Tune via flags.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np
import pandas as pd

SR_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SR_ROOT))

from src.research.deflated_sharpe import (  # noqa: E402
    deflated_sharpe,
    load_returns_grid,
    per_period_sharpe,
    probability_of_backtest_overfitting,
)
from src.research.factor_attribution import (  # noqa: E402
    load_famafrench_monthly,
    load_factors_csv,
    regress_on_factors,
    strategy_monthly_returns_from_equity_curve,
)


@dataclass
class GateThresholds:
    min_dsr: float = 0.95
    max_pbo: float = 0.50
    min_alpha_tstat_hac: float = 1.5
    min_net_monthly_return: float = 0.0
    pbo_splits: int = 8


@dataclass
class GateOutcome:
    passed: bool
    reasons: List[str]
    metrics: dict


def run_gates(
    *,
    candidate_curve: Path,
    grid_dir: Path,
    grid_pattern: str,
    thresholds: GateThresholds,
    factors_csv: Optional[Path],
) -> GateOutcome:
    metrics: dict = {}
    reasons: List[str] = []

    # ----- DSR + PBO over the full grid -----------------------------------
    grid_paths = sorted(grid_dir.glob(grid_pattern))
    if candidate_curve not in grid_paths:
        grid_paths.append(candidate_curve)

    rets, labels = load_returns_grid(str(p) for p in grid_paths)
    if rets.empty:
        return GateOutcome(False, ["could not load any returns from grid"], metrics)

    sharpes = np.array([per_period_sharpe(rets[c].values) for c in labels])
    cand_label = candidate_curve.parent.name
    if cand_label not in labels:
        return GateOutcome(False, [f"candidate {cand_label} not found in grid"], metrics)

    cand_rets = rets[cand_label].values
    dsr_res = deflated_sharpe(cand_rets, all_trial_sharpes=sharpes[np.isfinite(sharpes)])
    pbo_res = probability_of_backtest_overfitting(rets.values, n_splits=thresholds.pbo_splits)

    metrics["dsr"] = dsr_res.dsr
    metrics["pbo"] = pbo_res.pbo
    metrics["sharpe_per_period"] = dsr_res.sr_observed
    metrics["n_trials"] = dsr_res.n_trials
    metrics["n_pbo_combinations"] = pbo_res.n_combinations

    if dsr_res.dsr < thresholds.min_dsr:
        reasons.append(
            f"DSR {dsr_res.dsr:.3f} < {thresholds.min_dsr:.2f} "
            f"(multiple-testing-adjusted Sharpe not strong enough)"
        )
    if pbo_res.pbo > thresholds.max_pbo:
        reasons.append(
            f"PBO {pbo_res.pbo:.3f} > {thresholds.max_pbo:.2f} "
            f"(IS-best underperforms OOS too often; likely curve-fitting)"
        )

    # ----- Factor α t-stat on the candidate's own monthly returns ---------
    try:
        monthly = strategy_monthly_returns_from_equity_curve(candidate_curve)
        if len(monthly) < 12:
            metrics["alpha_tstat_hac"] = None
            reasons.append(
                f"only {len(monthly)} monthly returns — too few for "
                "Fama-French regression (need ≥ 12)"
            )
        else:
            factors = load_factors_csv(factors_csv) if factors_csv else load_famafrench_monthly(
                start=str(monthly.index.min().date()),
                end=str(monthly.index.max().date()),
            )
            fa = regress_on_factors(monthly, factors)
            metrics["alpha_monthly"] = fa.alpha_monthly
            metrics["alpha_annualized"] = fa.alpha_annualized
            metrics["alpha_tstat_hac"] = fa.alpha_tstat
            metrics["factor_r_squared"] = fa.r_squared
            metrics["factor_betas"] = fa.factor_betas
            if abs(fa.alpha_tstat) < thresholds.min_alpha_tstat_hac:
                reasons.append(
                    f"α t-stat HAC {fa.alpha_tstat:.2f} < {thresholds.min_alpha_tstat_hac:.2f} "
                    f"(return is mostly factor exposure, not skill)"
                )
    except Exception as exc:
        reasons.append(f"factor attribution failed: {exc}")

    # ----- Net-of-cost monthly return (approximation) ---------------------
    # Approximate: assume 5 bps per rebalance; subtract from sharpe-implied return.
    monthly_mean = float(np.mean(cand_rets))
    cost_per_rebalance_bps = 5.0
    approx_net_monthly = monthly_mean - (cost_per_rebalance_bps / 10_000.0)
    metrics["net_monthly_return_approx"] = approx_net_monthly
    if approx_net_monthly < thresholds.min_net_monthly_return:
        reasons.append(
            f"net monthly return (approx) {approx_net_monthly:.4f} < "
            f"{thresholds.min_net_monthly_return:.4f}"
        )

    return GateOutcome(passed=not reasons, reasons=reasons, metrics=metrics)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Signal promotion gate.")
    ap.add_argument("--candidate-signal", type=Path, required=True)
    ap.add_argument("--candidate-curve", type=Path, required=True)
    ap.add_argument("--grid-dir", type=Path, required=True)
    ap.add_argument("--grid-pattern", type=str, default="*/equity_curve.csv")
    ap.add_argument("--live-out", type=Path, required=True,
                    help="Where to copy the signal if all gates pass.")
    ap.add_argument("--factors-csv", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="Don't actually copy; print decision + metrics.")
    ap.add_argument("--min-dsr", type=float, default=GateThresholds.min_dsr)
    ap.add_argument("--max-pbo", type=float, default=GateThresholds.max_pbo)
    ap.add_argument("--min-alpha-tstat", type=float, default=GateThresholds.min_alpha_tstat_hac)
    ap.add_argument("--min-net-return", type=float, default=GateThresholds.min_net_monthly_return)
    ap.add_argument("--pbo-splits", type=int, default=GateThresholds.pbo_splits)
    args = ap.parse_args(argv)

    thresholds = GateThresholds(
        min_dsr=args.min_dsr,
        max_pbo=args.max_pbo,
        min_alpha_tstat_hac=args.min_alpha_tstat,
        min_net_monthly_return=args.min_net_return,
        pbo_splits=args.pbo_splits,
    )
    outcome = run_gates(
        candidate_curve=args.candidate_curve,
        grid_dir=args.grid_dir,
        grid_pattern=args.grid_pattern,
        thresholds=thresholds,
        factors_csv=args.factors_csv,
    )

    decision = {
        "candidate_signal": str(args.candidate_signal),
        "passed": outcome.passed,
        "failure_reasons": outcome.reasons,
        "metrics": outcome.metrics,
        "thresholds": vars(thresholds),
    }
    try:
        from src.research.fingerprint import stamp as _stamp_fp
        _stamp_fp(decision, config={"args": vars(args)})
    except Exception:
        pass
    print(json.dumps(decision, indent=2, default=str))

    if not outcome.passed:
        print("\n❌ GATE FAILED — live signal NOT updated.", file=sys.stderr)
        return 2

    if args.dry_run:
        print("\n✅ Would promote (dry-run; live signal not touched).", file=sys.stderr)
        return 0

    args.live_out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.candidate_signal, args.live_out)
    print(f"\n✅ PROMOTED: {args.candidate_signal} → {args.live_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
