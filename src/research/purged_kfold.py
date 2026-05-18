"""
Purged k-fold cross-validation for time-series ML (López de Prado, AFML 2018).

Standard k-fold leaks information when:
  - The label of a training observation overlaps in time with the test fold
    (because the label was computed from data that *includes* test-fold info).
  - A training observation immediately follows the test fold and shares
    autocorrelated context.

Purged k-fold fixes both by:
  1. **Purging**: drop any training row whose label time-window overlaps the
     test fold.
  2. **Embargo**: drop additional training rows in a small window after the
     test fold to break short-horizon autocorrelation leakage.

For monthly returns predicting next-month ret_fwd_1m, label_horizon=1.
Embargo=1 means one extra training month is dropped after each test fold.

This is provided as an alternative to the chronological CV in
alpha_insights_walkforward_runner._cv_select_lambda. Wire it in via
`select_lambda_purged_kfold` from training data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Fold generation
# ---------------------------------------------------------------------------


def purged_kfold_indices(
    n_periods: int,
    *,
    k_folds: int = 5,
    embargo: int = 1,
    label_horizon: int = 1,
) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
    """
    Yield (train_idx, test_idx) integer arrays into [0, n_periods).

    Periods are contiguous groups (e.g. months). Each fold's test block is
    contiguous; train is everything except a purged + embargoed window
    around the test block.

    label_horizon : how many periods FORWARD the label depends on. For
                    next-month prediction this is 1.
    embargo       : how many extra periods to drop AFTER the test fold (to
                    suppress autocorrelation leakage into the next training
                    observation).
    """
    if k_folds < 2:
        raise ValueError("k_folds must be >= 2")
    if n_periods < k_folds:
        raise ValueError(f"n_periods ({n_periods}) must be >= k_folds ({k_folds})")
    if embargo < 0:
        raise ValueError("embargo must be >= 0")
    if label_horizon < 0:
        raise ValueError("label_horizon must be >= 0")

    boundaries = np.linspace(0, n_periods, k_folds + 1, dtype=int)
    for i in range(k_folds):
        test_start = int(boundaries[i])
        test_end = int(boundaries[i + 1])
        if test_end <= test_start:
            continue
        # Purge training rows whose forward label overlaps the test window.
        purge_lo = max(0, test_start - label_horizon)
        # Embargo: drop a few rows after the test window so the immediately
        # next training row doesn't carry autocorrelated context.
        purge_hi = min(n_periods, test_end + label_horizon + embargo)
        train_mask = np.ones(n_periods, dtype=bool)
        train_mask[purge_lo:purge_hi] = False
        train_idx = np.flatnonzero(train_mask)
        test_idx = np.arange(test_start, test_end)
        yield train_idx, test_idx


# ---------------------------------------------------------------------------
# CV scoring + lambda selection for the alpha ridge
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PurgedCVResult:
    lambda_selected: float
    fold_scores: np.ndarray  # mean IC per fold for the selected lambda
    lambda_grid: List[float]
    lambda_scores: List[float]  # mean OOS IC across folds, per lambda
    k_folds: int
    embargo: int


def _ridge_solve(X: np.ndarray, y: np.ndarray, lam: float, w: Optional[np.ndarray] = None) -> np.ndarray:
    """Closed-form weighted ridge. Mirror of scripts/alpha_insights_walkforward_runner._ridge_fit."""
    if w is not None:
        W = np.diag(w)
        XtWX = X.T @ W @ X
        XtWy = X.T @ (w * y)
    else:
        XtWX = X.T @ X
        XtWy = X.T @ y
    k = XtWX.shape[0]
    return np.linalg.solve(XtWX + float(lam) * np.eye(k), XtWy)


def _spearman_ic(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson on ranks — no scipy dep."""
    if a.size < 3 or b.size < 3:
        return float("nan")
    ra = pd.Series(a).rank(method="average").to_numpy()
    rb = pd.Series(b).rank(method="average").to_numpy()
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denom = float(np.sqrt((ra**2).sum()) * np.sqrt((rb**2).sum()))
    if denom <= 0:
        return float("nan")
    return float((ra * rb).sum() / denom)


