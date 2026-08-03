#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
SR_ROOT = _bmod.bootstrap_repo_paths(__file__)


def _read_json(path: Path) -> Dict:
    return json.loads(path.read_text())


def _max_drawdown_from_returns(r: pd.Series) -> float:
    eq = (1.0 + r.fillna(0.0)).cumprod()
    dd = eq / eq.cummax() - 1.0
    return float(dd.min())


def _sharpe_annualized(r: pd.Series, periods_per_year: float = 252.0) -> float:
    x = r.dropna().astype(float)
    if len(x) < 3:
        return float("nan")
    mu = float(x.mean())
    sd = float(x.std(ddof=1))
    if not np.isfinite(sd) or sd <= 1e-12:
        return float("nan")
    return float(mu / sd * math.sqrt(periods_per_year))


def _sortino_annualized(r: pd.Series, periods_per_year: float = 252.0) -> float:
    x = r.dropna().astype(float)
    if len(x) < 3:
        return float("nan")
    neg = x[x < 0.0]
    dsd = float(neg.std(ddof=1)) if len(neg) >= 2 else float("nan")
    if not np.isfinite(dsd) or dsd <= 1e-12:
        return float("nan")
    return float(x.mean() / dsd * math.sqrt(periods_per_year))


def _cagr_from_equity(eq: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    years = float((end - start).days) / 365.25
    if years <= 0:
        return float("nan")
    s = float(eq.iloc[0])
    e = float(eq.iloc[-1])
    if s <= 0:
        return float("nan")
    return float((e / s) ** (1.0 / years) - 1.0)


def _rolling_win_rate(r: pd.Series, window: int) -> float:
    x = r.tail(int(window)).dropna()
    if len(x) == 0:
        return float("nan")
    return float((x > 0.0).mean())


def _find_cash_keys(weights: Dict[str, float]) -> List[str]:
    out = []
    for k in weights.keys():
        u = str(k).upper()
        if u in {"CASH", "BIL", "SGOV", "SHV", "SHY"}:
            out.append(k)
    return out


def _calc_concentration(weights: Dict[str, float]) -> Dict[str, float]:
    vals = np.array([max(0.0, float(v)) for v in weights.values()], dtype=float)
    total = float(vals.sum())
    if total <= 1e-12:
        return {"hhi": float("nan"), "effective_n": float("nan")}
    p = vals / total
    hhi = float(np.sum(p * p))
    eff_n = float(1.0 / hhi) if hhi > 0 else float("nan")
    return {"hhi": hhi, "effective_n": eff_n}


def _benchmark_slice(panel_csv: Path, benchmark: str, dates: pd.DatetimeIndex) -> Optional[pd.Series]:
    if not panel_csv.exists():
        return None
    df = pd.read_csv(panel_csv, usecols=["Instrument", "Date", "Price_Close"])
    df = df[df["Instrument"].astype(str) == str(benchmark)].copy()
    if df.empty:
        return None
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")
    px = df.set_index("Date")["Price_Close"].astype(float)
    px = px.reindex(dates).ffill()
    ret = px.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return ret


def build_scorecard(
    ledger_csv: Path,
    signal_json: Path,
    panel_csv: Optional[Path],
    benchmark: str,
) -> Dict:
    ledger = pd.read_csv(ledger_csv)
    ledger["date"] = pd.to_datetime(ledger["date"], errors="coerce")
    ledger = ledger.dropna(subset=["date"]).sort_values("date")
    if ledger.empty:
        raise ValueError("ledger is empty")

    signal = _read_json(signal_json)
    weights = signal.get("weights", {}) or {}
    if not isinstance(weights, dict):
        weights = {}

    r = ledger["daily_return"].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    eq = ledger["equity"].astype(float)
    dd = ledger["drawdown"].astype(float)
    start = pd.Timestamp(ledger["date"].iloc[0])
    end = pd.Timestamp(ledger["date"].iloc[-1])

    cash_keys = _find_cash_keys(weights)
    conc = _calc_concentration(weights)
    top_weights = sorted(weights.items(), key=lambda kv: float(kv[1]), reverse=True)[:10]

    score = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "period": {
            "start": str(start.date()),
            "end": str(end.date()),
            "n_days": int(len(ledger)),
        },
        "performance": {
            "return_since_start": float(eq.iloc[-1] / eq.iloc[0] - 1.0) if float(eq.iloc[0]) > 0 else float("nan"),
            "cagr_since_start": _cagr_from_equity(eq, start, end),
            "sharpe_daily_252": _sharpe_annualized(r, periods_per_year=252.0),
            "sortino_daily_252": _sortino_annualized(r, periods_per_year=252.0),
            "max_drawdown_from_returns": _max_drawdown_from_returns(r),
            "max_drawdown_from_ledger": float(dd.min()),
            "latest_drawdown": float(dd.iloc[-1]),
            "latest_equity": float(eq.iloc[-1]),
            "return_7d": float((1.0 + r.tail(7)).prod() - 1.0),
            "return_30d": float((1.0 + r.tail(30)).prod() - 1.0),
            "win_rate_30d": _rolling_win_rate(r, 30),
            "worst_day": float(r.min()),
            "best_day": float(r.max()),
        },
        "positioning": {
            "as_of_month": signal.get("as_of_month"),
            "strategy": signal.get("strategy"),
            "n_weights": int(len(weights)),
            "cash_keys": cash_keys,
            "cash_weight": float(sum(float(weights.get(k, 0.0)) for k in cash_keys)),
            "concentration_hhi": conc["hhi"],
            "effective_n": conc["effective_n"],
            "top_weights": [{"ticker": k, "weight": float(v)} for k, v in top_weights],
        },
    }

    if panel_csv is not None:
        br = _benchmark_slice(panel_csv, benchmark, pd.DatetimeIndex(ledger["date"]))
        if br is not None and len(br) == len(r):
            active = r.values - br.values
            active_s = pd.Series(active, index=ledger["date"])
            score["benchmark"] = {
                "ticker": benchmark,
                "return_30d": float((1.0 + br.tail(30)).prod() - 1.0),
                "alpha_30d": float((1.0 + r.tail(30)).prod() - (1.0 + br.tail(30)).prod()),
                "tracking_error_30d": float(active_s.tail(30).std(ddof=1) * math.sqrt(252.0)) if len(active_s.tail(30)) > 2 else float("nan"),
            }

    return score


