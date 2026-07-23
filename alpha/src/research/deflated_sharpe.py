"""
Deflated Sharpe Ratio (DSR) + Probability of Backtest Overfitting (PBO).

References
----------
Bailey & López de Prado (2014), "The Deflated Sharpe Ratio: Correcting for
Selection Bias, Backtest Overfitting, and Non-Normality", Journal of
Portfolio Management.

Bailey, Borwein, López de Prado, Zhu (2014), "The Probability of Backtest
Overfitting", Journal of Computational Finance.

Why this matters
----------------
A grid search over N candidate strategies inflates the apparent Sharpe of the
selected winner. Reporting the raw best-Sharpe is statistically dishonest.
DSR adjusts the selected SR for (a) the number of trials, (b) the variance of
SR across trials, and (c) non-normality (skew, kurtosis) of the underlying
returns. PBO estimates the probability that the IS-best strategy
underperforms the median OOS — a direct, distribution-free measure of how
much your grid search was just curve-fitting noise.

For monthly returns the inputs to these functions should be in *per-period*
(monthly) Sharpe space. Annualize only on the way out, if at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats

# Euler-Mascheroni constant — appears in the expected-max-of-N-normals approx
_EULER_MASCHERONI = 0.5772156649015328606


# ---------------------------------------------------------------------------
# Sharpe + its sampling variance (non-Normal returns; Mertens 2002 / LdP 2012)
# ---------------------------------------------------------------------------


def per_period_sharpe(returns: Sequence[float]) -> float:
    """Mean / std (sample, ddof=1). Per-period (not annualized)."""
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    if r.size < 2:
        return float("nan")
    sd = r.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return float("nan")
    return float(r.mean() / sd)


def sharpe_se(returns: Sequence[float]) -> float:
    """
    Standard error of the per-period Sharpe under Mertens' non-Normal correction.

    Var(SR_hat) = (1 - skew*SR + ((kurt - 1)/4) * SR^2) / (N - 1)

    where kurt is the *raw* kurtosis (3 for Normal). For Normal returns this
    reduces to (1 + 0.5*SR^2)/(N-1), matching the classic Lo (2002) formula.
    """
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    n = r.size
    if n < 3:
        return float("nan")
    sr = per_period_sharpe(r)
    if not np.isfinite(sr):
        return float("nan")
    sk = float(stats.skew(r, bias=False))
    kr = float(stats.kurtosis(r, fisher=False, bias=False))  # raw, not excess
    denom_inside = 1.0 - sk * sr + ((kr - 1.0) / 4.0) * sr * sr
    if denom_inside <= 0 or not np.isfinite(denom_inside):
        return float("nan")
    return float(math.sqrt(denom_inside / (n - 1)))


# ---------------------------------------------------------------------------
# Probabilistic Sharpe (PSR) and Deflated Sharpe (DSR)
# ---------------------------------------------------------------------------


def psr(returns: Sequence[float], sr_benchmark: float = 0.0) -> float:
    """
    Probabilistic Sharpe Ratio: P(SR_true > sr_benchmark | observed).

    Returns Φ((SR_hat - sr_benchmark) / sigma(SR_hat)).
    """
    sr_hat = per_period_sharpe(returns)
    se = sharpe_se(returns)
    if not np.isfinite(sr_hat) or not np.isfinite(se) or se == 0:
        return float("nan")
    z = (sr_hat - sr_benchmark) / se
    return float(stats.norm.cdf(z))


def expected_max_sharpe_under_null(n_trials: int, sr_variance: float) -> float:
    """
    Expected maximum Sharpe across `n_trials` independent strategies under the
    null SR = 0, assuming Sharpes are Normally distributed with variance V.

    E[max_K SR | null] ≈ sqrt(V) * ((1-γ)*Φ^{-1}(1-1/K) + γ*Φ^{-1}(1-1/(K*e)))

    where γ is the Euler-Mascheroni constant.
    """
    if n_trials < 2 or sr_variance <= 0:
        return 0.0
    k = float(n_trials)
    z1 = stats.norm.ppf(1.0 - 1.0 / k)
    z2 = stats.norm.ppf(1.0 - 1.0 / (k * math.e))
    return float(math.sqrt(sr_variance) * ((1.0 - _EULER_MASCHERONI) * z1 + _EULER_MASCHERONI * z2))


@dataclass(frozen=True)
class DSRResult:
    sr_observed: float
    sr_benchmark: float
    psr: float
    dsr: float
    expected_max_sr_under_null: float
    sharpe_se: float
    n_trials: int
    sr_variance_across_trials: float


def deflated_sharpe(
    selected_returns: Sequence[float],
    *,
    all_trial_sharpes: Sequence[float],
) -> DSRResult:
    """
    Deflated Sharpe Ratio for the winner of a grid search.

    selected_returns : per-period return series of the *winning* strategy
    all_trial_sharpes : per-period Sharpes of every strategy in the search
                       (used to estimate the variance of SR across trials AND
                       the trial count). Should include the winner.

    DSR = Φ((SR_obs - E[max SR | null]) / sigma(SR_obs))
    """
    sr_obs = per_period_sharpe(selected_returns)
    se = sharpe_se(selected_returns)
    trials = np.asarray(all_trial_sharpes, dtype=float)
    trials = trials[np.isfinite(trials)]
    n_trials = int(trials.size)
    sr_var = float(trials.var(ddof=1)) if n_trials >= 2 else 0.0

    sr_star = expected_max_sharpe_under_null(n_trials, sr_var)
    if np.isfinite(sr_obs) and np.isfinite(se) and se > 0:
        psr_val = float(stats.norm.cdf(sr_obs / se))
        dsr_val = float(stats.norm.cdf((sr_obs - sr_star) / se))
    else:
        psr_val = float("nan")
        dsr_val = float("nan")

    return DSRResult(
        sr_observed=float(sr_obs),
        sr_benchmark=float(sr_star),
        psr=psr_val,
        dsr=dsr_val,
        expected_max_sr_under_null=float(sr_star),
        sharpe_se=float(se),
        n_trials=n_trials,
        sr_variance_across_trials=sr_var,
    )


# ---------------------------------------------------------------------------
# Probability of Backtest Overfitting (Combinatorially-Symmetric CV)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PBOResult:
    pbo: float
    n_splits: int
    n_strategies: int
    n_combinations: int
    logits: np.ndarray  # one λ_c per combination; PBO = P(λ<=0)
    selected_strategy_indices: np.ndarray  # winner picked from each IS fold


def _combination_indices(n_groups: int) -> List[Tuple[Tuple[int, ...], Tuple[int, ...]]]:
    """All ways to split {0..n_groups-1} into two equal halves (IS, OOS)."""
    assert n_groups % 2 == 0, "n_groups must be even"
    half = n_groups // 2
    all_idx = tuple(range(n_groups))
    combos = []
    for is_idx in combinations(all_idx, half):
        oos_idx = tuple(i for i in all_idx if i not in set(is_idx))
        combos.append((is_idx, oos_idx))
    return combos


def probability_of_backtest_overfitting(
    returns_matrix: np.ndarray,
    *,
    n_splits: int = 16,
) -> PBOResult:
    """
    Combinatorially-Symmetric Cross-Validation PBO.

    returns_matrix : (T, N) array. T = time periods, N = strategies tried.
    n_splits       : S (even). Partitions T into S disjoint, contiguous groups.
                     Default 16 yields C(16,8) = 12870 combinations.

    For each (IS, OOS) split of S/2 groups each:
      - Pick the strategy n* with max Sharpe on IS
      - Rank n*'s Sharpe among all strategies on OOS
      - ω_c = rank/(N+1);  λ_c = log(ω_c/(1-ω_c))
    PBO = fraction of c where λ_c <= 0 (IS-winner ≤ OOS median).

    Returns the PBO and the distribution of logits.
    """
    M = np.asarray(returns_matrix, dtype=float)
    if M.ndim != 2:
        raise ValueError("returns_matrix must be 2-D (T, N)")
    T, N = M.shape
    if N < 2:
        raise ValueError("need at least 2 strategies to estimate PBO")
    if n_splits % 2 != 0 or n_splits < 2:
        raise ValueError("n_splits must be even and >= 2")
    if T < n_splits:
        raise ValueError(f"need T >= n_splits (got T={T}, S={n_splits})")

    # Partition rows into S near-equal contiguous groups
    boundaries = np.linspace(0, T, n_splits + 1, dtype=int)
    groups = [np.arange(boundaries[s], boundaries[s + 1]) for s in range(n_splits)]

    combos = _combination_indices(n_splits)
    logits = np.empty(len(combos), dtype=float)
    winners = np.empty(len(combos), dtype=int)

    for c_idx, (is_idx, oos_idx) in enumerate(combos):
        is_rows = np.concatenate([groups[i] for i in is_idx])
        oos_rows = np.concatenate([groups[i] for i in oos_idx])
        is_block = M[is_rows]
        oos_block = M[oos_rows]

        is_mean = is_block.mean(axis=0)
        is_std = is_block.std(axis=0, ddof=1)
        is_sr = np.where(is_std > 0, is_mean / is_std, -np.inf)
        n_star = int(np.argmax(is_sr))
        winners[c_idx] = n_star

        oos_mean = oos_block.mean(axis=0)
        oos_std = oos_block.std(axis=0, ddof=1)
        oos_sr = np.where(oos_std > 0, oos_mean / oos_std, np.nan)
        # Rank n* against the OOS distribution. ranks: 1..N (1 = worst, N = best)
        order = np.argsort(np.where(np.isnan(oos_sr), -np.inf, oos_sr))
        rank_of = np.empty(N, dtype=int)
        rank_of[order] = np.arange(1, N + 1)
        r_star = rank_of[n_star]
        omega = r_star / (N + 1.0)
        # Guard against omega == 0 or 1 (only possible at the extremes)
        omega = float(min(max(omega, 1e-9), 1.0 - 1e-9))
        logits[c_idx] = math.log(omega / (1.0 - omega))

    pbo = float(np.mean(logits <= 0.0))
    return PBOResult(
        pbo=pbo,
        n_splits=int(n_splits),
        n_strategies=int(N),
        n_combinations=int(len(combos)),
        logits=logits,
        selected_strategy_indices=winners,
    )


# ---------------------------------------------------------------------------
# CLI helper: load a grid of equity-curve CSVs and run DSR + PBO
# ---------------------------------------------------------------------------


def load_returns_grid(equity_curve_paths: Iterable[str]) -> Tuple[pd.DataFrame, List[str]]:
    """
    Load several `equity_curve.csv` files (date, equity) into a single
    (T, N) period-return DataFrame aligned on the common date intersection.

    Returns (returns_df, strategy_labels) where strategy_labels[i] is the
    parent directory name of equity_curve_paths[i].
    """
    from pathlib import Path

    curves = {}
    for raw in equity_curve_paths:
        p = Path(raw)
        if not p.exists():
            continue
        df = pd.read_csv(p, index_col=0)
        df.index = pd.to_datetime(df.index, errors="coerce")
        df = df[~df.index.isna()].sort_index()
        # Assume single value column
        if df.shape[1] == 0:
            continue
        equity = df.iloc[:, 0]
        rets = equity.pct_change().dropna()
        if not rets.empty:
            curves[p.parent.name] = rets

    if not curves:
        return pd.DataFrame(), []

    aligned = pd.concat(curves, axis=1).dropna(how="any")
    labels = list(aligned.columns)
    return aligned, labels


def cli(argv: Optional[Sequence[str]] = None) -> int:
    """CLI: DSR + PBO from a directory of backtest output dirs."""
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(
        description="Compute Deflated Sharpe Ratio + PBO from a grid of backtest outputs."
    )
    ap.add_argument(
        "--outputs-dir",
        type=Path,
        required=True,
        help="Directory containing one subdir per backtest, each with equity_curve.csv",
    )
    ap.add_argument(
        "--pattern",
        type=str,
        default="*/equity_curve.csv",
        help="Glob under --outputs-dir to find equity curves (default: */equity_curve.csv)",
    )
    ap.add_argument("--pbo-splits", type=int, default=16, help="S in PBO (must be even).")
    ap.add_argument("--report-json", type=Path, default=None, help="Optional report output path.")
    args = ap.parse_args(argv)

    paths = sorted(args.outputs_dir.glob(args.pattern))
    if not paths:
        raise SystemExit(f"no equity_curve.csv found under {args.outputs_dir}/{args.pattern}")

    rets, labels = load_returns_grid(str(p) for p in paths)
    if rets.empty:
        raise SystemExit("loaded zero usable returns")

    # Per-strategy Sharpes for DSR
    sharpes = np.array([per_period_sharpe(rets[c].values) for c in labels])
    finite_mask = np.isfinite(sharpes)
    if not finite_mask.any():
        raise SystemExit("no finite Sharpes; cannot deflate")
    winner_idx = int(np.nanargmax(sharpes))
    winner_label = labels[winner_idx]

    dsr_res = deflated_sharpe(
        rets[winner_label].values,
        all_trial_sharpes=sharpes[finite_mask],
    )

    pbo_res = probability_of_backtest_overfitting(rets.values, n_splits=args.pbo_splits)

    report = {
        "schema": "sharpe-renaissance/dsr_pbo/v1",
        "outputs_dir": str(args.outputs_dir),
        "n_strategies_loaded": int(len(labels)),
        "n_periods": int(rets.shape[0]),
        "winner": {
            "label": winner_label,
            "sharpe_observed_per_period": float(sharpes[winner_idx]),
        },
        "deflated_sharpe": {
            "sr_observed": dsr_res.sr_observed,
            "sr_expected_under_null_max": dsr_res.expected_max_sr_under_null,
            "sharpe_se": dsr_res.sharpe_se,
            "psr": dsr_res.psr,
            "dsr": dsr_res.dsr,
            "n_trials": dsr_res.n_trials,
            "sr_variance_across_trials": dsr_res.sr_variance_across_trials,
        },
        "pbo": {
            "pbo": pbo_res.pbo,
            "n_splits": pbo_res.n_splits,
            "n_strategies": pbo_res.n_strategies,
            "n_combinations": pbo_res.n_combinations,
        },
    }

    # Attach a fingerprint so the report is itself reproducible
    try:
        from src.research.fingerprint import stamp as _stamp_fp

        _stamp_fp(report, config={"args": vars(args), "labels": labels})
    except Exception:
        pass

    text = json.dumps(report, indent=2, default=str)
    print(text)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(text + "\n")
        print(f"\nwrote: {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