def select_lambda_purged_kfold(
    train: pd.DataFrame,
    *,
    feature_cols: Sequence[str],
    lam_grid: Sequence[float],
    min_assets: int = 3,
    k_folds: int = 5,
    embargo: int = 1,
    label_horizon: int = 1,
    date_col: str = "date",
    label_col: str = "ret_fwd_1m",
) -> PurgedCVResult:
    """
    Pick lambda by purged k-fold CV on a panel DataFrame.

    train is expected to have columns [date, instrument, *feature_cols, label_col].
    Each unique date is one period (e.g. month). For each (train_dates, test_dates)
    purged fold, fit ridge on train rows, score Spearman IC of predictions
    against labels across test rows (averaged per test date for stability).

    Returns the lambda with the highest mean cross-fold IC. Falls back to the
    middle of the grid if every lambda's IC is non-positive.
    """
    if not lam_grid:
        raise ValueError("lam_grid must be non-empty")
    unique_dates = sorted(pd.Index(train[date_col].unique()))
    n_periods = len(unique_dates)
    if n_periods < k_folds + label_horizon + embargo + 1:
        # Not enough data for purged CV — caller should fall back.
        raise ValueError(
            f"need at least {k_folds + label_horizon + embargo + 1} periods; got {n_periods}"
        )

    # Pre-extract for speed: per-period arrays.
    fcols = list(feature_cols)
    by_period_X: List[np.ndarray] = []
    by_period_y: List[np.ndarray] = []
    for d in unique_dates:
        sub = train[train[date_col] == d].dropna(subset=fcols + [label_col])
        by_period_X.append(sub[fcols].to_numpy(dtype=float))
        by_period_y.append(sub[label_col].to_numpy(dtype=float))

    folds = list(purged_kfold_indices(n_periods, k_folds=k_folds, embargo=embargo, label_horizon=label_horizon))

    lambda_scores: List[float] = []
    per_fold_for_winner: Optional[np.ndarray] = None
    best_lam = float(lam_grid[len(lam_grid) // 2])
    best_score = -np.inf

    for lam in lam_grid:
        fold_ics: List[float] = []
        for tr_idx, te_idx in folds:
            X_tr = [by_period_X[i] for i in tr_idx if by_period_X[i].size > 0]
            y_tr = [by_period_y[i] for i in tr_idx if by_period_y[i].size > 0]
            if not X_tr:
                continue
            X_tr_cat = np.vstack(X_tr)
            y_tr_cat = np.concatenate(y_tr)
            if X_tr_cat.shape[0] < min_assets:
                continue
            beta = _ridge_solve(X_tr_cat, y_tr_cat, float(lam))

            test_ics: List[float] = []
            for j in te_idx:
                if by_period_X[j].size == 0 or by_period_X[j].shape[0] < min_assets:
                    continue
                pred = by_period_X[j] @ beta
                ic = _spearman_ic(pred, by_period_y[j])
                if np.isfinite(ic):
                    test_ics.append(ic)
            if test_ics:
                fold_ics.append(float(np.mean(test_ics)))
        if not fold_ics:
            lambda_scores.append(float("nan"))
            continue
        score = float(np.mean(fold_ics))
        lambda_scores.append(score)
        if score > best_score:
            best_score = score
            best_lam = float(lam)
            per_fold_for_winner = np.asarray(fold_ics, dtype=float)

    if best_score <= 0 or per_fold_for_winner is None:
        best_lam = float(lam_grid[len(lam_grid) // 2])
        per_fold_for_winner = np.array([], dtype=float)

    return PurgedCVResult(
        lambda_selected=best_lam,
        fold_scores=per_fold_for_winner,
        lambda_grid=[float(x) for x in lam_grid],
        lambda_scores=lambda_scores,
        k_folds=int(k_folds),
        embargo=int(embargo),
    )
