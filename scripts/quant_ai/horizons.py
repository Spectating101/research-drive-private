from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd

from quant_ai.config import AnalystConfig
from quant_ai.pipeline import SHOCKS, country_frame, country_strategies, walkforward_country

Horizon = Literal["1w", "2w", "4w", "monthly"]
TARGET_MAP = {"1w": "fwd_return_1w", "2w": "fwd_return_2w", "4w": "fwd_return_4w"}


@dataclass
class PeriodPerf:
    label: str
    horizon: str
    n_periods: int
    mean_return: float
    median_return: float
    std_return: float
    hit_rate: float
    sharpe: float
    max_drawdown: float
    total_compound: float
    best_period: float
    worst_period: float


def _non_overlapping_step(horizon: str) -> int:
    return {"2w": 2, "4w": 4}.get(horizon, 1)


def _compound_return(r: pd.Series, horizon: str) -> float:
    """Compound without double-counting overlapping multi-week forward labels."""
    step = _non_overlapping_step(horizon)
    sub = r.iloc[::step]
    return float((1.0 + sub).prod()) if not sub.empty else float("nan")


def _perf_series(returns: pd.Series, horizon: str, label: str) -> PeriodPerf:
    r = pd.to_numeric(returns, errors="coerce").dropna()
    if r.empty:
        return PeriodPerf(label, horizon, 0, *[float("nan")] * 9)
    step = _non_overlapping_step(horizon)
    trade_r = r.iloc[::step] if step > 1 else r
    eq = (1.0 + trade_r).cumprod()
    dd = eq / eq.cummax() - 1.0
    vol = float(r.std(ddof=1))
    ann_factor = {"1w": 52, "2w": 26, "4w": 13, "monthly": 12}.get(horizon, 52)
    sharpe = float(r.mean() / vol * math.sqrt(ann_factor)) if vol > 0 else float("nan")
    return PeriodPerf(
        label=label,
        horizon=horizon,
        n_periods=int(len(r)),
        mean_return=float(r.mean()),
        median_return=float(r.median()),
        std_return=vol,
        hit_rate=float((r > 0).mean()),
        sharpe=sharpe,
        max_drawdown=float(dd.min()),
        total_compound=_compound_return(r, horizon),
        best_period=float(r.max()),
        worst_period=float(r.min()),
    )


def weekly_to_monthly_returns(weekly: pd.Series) -> pd.Series:
    s = weekly.copy()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index().fillna(0.0)
    eq = (1.0 + s).cumprod()
    monthly_eq = eq.resample("ME").last().dropna()
    return monthly_eq.pct_change().dropna()


def _walkforward_stocks_target(
    cfg: AnalystConfig,
    symbols: list[str],
    min_train: int,
    alpha: float,
    target: str,
) -> pd.DataFrame:
    """Walk-forward per stock for arbitrary forward-return target."""
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo / "scripts"))
    from run_asia_news_market_modeling_trial import ridge_fit_predict  # noqa: E402

    b = pd.read_parquet(cfg.broadcast_panel)
    b["week_end"] = pd.to_datetime(b["week_end"])
    b = b[(b["country_iso3"] == cfg.country) & (b["yahoo_symbol"].isin(symbols))].copy()
    feat = [f"{s}_per_1k_rows" for s in SHOCKS if f"{s}_per_1k_rows" in b.columns]
    weeks = sorted(b["week_end"].dropna().unique())
    pred_rows = []
    for i, week in enumerate(weeks):
        if i < min_train:
            continue
        train = b[b["week_end"] < week]
        test = b[b["week_end"] == week]
        if len(test) < 5 or target not in test.columns:
            continue
        for sym, grp in test.groupby("yahoo_symbol"):
            tr = train[train["yahoo_symbol"] == sym]
            if len(tr) < 30:
                continue
            p = ridge_fit_predict(tr, grp, feat, target, alpha)
            pred_rows.append(
                {
                    "week_end": week,
                    "yahoo_symbol": sym,
                    target: float(grp[target].iloc[0]),
                    "pred": float(p[0]),
                }
            )
    return pd.DataFrame(pred_rows)


