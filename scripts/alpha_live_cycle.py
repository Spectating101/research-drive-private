#!/usr/bin/env python3
from __future__ import annotations

"""
One-command "live" cycle using yfinance (paper/evaluation).

Steps:
  1) Fetch latest daily bars via yfinance into a tidy panel CSV
  2) Build/update an alpha feature cache (insights + event-proxy)
  3) Export latest month-end weights to signal.json
  4) Update a daily mark-to-market ledger to evaluate if picks are working

This does not place real orders.
"""

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

SR_ROOT = Path(__file__).resolve().parents[1]
if str(SR_ROOT) not in sys.path:
    sys.path.insert(0, str(SR_ROOT))

from trading.data.providers.base import BarsRequest  # noqa: E402
from trading.data.providers.yfinance_provider import YFinanceProvider  # noqa: E402

from scripts.alpha_insights_walkforward_runner import (  # noqa: E402
    build_feature_panel,
    daily_close_wide,
    daily_volume_wide,
    load_panel,
    monthly_close_and_returns,
    _load_manual_events,
    walkforward_backtest,
)
from scripts.alpha_daily_scorecard import build_scorecard, write_outputs  # noqa: E402
from src.strategy.control_profiles import apply_profile_to_namespace, profiles_json  # noqa: E402


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_tickers_file(path: Path) -> list[str]:
    tickers: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        tickers.append(line.split()[0].strip())
    # Preserve order but dedupe
    out: list[str] = []
    seen: set[str] = set()
    for t in tickers:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def build_tidy_panel_from_bars(bars: pd.DataFrame) -> pd.DataFrame:
    bars = bars.copy()
    bars["Date"] = pd.to_datetime(bars["timestamp"], errors="coerce").dt.tz_localize(None)
    out = pd.DataFrame(
        {
            "Instrument": bars["symbol"].astype(str),
            "Date": bars["Date"],
            "Price_Close": pd.to_numeric(bars["close"], errors="coerce"),
            "Volume": pd.to_numeric(bars.get("volume"), errors="coerce") if "volume" in bars.columns else pd.NA,
        }
    ).dropna(subset=["Instrument", "Date", "Price_Close"])
    out = out.sort_values(["Instrument", "Date"]).reset_index(drop=True)
    return out


def _as_float_map(series: pd.Series) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for k, v in series.items():
        try:
            fv = float(v)
        except Exception:
            continue
        if not np.isfinite(fv) or fv == 0.0:
            continue
        out[str(k)] = float(fv)
    return out


def _panel_freshness(panel_csv: Path, *, reference_time: Optional[datetime] = None) -> Dict[str, Any]:
    df = pd.read_csv(panel_csv, usecols=["Instrument", "Date"])
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Instrument", "Date"])
    if df.empty:
        raise ValueError(f"Panel is empty: {panel_csv}")
    latest = pd.Timestamp(df["Date"].max()).tz_localize(None)
    earliest = pd.Timestamp(df["Date"].min()).tz_localize(None)
    ref_ts = pd.Timestamp(reference_time or _utc_now()).tz_localize(None)
    age_days = int((ref_ts.normalize() - latest.normalize()).days)
    return {
        "path": str(panel_csv),
        "earliest_date": str(earliest.date()),
        "latest_date": str(latest.date()),
        "age_days": int(age_days),
        "n_rows": int(len(df)),
        "n_instruments": int(df["Instrument"].astype(str).nunique()),
    }