def write_outputs(score: Dict, out_dir: Path, history_csv: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scorecard_latest.json").write_text(json.dumps(score, indent=2) + "\n")

    perf = score["performance"]
    pos = score["positioning"]
    lines = [
        "# Alpha Paper Trading Scorecard",
        "",
        f"- generated_at: `{score['generated_at']}`",
        f"- period: `{score['period']['start']}` -> `{score['period']['end']}` ({score['period']['n_days']} days)",
        "",
        "## Performance",
        "",
        f"- return_since_start: `{perf['return_since_start']:.4f}`",
        f"- cagr_since_start: `{perf['cagr_since_start']:.4f}`",
        f"- sharpe_daily_252: `{perf['sharpe_daily_252']:.4f}`",
        f"- sortino_daily_252: `{perf['sortino_daily_252']:.4f}`",
        f"- max_drawdown_from_ledger: `{perf['max_drawdown_from_ledger']:.4f}`",
        f"- latest_drawdown: `{perf['latest_drawdown']:.4f}`",
        f"- return_7d: `{perf['return_7d']:.4f}`",
        f"- return_30d: `{perf['return_30d']:.4f}`",
        f"- win_rate_30d: `{perf['win_rate_30d']:.4f}`",
        "",
        "## Positioning",
        "",
        f"- strategy: `{pos['strategy']}`",
        f"- as_of_month: `{pos['as_of_month']}`",
        f"- n_weights: `{pos['n_weights']}`",
        f"- cash_weight: `{pos['cash_weight']:.4f}`",
        f"- effective_n: `{pos['effective_n']:.4f}`",
        "",
        "## Top Weights",
        "",
    ]
    top_df = pd.DataFrame(pos["top_weights"])
    if not top_df.empty:
        lines.append(top_df.to_markdown(index=False))
    else:
        lines.append("_No weights found_")

    if "benchmark" in score:
        bm = score["benchmark"]
        lines.extend(
            [
                "",
                "## Benchmark",
                "",
                f"- ticker: `{bm['ticker']}`",
                f"- benchmark_return_30d: `{bm['return_30d']:.4f}`",
                f"- alpha_30d: `{bm['alpha_30d']:.4f}`",
                f"- tracking_error_30d: `{bm['tracking_error_30d']:.4f}`",
            ]
        )

    (out_dir / "scorecard_latest.md").write_text("\n".join(lines) + "\n")

    history_row = {
        "date": score["period"]["end"],
        "generated_at": score["generated_at"],
        "cagr_since_start": perf["cagr_since_start"],
        "sharpe_daily_252": perf["sharpe_daily_252"],
        "max_drawdown": perf["max_drawdown_from_ledger"],
        "latest_drawdown": perf["latest_drawdown"],
        "return_7d": perf["return_7d"],
        "return_30d": perf["return_30d"],
        "win_rate_30d": perf["win_rate_30d"],
        "cash_weight": pos["cash_weight"],
        "effective_n": pos["effective_n"],
        "strategy": pos["strategy"],
        "as_of_month": pos["as_of_month"],
    }
    if "benchmark" in score:
        history_row["benchmark_ticker"] = score["benchmark"]["ticker"]
        history_row["benchmark_return_30d"] = score["benchmark"]["return_30d"]
        history_row["alpha_30d"] = score["benchmark"]["alpha_30d"]

    history_df = pd.DataFrame([history_row])
    if history_csv.exists():
        old = pd.read_csv(history_csv)
        new = pd.concat([old, history_df], ignore_index=True)
        new = new.drop_duplicates(subset=["date"], keep="last")
    else:
        new = history_df
    history_csv.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(history_csv, index=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build daily paper-trading scorecard for Sharpe-Renaissance.")
    ap.add_argument("--ledger", type=Path, default=SR_ROOT / "backtests/outputs/alpha_paper/ledger.csv")
    ap.add_argument("--signal", type=Path, default=SR_ROOT / "backtests/outputs/signals/alpha_live_signal.json")
    ap.add_argument("--panel", type=Path, default=SR_ROOT / "data_lake/daily_alpha_panel.csv")
    ap.add_argument("--benchmark", type=str, default="SPY")
    ap.add_argument("--out-dir", type=Path, default=SR_ROOT / "backtests/outputs/alpha_paper")
    ap.add_argument(
        "--history-csv",
        type=Path,
        default=SR_ROOT / "backtests/outputs/alpha_paper/scorecard_history.csv",
    )
    args = ap.parse_args()

    if not args.ledger.exists():
        raise SystemExit(f"ledger file not found: {args.ledger}")
    if not args.signal.exists():
        raise SystemExit(f"signal file not found: {args.signal}")

    panel = args.panel if args.panel.exists() else None
    score = build_scorecard(args.ledger, args.signal, panel, args.benchmark)

    # Reproducibility fingerprint: pins this scorecard to a {git_commit,
    # panel_sha256, signal_sha256} so its claims can be reconstructed later.
    try:
        from src.research.fingerprint import stamp as _stamp_fp  # noqa: WPS433

        _stamp_fp(
            score,
            panel_path=panel,
            config={
                "ledger": str(args.ledger),
                "signal": str(args.signal),
                "benchmark": args.benchmark,
            },
            extra={"signal": args.signal, "ledger": args.ledger},
        )
    except Exception as exc:  # pragma: no cover - never block scorecard write
        score["fingerprint_error"] = repr(exc)

    write_outputs(score, args.out_dir, args.history_csv)

    print(f"wrote: {args.out_dir / 'scorecard_latest.json'}")
    print(f"wrote: {args.out_dir / 'scorecard_latest.md'}")
    print(f"updated: {args.history_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

