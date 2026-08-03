#!/usr/bin/env python3
"""
Minimal alpha regression helpers (no external dependencies).

Computes OLS alpha (intercept) and a simple Newey-West HAC t-stat.

Notes:
- This is for research diagnostics only.
- If you want “paper-grade” inference, use statsmodels and more careful factor datasets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AlphaResult:
    alpha_monthly: float
    alpha_annual: float
    alpha_tstat_hac: float
    n: int
    factors: list[str]


def _nw_cov(X: np.ndarray, u: np.ndarray, lags: int) -> np.ndarray:
    """
    Newey-West covariance estimator for OLS coefficients.
    X: (T, K), u: (T,)
    Returns: (K, K)
    """
    T, K = X.shape
    if T <= K + 2:
        return np.full((K, K), np.nan)

    # S_0
    Xu = X * u.reshape(-1, 1)
    S = (Xu.T @ Xu) / T

    L = int(max(0, lags))
    for l in range(1, L + 1):
        w = 1.0 - l / (L + 1.0)
        Gamma = (Xu[l:].T @ Xu[:-l]) / T
        S = S + w * (Gamma + Gamma.T)

    XtX_inv = np.linalg.pinv((X.T @ X) / T)
    V = XtX_inv @ S @ XtX_inv / T
    return V


def alpha_regression(
    y: pd.Series,
    X: pd.DataFrame,
    *,
    lags: int = 3,
) -> Optional[AlphaResult]:
    """
    Regress y on X (with intercept) and return alpha + HAC t-stat for alpha.
    y and X are expected to be monthly returns aligned on the same index.
    """
    if y.empty or X.empty:
        return None

    df = pd.concat([y.rename("y"), X], axis=1).dropna()
    if len(df) < 24:
        return None

    yv = df["y"].to_numpy(dtype=float)
    Xv = df.drop(columns=["y"]).to_numpy(dtype=float)
    Xv = np.column_stack([np.ones(len(df), dtype=float), Xv])

    beta = np.linalg.pinv(Xv) @ yv
    u = yv - Xv @ beta
    V = _nw_cov(Xv, u, lags=lags)
    if np.any(np.isnan(V)):
        return None

    se = float(np.sqrt(V[0, 0]))
    t = float(beta[0] / se) if se > 0 else 0.0

    alpha_m = float(beta[0])
    return AlphaResult(
        alpha_monthly=alpha_m,
        alpha_annual=float(alpha_m * 12.0),
        alpha_tstat_hac=t,
        n=int(len(df)),
        factors=["Intercept"] + list(df.drop(columns=["y"]).columns),
    )


def alpha_report_dict(res: Optional[AlphaResult]) -> Optional[Dict]:
    return asdict(res) if res is not None else None

