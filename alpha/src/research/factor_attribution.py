"""
Fama-French 5-factor + Momentum attribution for strategy monthly returns.

Regresses strategy excess returns on:
    Mkt-RF, SMB, HML, RMW, CMA, Mom

and reports:
    alpha (monthly + annualized)
    factor betas
    t-statistics (Newey-West HAC, 3-lag default)
    R², adjusted R²
    information ratio of the residual

Why this matters
----------------
A Sharpe of 1.0 is uninformative if it's just compensation for size/value/
momentum tilts you could buy in a $5 ETF. This module tells you what
fraction of the strategy return is *real* alpha vs known factor exposure.

Data sources
------------
Default: pandas_datareader.famafrench (requires internet). The CLI also
accepts pre-saved monthly factor CSVs so the analysis is reproducible
offline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import numpy as np
import pandas as pd


_FF5_ZIP_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_5_Factors_2x3_CSV.zip"
)
_MOM_ZIP_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Momentum_Factor_CSV.zip"
)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def _fetch_kf_zip_to_monthly_df(url: str) -> pd.DataFrame:
    """
    Download a Ken French CSV ZIP, return the *monthly* block parsed.

    KF CSV layout: a few header lines, then a monthly block (yyyymm,...),
    a blank line, then an annual block (yyyy,...). We keep the monthly block.
    """
    import io
    import re
    import urllib.request
    import zipfile

    with urllib.request.urlopen(url, timeout=30) as resp:
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        name = zf.namelist()[0]
        raw = zf.read(name).decode("latin-1")

    # Parse: find the header (first column empty, remaining are factor names),
    # then take consecutive monthly-format (yyyymm) rows until the block ends.
    lines = raw.splitlines()
    header_idx = None
    for i, ln in enumerate(lines):
        parts = [p.strip() for p in ln.split(",")]
        if (
            len(parts) >= 2
            and parts[0] == ""
            and all(_looks_like_factor_name(p) for p in parts[1:])
        ):
            header_idx = i
            break
    if header_idx is None:
        raise RuntimeError(f"could not locate header in KF CSV {url}")
    header = [p.strip() for p in lines[header_idx].split(",")][1:]

    rows = []
    for ln in lines[header_idx + 1:]:
        parts = [p.strip() for p in ln.split(",")]
        if not parts or not parts[0]:
            break
        if not re.match(r"^\d{6}$", parts[0]):
            break  # we've left the monthly block
        try:
            vals = [float(x) for x in parts[1:]]
        except ValueError:
            break
        rows.append((parts[0], *vals))

    if not rows:
        raise RuntimeError(f"no monthly rows parsed from {url}")
    df = pd.DataFrame(rows, columns=["yyyymm"] + header)
    df["date"] = pd.to_datetime(df["yyyymm"], format="%Y%m").dt.to_period("M").dt.to_timestamp("M")
    df = df.drop(columns=["yyyymm"]).set_index("date").astype(float)
    return df


def _looks_like_factor_name(s: str) -> bool:
    s = s.strip()
    return bool(s) and any(tag in s for tag in ("Mkt", "SMB", "HML", "RMW", "CMA", "RF", "Mom"))


def load_famafrench_monthly(
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch FF5 + Mom monthly factors directly from Ken French's data library.

    Returns DataFrame indexed by month-end Timestamp with columns:
        Mkt-RF, SMB, HML, RMW, CMA, RF, Mom
    in *decimal* units (i.e. 0.01 == 1%).
    """
    ff5 = _fetch_kf_zip_to_monthly_df(_FF5_ZIP_URL)
    mom = _fetch_kf_zip_to_monthly_df(_MOM_ZIP_URL)

    df = ff5.join(mom, how="inner") / 100.0  # KF publishes in percent
    df.columns = [str(c).strip() for c in df.columns]
    if "Mom" not in df.columns:
        for c in df.columns:
            if c.lower().startswith("mom"):
                df = df.rename(columns={c: "Mom"})
                break
    if start:
        df = df.loc[pd.Timestamp(start):]
    if end:
        df = df.loc[:pd.Timestamp(end)]
    return df


def load_factors_csv(path: Path) -> pd.DataFrame:
    """
    Load a pre-saved monthly factors CSV. Expected columns:
        date,Mkt-RF,SMB,HML,RMW,CMA,RF,Mom   (values in decimals)
    """
    df = pd.read_csv(path)
    if "date" not in df.columns:
        raise ValueError("factors CSV must have a 'date' column")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date").sort_index()
    required = {"Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF", "Mom"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"factors CSV missing columns: {sorted(missing)}")
    return df.astype(float)


def strategy_monthly_returns_from_ledger(ledger_csv: Path) -> pd.Series:
    """Aggregate the daily paper ledger to month-end returns."""
    df = pd.read_csv(ledger_csv)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    monthly_equity = df["equity"].resample("ME").last()
    return monthly_equity.pct_change().dropna()


def strategy_monthly_returns_from_equity_curve(curve_csv: Path) -> pd.Series:
    """Load an `equity_curve.csv` (already month-end) and return monthly returns."""
    df = pd.read_csv(curve_csv, index_col=0)
    df.index = pd.to_datetime(df.index, errors="coerce")
    df = df.sort_index()
    return df.iloc[:, 0].pct_change().dropna()


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


