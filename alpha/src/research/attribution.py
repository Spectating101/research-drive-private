"""
Position-level performance attribution for the paper trading ledger.

Decomposes the realized daily P&L into per-holding contributions:

    daily_return(t)  ≈  Σ_i  w_i(t) · r_i(t)

where w_i(t) is the weight held in instrument i on day t (taken from the
active signal that produced the ledger row, i.e. the signal whose as_of_month
is the latest one <= t) and r_i(t) is the daily return of instrument i.

For a long-only multi-asset paper book this gives a clean, directly
interpretable answer to "which positions caused this drawdown?"

If a benchmark is provided we also report Brinson-style allocation /
selection / interaction effects vs that benchmark.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignalSnapshot:
    as_of: pd.Timestamp
    strategy: str
    weights: Dict[str, float]
    source_path: str

    @classmethod
    def from_json(cls, path: Path) -> "SignalSnapshot":
        data = json.loads(Path(path).read_text())
        as_of = pd.to_datetime(data.get("as_of_month"), errors="coerce")
        if pd.isna(as_of):
            raise ValueError(f"signal {path} has no parseable as_of_month")
        return cls(
            as_of=as_of,
            strategy=str(data.get("strategy", path.stem)),
            weights={str(k): float(v) for k, v in data.get("weights", {}).items()},
            source_path=str(path),
        )


def _load_panel_returns(panel_csv: Path) -> pd.DataFrame:
    """Tidy panel (Instrument, Date, Price_Close, ...) -> wide daily returns."""
    df = pd.read_csv(panel_csv)
    cols = {c.lower(): c for c in df.columns}
    inst_col = cols.get("instrument") or "Instrument"
    date_col = cols.get("date") or "Date"
    px_col = cols.get("price_close") or cols.get("close") or "Price_Close"
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])
    wide = df.pivot_table(index=date_col, columns=inst_col, values=px_col, aggfunc="last")
    wide = wide.sort_index()
    return wide.pct_change(fill_method=None)


def _load_signals(signal_paths: Iterable[Path]) -> List[SignalSnapshot]:
    snaps = []
    for p in signal_paths:
        try:
            snaps.append(SignalSnapshot.from_json(Path(p)))
        except (ValueError, json.JSONDecodeError):
            continue
    snaps.sort(key=lambda s: s.as_of)
    return snaps


def _active_signal_for(date: pd.Timestamp, signals: Sequence[SignalSnapshot]) -> Optional[SignalSnapshot]:
    eligible = [s for s in signals if s.as_of <= date]
    return eligible[-1] if eligible else None


# ---------------------------------------------------------------------------
# Core attribution
# ---------------------------------------------------------------------------


@dataclass
class AttributionResult:
    daily_contributions: pd.DataFrame  # rows=date, cols=ticker, values=w*r
    daily_explained: pd.Series  # row sum (≈ ledger daily_return)
    daily_actual: pd.Series  # ledger daily_return for comparison
    by_ticker_total: pd.Series  # sum of daily contributions per ticker
    by_ticker_compound: pd.Series  # log-compounded equivalent
    period_start: pd.Timestamp
    period_end: pd.Timestamp
    n_days: int
    explained_r_squared: float
    active_signals_used: List[str]


def attribute(
    *,
    ledger_csv: Path,
    panel_csv: Path,
    signal_paths: Sequence[Path],
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> AttributionResult:
    """
    Compute per-position attribution over the ledger window.

    start / end : optional ISO dates to restrict the window. Defaults to the
                  full ledger.
    """
    ledger = pd.read_csv(ledger_csv)
    ledger["date"] = pd.to_datetime(ledger["date"])
    ledger = ledger.sort_values("date").set_index("date")
    if start:
        ledger = ledger.loc[pd.Timestamp(start):]
    if end:
        ledger = ledger.loc[:pd.Timestamp(end)]
    if ledger.empty:
        raise ValueError("ledger window is empty after applying start/end")

    rets = _load_panel_returns(panel_csv)
    signals = _load_signals(signal_paths)
    if not signals:
        raise ValueError("no usable signals provided")

    rows = []
    used_signals: List[str] = []
    for d, lr in ledger.iterrows():
        sig = _active_signal_for(d, signals)
        if sig is None:
            continue
        if sig.source_path not in used_signals:
            used_signals.append(sig.source_path)
        if d not in rets.index:
            continue
        today = rets.loc[d]
        row = {t: float(w) * float(today.get(t, np.nan)) for t, w in sig.weights.items()}
        row["_date"] = d
        rows.append(row)

    if not rows:
        raise ValueError("no overlap between ledger dates and panel returns")

    contrib = pd.DataFrame(rows).set_index("_date").fillna(0.0)
    contrib.index.name = "date"
    explained = contrib.sum(axis=1)
    actual = ledger["daily_return"].reindex(contrib.index).astype(float)

    by_ticker_total = contrib.sum(axis=0).sort_values()
    # Compounded: (1 + sum_t contrib_i(t)) approximates total contribution under
    # additive aggregation; for a cleaner geometric reading we use the
    # log-sum-exp trick on (1 + daily contribution) which captures path effects.
    by_ticker_compound = np.expm1(np.log1p(contrib.clip(lower=-0.99)).sum(axis=0)).sort_values()

    # R² between explained and actual: how well do held weights reconstruct
    # the realized daily PnL? Should be very close to 1 in paper trading;
    # gaps reveal mismatches (turnover during the day, dividends, cash drag).
    if actual.notna().sum() >= 3 and actual.std(ddof=0) > 0:
        resid = (actual - explained).var(ddof=0)
        total = actual.var(ddof=0)
        r2 = float(1.0 - resid / total) if total > 0 else float("nan")
    else:
        r2 = float("nan")

    return AttributionResult(
        daily_contributions=contrib,
        daily_explained=explained,
        daily_actual=actual,
        by_ticker_total=by_ticker_total,
        by_ticker_compound=by_ticker_compound,
        period_start=contrib.index.min(),
        period_end=contrib.index.max(),
        n_days=int(len(contrib)),
        explained_r_squared=r2,
        active_signals_used=used_signals,
    )


# ---------------------------------------------------------------------------
# Brinson-style attribution vs a benchmark
# ---------------------------------------------------------------------------


@dataclass
class BrinsonResult:
    allocation: float
    selection: float
    interaction: float
    total_active: float
    by_ticker: pd.DataFrame  # per-ticker allocation/selection/interaction


def brinson(
    *,
    portfolio_weights: Dict[str, float],
    benchmark_weights: Dict[str, float],
    asset_returns: Dict[str, float],
    benchmark_returns_by_asset: Optional[Dict[str, float]] = None,
) -> BrinsonResult:
    """
    Single-period Brinson-Fachler attribution.

    For each asset i:
      allocation_i  = (w_p_i - w_b_i) * r_b_i
      selection_i   = w_b_i * (r_p_i - r_b_i)
      interaction_i = (w_p_i - w_b_i) * (r_p_i - r_b_i)

    If benchmark_returns_by_asset is not provided, we assume r_p_i == r_b_i
    (same asset, same return) which makes selection + interaction collapse to
    zero. That's the right model when the "benchmark" is a fixed allocation
    over the same instruments — only the allocation effect is nonzero.
    """
    tickers = sorted(set(portfolio_weights) | set(benchmark_weights) | set(asset_returns))
    if benchmark_returns_by_asset is None:
        benchmark_returns_by_asset = dict(asset_returns)

    rows = []
    alloc_total = sel_total = inter_total = 0.0
    for t in tickers:
        w_p = float(portfolio_weights.get(t, 0.0))
        w_b = float(benchmark_weights.get(t, 0.0))
        r_p = float(asset_returns.get(t, 0.0))
        r_b = float(benchmark_returns_by_asset.get(t, r_p))
        alloc = (w_p - w_b) * r_b
        sel = w_b * (r_p - r_b)
        inter = (w_p - w_b) * (r_p - r_b)
        alloc_total += alloc
        sel_total += sel
        inter_total += inter
        rows.append({"ticker": t, "allocation": alloc, "selection": sel, "interaction": inter})
    df = pd.DataFrame(rows).set_index("ticker")
    return BrinsonResult(
        allocation=alloc_total,
        selection=sel_total,
        interaction=inter_total,
        total_active=alloc_total + sel_total + inter_total,
        by_ticker=df,
    )


# ---------------------------------------------------------------------------
# Report assembly + CLI
# ---------------------------------------------------------------------------


def attribution_summary(result: AttributionResult) -> Dict[str, Any]:
    """A JSON-serializable summary suitable for stamping into the scorecard."""
    return {
        "period": {
            "start": str(result.period_start.date()),
            "end": str(result.period_end.date()),
            "n_days": result.n_days,
        },
        "explained_r_squared": float(result.explained_r_squared) if np.isfinite(result.explained_r_squared) else None,
        "by_ticker_contribution_sum": {
            str(k): float(v) for k, v in result.by_ticker_total.items()
        },
        "by_ticker_contribution_compound": {
            str(k): float(v) for k, v in result.by_ticker_compound.items()
        },
        "top_5_winners": [
            {"ticker": str(t), "contribution": float(v)}
            for t, v in result.by_ticker_total.sort_values(ascending=False).head(5).items()
        ],
        "top_5_losers": [
            {"ticker": str(t), "contribution": float(v)}
            for t, v in result.by_ticker_total.sort_values(ascending=True).head(5).items()
        ],
        "active_signals_used": result.active_signals_used,
    }


def cli(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Per-position attribution of paper trading ledger."
    )
    ap.add_argument("--ledger", type=Path, required=True)
    ap.add_argument("--panel", type=Path, required=True)
    ap.add_argument(
        "--signal",
        type=Path,
        nargs="+",
        required=True,
        help="One or more signal JSON files (winner-takes-latest by as_of_month).",
    )
    ap.add_argument("--start", type=str, default=None)
    ap.add_argument("--end", type=str, default=None)
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args(argv)

    result = attribute(
        ledger_csv=args.ledger,
        panel_csv=args.panel,
        signal_paths=args.signal,
        start=args.start,
        end=args.end,
    )
    summary = attribution_summary(result)

    try:
        from src.research.fingerprint import stamp as _stamp_fp

        _stamp_fp(
            summary,
            panel_path=args.panel,
            config={
                "ledger": str(args.ledger),
                "signals": [str(s) for s in args.signal],
                "start": args.start,
                "end": args.end,
            },
        )
    except Exception:
        pass

    text = json.dumps(summary, indent=2, default=str)
    print(text)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(text + "\n")
        print(f"\nwrote: {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
