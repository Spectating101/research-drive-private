"""
Block bootstrap confidence intervals for ridge regression coefficients.

Why block bootstrap and not IID
-------------------------------
The alpha ridge is fit on a panel where observations within a period are
cross-sectional (assets at one date) and observations across periods are
serially dependent (returns are autocorrelated, especially in vol regimes).
IID bootstrap over rows would inflate effective sample size and produce
artificially tight intervals. Block bootstrap (Politis & Romano 1994)
samples contiguous *period* blocks with replacement, preserving short-run
dependence.

Output
------
For each feature coefficient, we report:
  - bootstrap mean (point estimate, equal to the in-sample fit at the limit)
  - bootstrap SE
  - 2.5% / 50% / 97.5% percentiles
  - "significant at 5%" flag: 0 is outside the 95% CI

These are the same intervals an institutional research desk would put on a
factor-tilt regression. Tells you which features the ridge actually trusts
and which are noise that happen to fit in-sample.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional, Sequence

import numpy as np
import pandas as pd

from src.research.purged_kfold import _ridge_solve


# ---------------------------------------------------------------------------
# Block index generation
# ---------------------------------------------------------------------------


def block_bootstrap_period_indices(
    n_periods: int,
    *,
    block_size: int,
    n_iter: int,
    seed: int = 0,
) -> Iterator[np.ndarray]:
    """
    Yield `n_iter` arrays of `n_periods` integer period indices, drawn as
    contiguous blocks of size `block_size` with replacement.

    Wraps around the end so blocks near the tail don't get truncated.
    """
    if block_size < 1:
        raise ValueError("block_size must be >= 1")
    if n_periods < block_size:
        raise ValueError(f"n_periods ({n_periods}) must be >= block_size ({block_size})")
    if n_iter < 1:
        raise ValueError("n_iter must be >= 1")
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n_periods / block_size))
    for _ in range(n_iter):
        starts = rng.integers(0, n_periods, size=n_blocks)
        idx = np.concatenate([
            (np.arange(start, start + block_size) % n_periods)
            for start in starts
        ])
        yield idx[:n_periods]


# ---------------------------------------------------------------------------
# Bootstrap ridge fits
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BootstrapCoefResult:
    feature_names: List[str]
    draws: np.ndarray  # shape (n_iter, n_features)
    point_estimate: np.ndarray  # in-sample fit coefficients
    block_size: int
    n_iter: int
    lambda_used: float

    def summary(self, alpha: float = 0.05) -> pd.DataFrame:
        lo = float(alpha / 2.0) * 100.0
        hi = (1.0 - float(alpha / 2.0)) * 100.0
        rows = []
        for j, name in enumerate(self.feature_names):
            d = self.draws[:, j]
            ci_lo = float(np.percentile(d, lo))
            ci_hi = float(np.percentile(d, hi))
            rows.append({
                "feature": name,
                "point_estimate": float(self.point_estimate[j]),
                "bootstrap_mean": float(np.mean(d)),
                "bootstrap_se": float(np.std(d, ddof=1)),
                "ci_lo": ci_lo,
                "ci_median": float(np.percentile(d, 50)),
                "ci_hi": ci_hi,
                "significant_5pct": bool((ci_lo > 0) or (ci_hi < 0)),
            })
        return pd.DataFrame(rows).set_index("feature")


def bootstrap_ridge_coefficients(
    panel: pd.DataFrame,
    *,
    feature_cols: Sequence[str],
    label_col: str = "ret_fwd_1m",
    date_col: str = "date",
    lam: float = 0.1,
    n_iter: int = 500,
    block_size: int = 3,
    seed: int = 0,
    min_assets_per_period: int = 3,
) -> BootstrapCoefResult:
    """
    Block-bootstrap CIs for ridge coefficients fit on a panel.

    panel must have columns [date_col, *feature_cols, label_col]. Each
    unique date is one period; periods are the resampling unit (preserves
    cross-section within a period, breaks across-period autocorrelation only
    at block boundaries).
    """
    fcols = list(feature_cols)
    sub = panel.dropna(subset=fcols + [label_col]).copy()
    unique_dates = sorted(sub[date_col].unique())
    n_periods = len(unique_dates)
    if n_periods < block_size:
        raise ValueError(f"need at least {block_size} periods; got {n_periods}")

    by_period_X: List[np.ndarray] = []
    by_period_y: List[np.ndarray] = []
    for d in unique_dates:
        s = sub[sub[date_col] == d]
        by_period_X.append(s[fcols].to_numpy(dtype=float))
        by_period_y.append(s[label_col].to_numpy(dtype=float))

    # In-sample point estimate from the full panel
    X_all = np.vstack([x for x in by_period_X if x.size > 0])
    y_all = np.concatenate([y for y in by_period_y if y.size > 0])
    point = _ridge_solve(X_all, y_all, lam)

    draws = np.empty((n_iter, len(fcols)), dtype=float)
    completed = 0
    for it_idx, period_idx in enumerate(
        block_bootstrap_period_indices(n_periods, block_size=block_size, n_iter=n_iter, seed=seed)
    ):
        Xs = [by_period_X[i] for i in period_idx if by_period_X[i].shape[0] >= min_assets_per_period]
        ys = [by_period_y[i] for i in period_idx if by_period_y[i].shape[0] >= min_assets_per_period]
        if not Xs:
            continue
        Xb = np.vstack(Xs)
        yb = np.concatenate(ys)
        try:
            beta = _ridge_solve(Xb, yb, lam)
        except np.linalg.LinAlgError:
            continue
        draws[completed] = beta
        completed += 1
    draws = draws[:completed]

    return BootstrapCoefResult(
        feature_names=fcols,
        draws=draws,
        point_estimate=np.asarray(point, dtype=float),
        block_size=int(block_size),
        n_iter=int(completed),
        lambda_used=float(lam),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Block-bootstrap CIs for ridge coefficients.")
    ap.add_argument("--panel", type=Path, required=True,
                    help="CSV/parquet with date, feature_cols, ret_fwd_1m columns.")
    ap.add_argument("--features", type=str, nargs="+", required=True)
    ap.add_argument("--label", type=str, default="ret_fwd_1m")
    ap.add_argument("--lam", type=float, default=0.1)
    ap.add_argument("--n-iter", type=int, default=500)
    ap.add_argument("--block-size", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.panel.suffix.lower() == ".parquet":
        panel = pd.read_parquet(args.panel)
    else:
        panel = pd.read_csv(args.panel)
    # Normalize date column
    for c in panel.columns:
        if c.lower() == "date":
            panel = panel.rename(columns={c: "date"})
            break
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce")

    res = bootstrap_ridge_coefficients(
        panel,
        feature_cols=args.features,
        label_col=args.label,
        lam=args.lam,
        n_iter=args.n_iter,
        block_size=args.block_size,
        seed=args.seed,
    )
    summary = res.summary().reset_index().to_dict(orient="records")
    out = {
        "lambda_used": res.lambda_used,
        "block_size": res.block_size,
        "n_iter_completed": res.n_iter,
        "coefficients": summary,
    }
    try:
        from src.research.fingerprint import stamp as _stamp_fp

        _stamp_fp(out, panel_path=args.panel, config={"args": vars(args)})
    except Exception:
        pass
    text = json.dumps(out, indent=2, default=str)
    print(text)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(text + "\n")
        print(f"\nwrote: {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