def _write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _readiness_report(
    *,
    panel_info: Dict[str, Any],
    signal: Dict[str, Any],
    score: Dict[str, Any],
    max_panel_staleness_days: int,
    min_ledger_days: int,
    min_sharpe: float,
    max_drawdown: float,
    min_alpha_30d: float,
) -> Dict[str, Any]:
    perf = score.get("performance", {}) or {}
    benchmark = score.get("benchmark", {}) or {}
    period = score.get("period", {}) or {}
    signal_as_of = pd.to_datetime(signal.get("as_of_month"), errors="coerce")
    latest_panel = pd.to_datetime(panel_info.get("latest_date"), errors="coerce")
    signal_lag_days = None
    if not pd.isna(signal_as_of) and not pd.isna(latest_panel):
        signal_lag_days = int((latest_panel.normalize() - signal_as_of.normalize()).days)

    sharpe = float(perf.get("sharpe_daily_252", float("nan")))
    latest_dd = float(perf.get("latest_drawdown", float("nan")))
    max_dd_seen = float(perf.get("max_drawdown_from_ledger", float("nan")))
    alpha_30d = benchmark.get("alpha_30d")
    alpha_ok = True if alpha_30d is None else bool(float(alpha_30d) >= float(min_alpha_30d))

    checks = {
        "panel_fresh": int(panel_info.get("age_days", 999999)) <= int(max_panel_staleness_days),
        "enough_ledger_history": int(period.get("n_days", 0)) >= int(min_ledger_days),
        "positive_sharpe": bool(math.isfinite(sharpe) and sharpe >= float(min_sharpe)),
        "drawdown_ok": bool(math.isfinite(latest_dd) and latest_dd >= -abs(float(max_drawdown))),
        "max_drawdown_ok": bool(math.isfinite(max_dd_seen) and max_dd_seen >= -abs(float(max_drawdown))),
        "alpha_ok": alpha_ok,
    }
    if signal_lag_days is not None:
        checks["signal_not_ahead_of_panel"] = signal_lag_days >= 0

    if all(checks.values()):
        status = "ready"
    elif checks["panel_fresh"] and checks["enough_ledger_history"]:
        status = "caution"
    else:
        status = "blocked"

    return {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "status": status,
        "checks": checks,
        "panel": panel_info,
        "signal": {
            "path": score.get("positioning", {}).get("signal_path"),
            "as_of_month": signal.get("as_of_month"),
            "strategy": signal.get("strategy"),
            "n_weights": int(len(signal.get("weights", {}) or {})),
            "signal_lag_days_vs_panel": signal_lag_days,
        },
        "performance": {
            "period_days": int(period.get("n_days", 0)),
            "cagr_since_start": perf.get("cagr_since_start"),
            "sharpe_daily_252": perf.get("sharpe_daily_252"),
            "sortino_daily_252": perf.get("sortino_daily_252"),
            "latest_drawdown": perf.get("latest_drawdown"),
            "max_drawdown_from_ledger": perf.get("max_drawdown_from_ledger"),
            "return_30d": perf.get("return_30d"),
            "win_rate_30d": perf.get("win_rate_30d"),
            "alpha_30d": alpha_30d,
        },
        "thresholds": {
            "max_panel_staleness_days": int(max_panel_staleness_days),
            "min_ledger_days": int(min_ledger_days),
            "min_sharpe": float(min_sharpe),
            "max_drawdown": float(max_drawdown),
            "min_alpha_30d": float(min_alpha_30d),
        },
    }