def _stock_strategies_for_target(preds: pd.DataFrame, target: str, prefix: str) -> dict[str, pd.Series]:
    weekly = []
    pred_col = "pred"
    for week, g in preds.groupby("week_end"):
        sub = g.dropna(subset=[target, pred_col])
        if len(sub) < 6:
            continue
        k = max(1, len(sub) // 3)
        weekly.append(
            {
                "week_end": week,
                "eq": float(sub[target].mean()),
                "top": float(sub.nlargest(k, pred_col)[target].mean()),
            }
        )
    w = pd.DataFrame(weekly)
    if w.empty:
        return {}
    w["week_end"] = pd.to_datetime(w["week_end"])
    w = w.set_index("week_end")
    return {
        f"{prefix}_stocks_equal_weight": w["eq"],
        f"{prefix}_stocks_top_tercile": w["top"],
    }


def build_horizon_returns(
    cfg: AnalystConfig,
    horizon: Horizon,
    oos_start: str = "2024-01-01",
    universe_asof: str | None = "2023-12-31",
) -> dict[str, pd.Series]:
    """Build strategy return series at requested horizon (weekly-native or monthly agg)."""
    prefix = cfg.country.lower()
    if horizon == "monthly":
        weekly = build_horizon_returns(cfg, "1w", oos_start, universe_asof)
        return {k: weekly_to_monthly_returns(v) for k, v in weekly.items() if not v.dropna().empty}

    target = TARGET_MAP[horizon]
    symbols = stock_universe(cfg) if universe_asof is None else _universe_asof(cfg, universe_asof)
    stock_preds = _walkforward_stocks_target(cfg, symbols, cfg.min_train_weeks, cfg.ridge_alpha, target)
    strategies = _stock_strategies_for_target(stock_preds, target, prefix)

    if horizon == "1w":
        country = country_frame(cfg)
        wf = walkforward_country(country, cfg.min_train_weeks, cfg.ridge_alpha)
        strategies.update(country_strategies(wf, prefix))
    return strategies


def _universe_asof(cfg: AnalystConfig, asof: str) -> list[str]:
    b = pd.read_parquet(cfg.broadcast_panel, columns=["yahoo_symbol", "country_iso3", "row_count_daily", "week_end"])
    b["week_end"] = pd.to_datetime(b["week_end"])
    cutoff = pd.Timestamp(asof)
    sub = b[(b["country_iso3"] == cfg.country) & (b["week_end"] <= cutoff)]
    top = sub.groupby("yahoo_symbol")["row_count_daily"].median().sort_values(ascending=False)
    return top.head(cfg.stock_universe).index.tolist()


def split_sample(series: pd.Series, oos_start: str) -> tuple[pd.Series, pd.Series]:
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    cut = pd.Timestamp(oos_start)
    return s[s.index < cut], s[s.index >= cut]


def horizon_report(
    cfg: AnalystConfig,
    horizons: list[Horizon] | None = None,
    oos_start: str = "2024-01-01",
    universe_asof: str | None = "2023-12-31",
) -> list[dict]:
    horizons = horizons or ["1w", "2w", "4w", "monthly"]
    rows: list[dict] = []
    for hz in horizons:
        strategies = build_horizon_returns(cfg, hz, oos_start, universe_asof)
        for name, ser in strategies.items():
            if ser is None or ser.dropna().empty:
                continue
            is_s, oos_s = split_sample(ser, oos_start)
            for sub, label in [(ser.dropna(), "full"), (is_s.dropna(), "is_pre2024"), (oos_s.dropna(), "oos_from2024")]:
                if sub.empty:
                    continue
                p = _perf_series(sub, hz, f"{name}|{label}")
                row = asdict(p)
                row["strategy"] = name
                row["sample"] = label
                rows.append(row)
    return rows


def format_report_table(rows: list[dict], focus: str | None = "equal_weight") -> str:
    lines = [
        "horizon | sample       | strategy                     |  n | mean%/period | hit% | sharpe | maxDD  | $1→",
        "-" * 100,
    ]
    for r in rows:
        strat = r["strategy"]
        if focus and focus not in strat and "buy_hold" not in strat and "top_tercile" not in strat:
            continue
        mean_pct = r["mean_return"] * 100
        lines.append(
            f"{r['horizon']:7} | {r['sample']:12} | {strat:28} | {r['n_periods']:3} | "
            f"{mean_pct:+7.2f}% | {r['hit_rate']*100:4.0f}% | {r['sharpe']:6.2f} | "
            f"{r['max_drawdown']*100:5.1f}% | {r['total_compound']:5.2f}x"
        )
    return "\n".join(lines)