@dataclass
class FactorRegressionResult:
    alpha_monthly: float
    alpha_annualized: float
    alpha_tstat: float
    alpha_pvalue: float
    r_squared: float
    adj_r_squared: float
    n_obs: int
    factor_betas: Dict[str, float]
    factor_tstats: Dict[str, float]
    factor_pvalues: Dict[str, float]
    residual_vol_annualized: float
    information_ratio: float
    factors_used: list


def regress_on_factors(
    strategy_monthly: pd.Series,
    factors: pd.DataFrame,
    *,
    use_momentum: bool = True,
    hac_lags: int = 3,
) -> FactorRegressionResult:
    """
    OLS with Newey-West (HAC) standard errors.

    strategy_monthly : pd.Series of monthly returns (decimal), DatetimeIndex.
    factors          : DataFrame containing at least Mkt-RF, SMB, HML, RMW,
                       CMA, RF, and (if use_momentum) Mom — in decimal units.
    """
    import statsmodels.api as sm

    factor_cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]
    if use_momentum and "Mom" in factors.columns:
        factor_cols.append("Mom")

    # Align indices on month boundaries.
    s = strategy_monthly.copy()
    s.index = pd.to_datetime(s.index).to_period("M").to_timestamp("M")
    f = factors.copy()
    f.index = pd.to_datetime(f.index).to_period("M").to_timestamp("M")

    joined = pd.concat([s.rename("strategy"), f], axis=1).dropna()
    if len(joined) < len(factor_cols) + 5:
        raise ValueError(
            f"need at least {len(factor_cols) + 5} aligned monthly obs; "
            f"got {len(joined)}"
        )

    y = (joined["strategy"] - joined["RF"]).values
    X = joined[factor_cols].values
    X = sm.add_constant(X)
    model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": int(hac_lags)})

    alpha_monthly = float(model.params[0])
    alpha_tstat = float(model.tvalues[0])
    alpha_pvalue = float(model.pvalues[0])
    alpha_annual = float((1.0 + alpha_monthly) ** 12 - 1.0)

    betas = {col: float(model.params[i + 1]) for i, col in enumerate(factor_cols)}
    tstats = {col: float(model.tvalues[i + 1]) for i, col in enumerate(factor_cols)}
    pvalues = {col: float(model.pvalues[i + 1]) for i, col in enumerate(factor_cols)}

    residuals = model.resid
    residual_vol_ann = float(np.std(residuals, ddof=1) * np.sqrt(12))
    ir = float((alpha_monthly * 12) / residual_vol_ann) if residual_vol_ann > 0 else float("nan")

    return FactorRegressionResult(
        alpha_monthly=alpha_monthly,
        alpha_annualized=alpha_annual,
        alpha_tstat=alpha_tstat,
        alpha_pvalue=alpha_pvalue,
        r_squared=float(model.rsquared),
        adj_r_squared=float(model.rsquared_adj),
        n_obs=int(len(joined)),
        factor_betas=betas,
        factor_tstats=tstats,
        factor_pvalues=pvalues,
        residual_vol_annualized=residual_vol_ann,
        information_ratio=ir,
        factors_used=factor_cols,
    )


def regression_summary(res: FactorRegressionResult) -> Dict[str, Any]:
    return {
        "alpha": {
            "monthly": res.alpha_monthly,
            "annualized": res.alpha_annualized,
            "tstat_hac": res.alpha_tstat,
            "pvalue_hac": res.alpha_pvalue,
            "is_significant_5pct": bool(abs(res.alpha_tstat) > 1.96),
        },
        "betas": res.factor_betas,
        "betas_tstats": res.factor_tstats,
        "betas_pvalues": res.factor_pvalues,
        "r_squared": res.r_squared,
        "adj_r_squared": res.adj_r_squared,
        "n_obs": res.n_obs,
        "residual_vol_annualized": res.residual_vol_annualized,
        "information_ratio_annualized": res.information_ratio,
        "factors_used": res.factors_used,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cli(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Fama-French + Momentum factor attribution.")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--ledger", type=Path, help="Daily paper ledger CSV.")
    grp.add_argument("--equity-curve", type=Path, help="Month-end equity curve CSV.")
    ap.add_argument(
        "--factors-csv",
        type=Path,
        default=None,
        help="Pre-saved FF5+Mom factors CSV; if omitted, fetch from Ken French.",
    )
    ap.add_argument("--no-momentum", action="store_true", help="Drop the Mom factor.")
    ap.add_argument("--hac-lags", type=int, default=3)
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.ledger:
        ret = strategy_monthly_returns_from_ledger(args.ledger)
    else:
        ret = strategy_monthly_returns_from_equity_curve(args.equity_curve)

    if args.factors_csv:
        factors = load_factors_csv(args.factors_csv)
    else:
        factors = load_famafrench_monthly(
            start=str(ret.index.min().date()),
            end=str(ret.index.max().date()),
        )

    res = regress_on_factors(ret, factors, use_momentum=not args.no_momentum, hac_lags=args.hac_lags)
    out = regression_summary(res)

    try:
        from src.research.fingerprint import stamp as _stamp_fp

        _stamp_fp(out, config={"args": vars(args), "n_months": int(len(ret))})
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
    raise SystemExit(cli())