def _readiness_markdown(report: Dict[str, Any]) -> str:
    perf = report.get("performance", {}) or {}
    panel = report.get("panel", {}) or {}
    signal = report.get("signal", {}) or {}
    checks = report.get("checks", {}) or {}
    lines = [
        "# Alpha Edge Readiness",
        "",
        f"- status: `{report.get('status')}`",
        f"- generated_at: `{report.get('generated_at')}`",
        f"- panel_latest_date: `{panel.get('latest_date')}` age_days=`{panel.get('age_days')}` instruments=`{panel.get('n_instruments')}`",
        f"- signal_as_of_month: `{signal.get('as_of_month')}` lag_days_vs_panel=`{signal.get('signal_lag_days_vs_panel')}`",
        f"- period_days: `{perf.get('period_days')}` sharpe=`{perf.get('sharpe_daily_252')}` alpha_30d=`{perf.get('alpha_30d')}`",
        f"- latest_drawdown: `{perf.get('latest_drawdown')}` max_drawdown_from_ledger=`{perf.get('max_drawdown_from_ledger')}`",
        "",
        "## Checks",
        "",
    ]
    for name, ok in checks.items():
        lines.append(f"- {name}: `{ok}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Alpha live cycle (yfinance -> signal -> paper ledger).")
    ap.add_argument(
        "--tickers-file",
        type=Path,
        default=SR_ROOT / "config" / "tickers_multi_asset_core.txt",
    )
    ap.add_argument(
        "--panel-out",
        type=Path,
        default=SR_ROOT / "data_lake" / "daily_alpha_panel.csv",
    )
    ap.add_argument("--skip-fetch", action="store_true", help="Reuse an existing panel instead of pulling fresh yfinance bars.")
    ap.add_argument("--interval", type=str, default="1d")
    ap.add_argument("--lookback-days", type=int, default=365 * 10)
    ap.add_argument("--max-panel-staleness-days", type=int, default=5)
    ap.add_argument("--strict-freshness", action="store_true", help="Fail if the panel is older than --max-panel-staleness-days.")

    ap.add_argument("--feature-cache", type=Path, default=SR_ROOT / "backtests" / "outputs" / "alpha_feature_cache" / "daily_alpha_features.parquet")
    ap.add_argument("--signal-out", type=Path, default=SR_ROOT / "backtests" / "outputs" / "signals" / "alpha_live_signal.json")
    ap.add_argument("--ledger", type=Path, default=SR_ROOT / "backtests" / "outputs" / "alpha_paper" / "ledger.csv")
    ap.add_argument("--scorecard-out-dir", type=Path, default=SR_ROOT / "backtests" / "outputs" / "alpha_paper")
    ap.add_argument("--scorecard-history-csv", type=Path, default=SR_ROOT / "backtests" / "outputs" / "alpha_paper" / "scorecard_history.csv")
    ap.add_argument("--edge-report-json", type=Path, default=SR_ROOT / "backtests" / "outputs" / "alpha_paper" / "edge_readiness_latest.json")
    ap.add_argument("--edge-report-md", type=Path, default=SR_ROOT / "backtests" / "outputs" / "alpha_paper" / "edge_readiness_latest.md")
    ap.add_argument("--initial-equity", type=float, default=10_000.0)
    ap.add_argument(
        "--manual-events",
        type=Path,
        default=SR_ROOT / "data_lake" / "manual_events.csv",
        help="Optional manual events CSV (Date,Score[,Tickers,Event,Horizon_Days]). If missing, ignored.",
    )

    # Strategy defaults: improved cfg12 (event-proxy enabled in feature build).
    ap.add_argument("--benchmark", type=str, default="SPY")
    ap.add_argument("--cash-ticker", type=str, default="BIL")
    ap.add_argument("--train-months", type=int, default=48)
    ap.add_argument("--top-n", type=int, default=4)
    ap.add_argument("--max-weight", type=float, default=0.30)
    ap.add_argument("--cost-bps", type=float, default=20.0)
    ap.add_argument("--lam-grid", nargs="*", type=float, default=[0.01, 0.1, 1.0, 10.0, 100.0])
    ap.add_argument("--min-assets", type=int, default=4)
    ap.add_argument("--target-vol", type=float, default=0.20)
    ap.add_argument("--vol-lookback", type=int, default=12)
    ap.add_argument("--max-gross", type=float, default=1.25)
    ap.add_argument("--allow-leverage", action="store_true")
    ap.add_argument("--regime-filter", action="store_true")
    ap.add_argument("--regime-window", type=int, default=12)
    ap.add_argument("--regime-off-gross", type=float, default=0.35)
    ap.add_argument("--base", choices=["cash", "benchmark", "trend"], default="trend")
    ap.add_argument("--alpha-mode", choices=["fixed", "ic_tstat"], default="ic_tstat")
    ap.add_argument("--ic-months", type=int, default=12)
    ap.add_argument("--alpha-tstat-scale", type=float, default=1.5)
    ap.add_argument("--corr-filter", action="store_true")
    ap.add_argument("--corr-threshold", type=float, default=0.65)
    ap.add_argument("--corr-lookback", type=int, default=6)
    ap.add_argument("--risk-budget", action="store_true")
    ap.add_argument("--max-turnover", type=float, default=0.75)
    ap.add_argument("--pf-dd-threshold", type=float, default=0.2)
    ap.add_argument("--pf-dd-floor-gross", type=float, default=0.50)
    ap.add_argument(
        "--control-profile",
        choices=["custom", "off", "growth", "balanced", "defensive"],
        default="growth",
        help="Named control preset. If not custom, overrides manual sleeve/circuit knobs.",
    )
    ap.add_argument("--print-control-profiles", action="store_true", help="Print built-in control profiles as JSON and exit.")
    ap.add_argument("--min-cash-weight", type=float, default=0.10, help="Minimum cash sleeve for tighter risk control.")
    ap.add_argument("--max-crypto-gross", type=float, default=0.45, help="Maximum aggregate crypto sleeve gross.")
    ap.add_argument("--cb-dd-trigger", type=float, default=0.10, help="Circuit breaker DD trigger; 0 disables.")
    ap.add_argument("--cb-alpha-trigger", type=float, default=-0.015, help="Circuit breaker trigger on trailing active return.")
    ap.add_argument("--cb-alpha-window", type=int, default=3, help="Trailing months for active-return circuit trigger.")
    ap.add_argument("--cb-cooldown-months", type=int, default=2, help="Months to keep circuit breaker active once triggered.")
    ap.add_argument("--cb-floor-gross", type=float, default=0.30, help="Risky gross cap while circuit breaker is active.")
    ap.add_argument("--auto-params", action="store_true", help="Enable mechanical regime policy for parameter adaptation.")
    ap.add_argument("--policy-window", type=int, default=12, help="Months used for regime policy features.")
    ap.add_argument("--readiness-min-ledger-days", type=int, default=30)
    ap.add_argument("--readiness-min-sharpe", type=float, default=0.0)
    ap.add_argument("--readiness-max-drawdown", type=float, default=0.20)
    ap.add_argument("--readiness-min-alpha-30d", type=float, default=-0.02)
    args = ap.parse_args()

    if bool(args.print_control_profiles):
        print(profiles_json())
        return 0
    if str(args.control_profile) != "custom":
        apply_profile_to_namespace(args, str(args.control_profile))

    tickers = _parse_tickers_file(Path(args.tickers_file))
    if not tickers:
        raise SystemExit("No tickers parsed.")

    if bool(args.skip_fetch):
        if not args.panel_out.exists():
            raise SystemExit(f"--skip-fetch requested but panel does not exist: {args.panel_out}")
    else:
        end = _utc_now()
        start = end - timedelta(days=int(args.lookback_days))
        provider = YFinanceProvider()
        bars = provider.fetch_bars(BarsRequest(symbols=tickers, start=start, end=end, interval=str(args.interval)))
        if bars.empty:
            raise SystemExit("No bars returned by yfinance provider.")

        panel = build_tidy_panel_from_bars(bars)
        args.panel_out.parent.mkdir(parents=True, exist_ok=True)
        panel.to_csv(args.panel_out, index=False)

    panel_info = _panel_freshness(args.panel_out)
    if bool(args.strict_freshness) and int(panel_info["age_days"]) > int(args.max_panel_staleness_days):
        raise SystemExit(
            f"Panel is stale: latest_date={panel_info['latest_date']} age_days={panel_info['age_days']} > "
            f"max_panel_staleness_days={int(args.max_panel_staleness_days)}"
        )

    # Build features (insights + event-proxy) from the freshly-updated panel.
    panel_loaded = load_panel(args.panel_out)
    close_d = daily_close_wide(panel_loaded)
    volume_d = daily_volume_wide(panel_loaded)
    if args.cash_ticker and args.cash_ticker not in close_d.columns:
        close_d[str(args.cash_ticker)] = 1.0
        if volume_d is not None:
            volume_d[str(args.cash_ticker)] = 0.0
    close_m, ret_m = monthly_close_and_returns(close_d)

    # Ensure enough months for the training window.
    available_months = int(len(close_m.index.dropna()))
    # walkforward_backtest requires >= train_months + 6 months.
    max_train = int(available_months - 6)
    if max_train < 12:
        raise SystemExit(
            f"Not enough monthly data: have {available_months} months; need at least 18 months. "
            f"Increase --lookback-days (recommended >= {365*6})."
        )
    if int(args.train_months) > max_train:
        args.train_months = int(max_train)
        print(f"[info] shrinking train window to {args.train_months} months (available months={available_months})")

    manual_df = None
    try:
        if args.manual_events and Path(args.manual_events).exists():
            manual_df = _load_manual_events(Path(args.manual_events))
    except Exception:
        manual_df = None

    feats = build_feature_panel(
        panel_loaded,
        close_d=close_d,
        volume_d=volume_d,
        close_m=close_m,
        ret_m=ret_m,
        lookback_days=365,
        use_insights=True,
        reddit_sentiment=None,
        reddit_lookback_days=30,
        sec_events=None,
        sec_lookback_days=365,
        sec_half_life_days=45,
        event_proxy=True,
        event_lookback_days=21,
        volz_days=60,
        manual_events=manual_df,
    )
    args.feature_cache.parent.mkdir(parents=True, exist_ok=True)
    if args.feature_cache.suffix.lower() == ".parquet":
        feats.to_parquet(args.feature_cache, index=False)
    else:
        feats.to_csv(args.feature_cache, index=False)

    res = walkforward_backtest(
        feats,
        ret_m=ret_m,
        benchmark=str(args.benchmark),
        train_months=int(args.train_months),
        top_n=int(args.top_n),
        max_weight=float(args.max_weight),
        cash_ticker=str(args.cash_ticker) if args.cash_ticker else None,
        cost_bps=float(args.cost_bps),
        lam_grid=[float(x) for x in args.lam_grid],
        min_assets=int(args.min_assets),
        target_vol=float(args.target_vol),
        vol_lookback=int(args.vol_lookback),
        max_gross=float(args.max_gross),
        allow_leverage=bool(args.allow_leverage),
        regime_filter=bool(args.regime_filter),
        regime_window=int(args.regime_window),
        regime_off_gross=float(args.regime_off_gross),
        base=str(args.base),
        alpha_mode=str(args.alpha_mode),
        ic_months=int(args.ic_months),
        alpha_tstat_scale=float(args.alpha_tstat_scale),
        auto_params=bool(args.auto_params),
        policy_window=int(args.policy_window),
        corr_filter=bool(args.corr_filter),
        corr_threshold=float(args.corr_threshold),
        corr_lookback=int(args.corr_lookback),
        risk_budget=bool(args.risk_budget),
        max_turnover=float(args.max_turnover),
        pf_dd_threshold=float(args.pf_dd_threshold),
        pf_dd_floor_gross=float(args.pf_dd_floor_gross),
        min_cash_weight=float(args.min_cash_weight),
        max_crypto_gross=float(args.max_crypto_gross),
        cb_dd_trigger=float(args.cb_dd_trigger),
        cb_alpha_trigger=float(args.cb_alpha_trigger),
        cb_alpha_window=int(args.cb_alpha_window),
        cb_cooldown_months=int(args.cb_cooldown_months),
        cb_floor_gross=float(args.cb_floor_gross),
        glidepath=False,
        build_max_dd=0.25,
        coast_max_dd=0.15,
        coast_multiple=2.0,
        cppi_mult=3.0,
    )

    pos = res.get("positions")
    if not isinstance(pos, pd.DataFrame) or pos.empty:
        raise SystemExit("No positions produced; cannot export signal.")
    as_of = pd.Timestamp(pos.index[-1])
    w = pos.iloc[-1].fillna(0.0)

    # Extract last lambda and alpha_scale from backtest results.
    lam_series = res.get("lambdas")
    last_lambda = float(lam_series.iloc[-1]) if isinstance(lam_series, pd.Series) and not lam_series.empty else None
    as_series = res.get("alpha_scale")
    last_alpha_scale = float(as_series.iloc[-1]) if isinstance(as_series, pd.Series) and not as_series.empty else None

    signal = {
        "strategy": "alpha_eventproxy_cfg12",
        "as_of_month": str(as_of.date()),
        "weights": _as_float_map(w),
        "lambda_selected": last_lambda,
        "alpha_scale": last_alpha_scale,
        "auto_params": bool(args.auto_params),
        "controls": {
            "control_profile": str(args.control_profile),
            "min_cash_weight": float(args.min_cash_weight),
            "max_crypto_gross": float(args.max_crypto_gross),
            "cb_dd_trigger": float(args.cb_dd_trigger),
            "cb_alpha_trigger": float(args.cb_alpha_trigger),
            "cb_alpha_window": int(args.cb_alpha_window),
            "cb_cooldown_months": int(args.cb_cooldown_months),
            "cb_floor_gross": float(args.cb_floor_gross),
        },
        "inputs": {
            "tickers_file": str(args.tickers_file),
            "panel_out": str(args.panel_out),
            "feature_cache": str(args.feature_cache),
        },
    }
    from src.research.fingerprint import stamp as _stamp_fp  # noqa: E402

    _stamp_fp(
        signal,
        panel_path=args.panel_out,
        config={
            "controls": signal["controls"],
            "auto_params": signal["auto_params"],
            "alpha_scale": signal.get("alpha_scale"),
            "lambda_selected": signal.get("lambda_selected"),
            "inputs": signal["inputs"],
            "argv": sys.argv[1:],
        },
    )
    _write_json(args.signal_out, signal)

    # Paper mark-to-market using the same panel (daily).
    from scripts.alpha_paper_tracker import main as tracker_main  # noqa: E402

    argv_prev = sys.argv[:]
    try:
        sys.argv = [
            "alpha_paper_tracker",
            "--signal",
            str(args.signal_out),
            "--panel",
            str(args.panel_out),
            "--ledger",
            str(args.ledger),
            "--initial-equity",
            str(float(args.initial_equity)),
        ]
        tracker_main()
    finally:
        sys.argv = argv_prev

    score = build_scorecard(args.ledger, args.signal_out, args.panel_out if args.panel_out.exists() else None, str(args.benchmark))
    score.setdefault("positioning", {})
    score["positioning"]["signal_path"] = str(args.signal_out)
    write_outputs(score, args.scorecard_out_dir, args.scorecard_history_csv)

    readiness = _readiness_report(
        panel_info=panel_info,
        signal=signal,
        score=score,
        max_panel_staleness_days=int(args.max_panel_staleness_days),
        min_ledger_days=int(args.readiness_min_ledger_days),
        min_sharpe=float(args.readiness_min_sharpe),
        max_drawdown=float(args.readiness_max_drawdown),
        min_alpha_30d=float(args.readiness_min_alpha_30d),
    )
    _write_json(args.edge_report_json, readiness)
    _write_md(args.edge_report_md, _readiness_markdown(readiness))

    print(f"Panel:  {args.panel_out}")
    print(f"Cache:  {args.feature_cache}")
    print(f"Signal: {args.signal_out}")
    print(f"Ledger: {args.ledger}")
    print(f"Score:  {args.scorecard_out_dir / 'scorecard_latest.json'}")
    print(f"Edge:   {args.edge_report_json} ({readiness['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
