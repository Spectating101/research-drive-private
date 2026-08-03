"""Inferential stats for IDX conditional signal / trade-return studies."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def mean_return_inference(
    returns_pct: pd.Series,
    *,
    n_boot: int = 2000,
    seed: int = 42,
) -> dict[str, Any]:
    """t-test vs 0 + bootstrap CI on trade returns (percent units)."""
    r = returns_pct.dropna().astype(float)
    n = int(len(r))
    if n < 3:
        return {"n": n, "sufficient": False}

    mean = float(r.mean())
    std = float(r.std(ddof=1))
    se = std / math.sqrt(n) if n else float("nan")
    t_stat = mean / se if se and se > 0 else 0.0

    try:
        from scipy import stats

        p_two = float(stats.ttest_1samp(r, 0.0, nan_policy="omit").pvalue)
    except Exception:
        # Normal approx fallback
        p_two = float(2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2)))))

    rng = np.random.default_rng(seed)
    arr = r.to_numpy()
    boots = np.array([float(rng.choice(arr, size=n, replace=True).mean()) for _ in range(n_boot)])
    ci_lo, ci_hi = np.percentile(boots, [2.5, 97.5])

    return {
        "n": n,
        "sufficient": True,
        "mean_pct": round(mean, 4),
        "std_pct": round(std, 4),
        "se_pct": round(se, 4) if se == se else None,
        "t_stat": round(t_stat, 3),
        "p_value_two_sided": round(p_two, 4),
        "ci_95_low_pct": round(float(ci_lo), 4),
        "ci_95_high_pct": round(float(ci_hi), 4),
        "significant_5pct": bool(p_two < 0.05),
        "ci_excludes_zero": bool(ci_lo > 0 or ci_hi < 0),
    }


def benjamini_hochberg(keys: list[str], p_values: list[float]) -> dict[str, float]:
    """BH-FDR q-values aligned to keys."""
    m = len(p_values)
    if m == 0:
        return {}
    order = sorted(range(m), key=lambda i: p_values[i])
    q = [1.0] * m
    prev = 1.0
    for rank, idx in enumerate(reversed(order), start=1):
        i = order[-rank]
        raw_q = p_values[i] * m / (m - rank + 1)
        prev = min(prev, raw_q)
        q[i] = min(prev, 1.0)
    return {keys[i]: round(float(q[i]), 4) for i in range(m)}


def verdict_from_stats(
    *,
    turn_type: str,
    mean5: float | None,
    win5: float | None,
    stats5: dict[str, Any],
    era: str,
) -> str:
    if era != "oos_holdout":
        return "monitor"
    if not stats5.get("sufficient"):
        return "insufficient"
    p = stats5.get("p_value_two_sided", 1.0)
    ci_lo = stats5.get("ci_95_low_pct")
    ci_hi = stats5.get("ci_95_high_pct")
    n = stats5.get("n", 0)

    if turn_type == "floor":
        if (
            mean5 is not None
            and mean5 > 0.25
            and (win5 or 0) >= 0.52
            and p < 0.05
            and ci_lo is not None
            and ci_lo > 0
            and n >= 30
        ):
            return "follow"
        if mean5 is not None and abs(mean5) < 0.1 and n >= 50:
            return "reject"
        if p > 0.4 and n >= 30 and ci_lo is not None and ci_hi is not None and ci_lo < 0 < ci_hi:
            return "reject"
        return "monitor"

    if turn_type == "ceiling":
        if mean5 is not None and mean5 < -0.2 and p < 0.05 and ci_hi is not None and ci_hi < 0:
            return "follow_fade"
        if mean5 is not None and mean5 > 0.1 and n >= 30:
            return "reject"
        return "monitor"

    return "monitor"
