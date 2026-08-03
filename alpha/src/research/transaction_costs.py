"""
Transaction-cost model for the paper trading ledger.

Two components:

1. **Spread + commission** — a flat per-asset bps charge. The bps schedule
   is configurable; sensible defaults reflect liquid-ETF execution (~5 bps)
   vs crypto (~25 bps) vs cash (~1 bps).

2. **Square-root market impact** — c · σ · √(participation_rate), where
   participation = trade_notional / (price · ADV). Captures the fact that
   pushing $10k through a thin coin moves the print, while $10k through
   SPY does not. The coefficient `c` defaults to 1.0 (standard market-impact
   literature, e.g. Almgren et al. 2005). Set c=0 to disable impact.

A rebalance is detected by a *change* in the ledger's `as_of` column. On
each rebalance date we recover the turnover `Σ_i |w_new_i - w_old_i|`,
charge cost per leg, and subtract the dollar charge from that day's equity.

The output is a gross-vs-net scorecard comparison: how much of the
realized return survives once realistic execution is priced in.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from src.research.attribution import SignalSnapshot, _load_signals


# ---------------------------------------------------------------------------
# Cost configuration
# ---------------------------------------------------------------------------


# Per-asset spread+commission in basis points (paid each side of a trade).
DEFAULT_SPREAD_BPS_BY_TICKER: Dict[str, float] = {
    # Cash-like
    "BIL": 1.0,
    "SHV": 1.0,
    "SHY": 1.5,
    # Broad equity ETFs
    "SPY": 1.5,
    "IWM": 2.5,
    "EFA": 3.0,
    "EEM": 4.0,
    "QQQ": 1.5,
    # Sector / commodity / real estate
    "GLD": 3.0,
    "DBC": 6.0,
    "VNQ": 4.0,
    "TLT": 2.5,
    # Crypto (proxy ETFs / spot)
    "BTC-USD": 25.0,
    "ETH-USD": 25.0,
    "BITO": 12.0,
    "ETHE": 30.0,
}

# Asset-class fallbacks if the ticker isn't in the table above.
_DEFAULT_BPS_BY_CLASS = {
    "crypto": 25.0,
    "etf": 5.0,
    "equity": 10.0,
    "cash": 1.0,
    "unknown": 8.0,
}


def _classify(ticker: str) -> str:
    t = ticker.upper()
    if t.endswith("-USD") or t in {"BTC", "ETH", "BITO", "ETHE"}:
        return "crypto"
    if t in {"BIL", "SHV", "SHY"}:
        return "cash"
    if t in {"SPY", "IWM", "QQQ", "EFA", "EEM", "GLD", "DBC", "VNQ", "TLT"}:
        return "etf"
    return "unknown"


def spread_bps(ticker: str, overrides: Optional[Mapping[str, float]] = None) -> float:
    if overrides and ticker in overrides:
        return float(overrides[ticker])
    if ticker in DEFAULT_SPREAD_BPS_BY_TICKER:
        return DEFAULT_SPREAD_BPS_BY_TICKER[ticker]
    return _DEFAULT_BPS_BY_CLASS[_classify(ticker)]


@dataclass(frozen=True)
class CostConfig:
    """Knobs for the cost model. All defaults are conservative for paper accounts."""

    spread_bps_overrides: Mapping[str, float] = field(default_factory=dict)
    impact_coefficient: float = 1.0  # c in c·σ·√participation
    impact_lookback_days: int = 20  # window for σ and ADV
    min_charge_bps: float = 0.0  # floor (e.g., to model min commission)
    # If ADV unavailable for an asset, fall back to this many dollars/day to
    # avoid silently zeroing impact:
    fallback_adv_dollars: float = 1_000_000.0


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradeCost:
    ticker: str
    notional: float
    spread_cost: float
    impact_cost: float
    total_cost: float
    spread_bps_applied: float
    impact_bps_applied: float


def estimate_trade_cost(
    *,
    ticker: str,
    notional: float,
    price: float,
    sigma_daily: float,
    adv_dollars: float,
    config: CostConfig,
) -> TradeCost:
    """
    Estimate one-sided execution cost for a single trade.

    notional      : dollar value being bought OR sold (signed magnitude is irrelevant)
    sigma_daily   : daily return volatility of the asset
    adv_dollars   : average daily dollar volume
    """
    n = abs(float(notional))
    if n == 0:
        return TradeCost(ticker, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    bps = spread_bps(ticker, config.spread_bps_overrides)
    spread = n * bps / 10_000.0

    # Square-root market impact: cost_$ = c · σ · √(participation) · n
    adv = max(float(adv_dollars), config.fallback_adv_dollars)
    participation = n / adv
    impact_frac = config.impact_coefficient * float(sigma_daily) * math.sqrt(max(participation, 0.0))
    impact = n * impact_frac
    impact_bps = impact_frac * 10_000.0

    floor = n * config.min_charge_bps / 10_000.0
    total = max(spread + impact, floor)

    return TradeCost(
        ticker=ticker,
        notional=n,
        spread_cost=float(spread),
        impact_cost=float(impact),
        total_cost=float(total),
        spread_bps_applied=float(bps),
        impact_bps_applied=float(impact_bps),
    )


# ---------------------------------------------------------------------------
# Rebalance detection + ledger-level cost application
# ---------------------------------------------------------------------------


def _ticker_stats(panel_csv: Path, *, lookback_days: int) -> Dict[str, Dict[str, float]]:
    """Per-ticker daily sigma and ADV ($) from the last `lookback_days` of panel."""
    df = pd.read_csv(panel_csv)
    cols = {c.lower(): c for c in df.columns}
    inst = cols.get("instrument") or "Instrument"
    date = cols.get("date") or "Date"
    px = cols.get("price_close") or "Price_Close"
    vol = cols.get("volume") or "Volume"
    df[date] = pd.to_datetime(df[date], errors="coerce")
    df = df.dropna(subset=[date])
    out: Dict[str, Dict[str, float]] = {}
    for tkr, g in df.groupby(inst):
        g = g.sort_values(date).tail(lookback_days + 1)
        if len(g) < 5:
            continue
        prices = g[px].astype(float).values
        rets = np.diff(prices) / prices[:-1]
        sigma = float(np.std(rets, ddof=1)) if rets.size >= 2 else 0.0
        last_px = float(prices[-1])
        if vol in g.columns:
            vols = g[vol].astype(float).values[1:]
            avg_volume = float(np.mean(vols)) if vols.size else 0.0
        else:
            avg_volume = 0.0
        adv_dollars = avg_volume * last_px
        out[str(tkr)] = {
            "sigma_daily": sigma,
            "last_price": last_px,
            "adv_dollars": adv_dollars,
        }
    return out


@dataclass
class CostedLedger:
    gross_ledger: pd.DataFrame  # original ledger
    net_ledger: pd.DataFrame  # daily_return adjusted for rebalance charges
    per_rebalance_costs: pd.DataFrame  # date, total_cost_$, total_cost_bps, turnover
    per_trade_costs: pd.DataFrame  # date, ticker, notional, costs
    summary: Dict[str, Any]


def cost_adjust_ledger(
    *,
    ledger_csv: Path,
    panel_csv: Path,
    signal_paths: Sequence[Path],
    config: Optional[CostConfig] = None,
    initial_equity: Optional[float] = None,
) -> CostedLedger:
    """
    Charge realistic spread + impact costs at each detected rebalance date,
    returning gross-vs-net daily ledgers and a per-rebalance breakdown.
    """
    cfg = config or CostConfig()
    ledger = pd.read_csv(ledger_csv)
    ledger["date"] = pd.to_datetime(ledger["date"])
    ledger = ledger.sort_values("date").reset_index(drop=True)
    if initial_equity is None:
        initial_equity = float(ledger["equity"].iloc[0]) / (1.0 + float(ledger["daily_return"].iloc[0]))

    signals = _load_signals(signal_paths)
    stats = _ticker_stats(panel_csv, lookback_days=cfg.impact_lookback_days)

    # Rebalance dates: rows where `as_of` differs from the previous row.
    as_of = ledger["as_of"].astype(str)
    rebalance_mask = as_of.ne(as_of.shift(1)).fillna(True)
    # The very first row of the ledger always counts as an "initial allocation"
    # — charge cost for the full starting weights.
    rebalance_dates = ledger.loc[rebalance_mask, "date"].tolist()

    trade_rows: List[Dict[str, Any]] = []
    reb_rows: List[Dict[str, Any]] = []
    prev_weights: Dict[str, float] = {}
    running_equity = initial_equity

    for d in rebalance_dates:
        # signals is sorted ascending by as_of; we want the latest eligible.
        eligible = [s for s in signals if s.as_of <= d]
        snap = eligible[-1] if eligible else None
        # If the ledger has rebalances we have no signal for, skip costlessly.
        if snap is None:
            continue
        new_w = snap.weights
        # Use equity at end of the day before this rebalance as the trading book.
        prior = ledger.loc[ledger["date"] < d]
        book = float(prior["equity"].iloc[-1]) if not prior.empty else running_equity

        tickers = sorted(set(prev_weights) | set(new_w))
        per_reb_total = 0.0
        turnover = 0.0
        for t in tickers:
            delta = float(new_w.get(t, 0.0)) - float(prev_weights.get(t, 0.0))
            notional = abs(delta) * book
            if notional == 0:
                continue
            turnover += abs(delta)
            st = stats.get(t, {"sigma_daily": 0.02, "last_price": 100.0,
                               "adv_dollars": cfg.fallback_adv_dollars})
            cost = estimate_trade_cost(
                ticker=t,
                notional=notional,
                price=st["last_price"],
                sigma_daily=st["sigma_daily"],
                adv_dollars=st["adv_dollars"],
                config=cfg,
            )
            per_reb_total += cost.total_cost
            trade_rows.append(
                {
                    "date": d,
                    "ticker": t,
                    "notional": notional,
                    "delta_weight": delta,
                    "spread_cost": cost.spread_cost,
                    "impact_cost": cost.impact_cost,
                    "total_cost": cost.total_cost,
                    "spread_bps": cost.spread_bps_applied,
                    "impact_bps": cost.impact_bps_applied,
                }
            )
        reb_rows.append(
            {
                "date": d,
                "as_of": snap.as_of,
                "book_equity": book,
                "turnover_weight": turnover,
                "total_cost_$": per_reb_total,
                "total_cost_bps": (per_reb_total / book * 10_000.0) if book > 0 else 0.0,
            }
        )
        prev_weights = dict(new_w)

    per_reb = pd.DataFrame(reb_rows)
    per_trade = pd.DataFrame(trade_rows)

    # Apply costs: on each rebalance date, subtract the cost from that day's
    # equity. Recompute daily_return + cumulative net equity from there.
    net = ledger.copy()
    net["cost_charge_$"] = 0.0
    if not per_reb.empty:
        cost_by_date = per_reb.set_index("date")["total_cost_$"]
        for d, c in cost_by_date.items():
            mask = net["date"] == d
            if mask.any():
                net.loc[mask, "cost_charge_$"] = float(c)

    # Reconstruct net equity from gross daily return + cost charges.
    net["net_equity"] = float(initial_equity)
    prev_eq = float(initial_equity)
    for i, row in net.iterrows():
        gross_growth = 1.0 + float(row.get("daily_return", 0.0))
        eq_after_market = prev_eq * gross_growth
        eq_after_costs = eq_after_market - float(row["cost_charge_$"])
        net.at[i, "net_equity"] = eq_after_costs
        prev_eq = eq_after_costs
    net["net_daily_return"] = net["net_equity"].pct_change()
    net.loc[net.index[0], "net_daily_return"] = net["net_equity"].iloc[0] / initial_equity - 1.0

    # Summary
    gross_total = float(ledger["equity"].iloc[-1] / initial_equity - 1.0) if not ledger.empty else 0.0
    net_total = float(net["net_equity"].iloc[-1] / initial_equity - 1.0) if not net.empty else 0.0
    cost_drag = gross_total - net_total
    summary = {
        "initial_equity": float(initial_equity),
        "gross_total_return": gross_total,
        "net_total_return": net_total,
        "cost_drag": cost_drag,
        "n_rebalances": int(len(per_reb)),
        "total_cost_$": float(per_reb["total_cost_$"].sum()) if not per_reb.empty else 0.0,
        "avg_rebalance_cost_bps": float(per_reb["total_cost_bps"].mean()) if not per_reb.empty else 0.0,
        "config": {
            "impact_coefficient": cfg.impact_coefficient,
            "impact_lookback_days": cfg.impact_lookback_days,
            "min_charge_bps": cfg.min_charge_bps,
            "fallback_adv_dollars": cfg.fallback_adv_dollars,
        },
    }
    return CostedLedger(gross_ledger=ledger, net_ledger=net, per_rebalance_costs=per_reb,
                        per_trade_costs=per_trade, summary=summary)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cli(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Apply transaction costs to the paper ledger.")
    ap.add_argument("--ledger", type=Path, required=True)
    ap.add_argument("--panel", type=Path, required=True)
    ap.add_argument("--signal", type=Path, nargs="+", required=True)
    ap.add_argument("--impact-coef", type=float, default=1.0)
    ap.add_argument("--lookback", type=int, default=20)
    ap.add_argument("--out-json", type=Path, default=None)
    ap.add_argument("--out-net-ledger", type=Path, default=None)
    args = ap.parse_args(argv)

    cfg = CostConfig(impact_coefficient=args.impact_coef, impact_lookback_days=args.lookback)
    res = cost_adjust_ledger(
        ledger_csv=args.ledger,
        panel_csv=args.panel,
        signal_paths=args.signal,
        config=cfg,
    )
    out = dict(res.summary)
    out["per_rebalance"] = res.per_rebalance_costs.to_dict(orient="records") if not res.per_rebalance_costs.empty else []

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
    if args.out_net_ledger:
        args.out_net_ledger.parent.mkdir(parents=True, exist_ok=True)
        res.net_ledger.to_csv(args.out_net_ledger, index=False)
        print(f"wrote: {args.out_net_ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
