#!/usr/bin/env python3
"""Generate a compact audit of the Sharpe-Renaissance investment research engine.

This is intentionally not a trading signal. It reads existing artifacts and
summarizes which parts of the repo look usable as a research cockpit, which
parts are still experimental, and where the news-pattern layer should plug in.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any


import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
DEFAULT_OUT_DIR = REPO / "reports" / "investment_research_engine"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--top-backtests", type=int, default=20)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def maybe_json(path: Path) -> Any | None:
    try:
        if path.exists():
            return load_json(path)
    except Exception:
        return None
    return None


def safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out):
        return None
    return out


def pct(value: Any, digits: int = 1) -> str:
    number = safe_float(value)
    if number is None:
        return "n/a"
    return f"{number * 100:.{digits}f}%"


def num(value: Any, digits: int = 2) -> str:
    number = safe_float(value)
    if number is None:
        return "n/a"
    return f"{number:.{digits}f}"


def money(value: Any) -> str:
    number = safe_float(value)
    if number is None:
        return "n/a"
    return f"${number:,.0f}"


def verdict(label: str, reason: str) -> dict[str, str]:
    return {"verdict": label, "reason": reason}


def summarize_live(repo: Path) -> dict[str, Any]:
    score = maybe_json(repo / "backtests/outputs/alpha_paper/scorecard_latest.json") or {}
    signal = maybe_json(repo / "backtests/outputs/signals/alpha_live_signal.json") or {}
    perf = score.get("performance", {}) if isinstance(score, dict) else {}
    pos = score.get("positioning", {}) if isinstance(score, dict) else {}
    benchmark = score.get("benchmark", {}) if isinstance(score, dict) else {}
    weights = signal.get("weights", {}) if isinstance(signal, dict) else {}
    top_weights = sorted(weights.items(), key=lambda kv: abs(safe_float(kv[1]) or 0), reverse=True)[:10]

    sharpe = safe_float(perf.get("sharpe_daily_252"))
    alpha_30d = safe_float(benchmark.get("alpha_30d"))
    latest_equity = safe_float(perf.get("latest_equity"))
    if sharpe is not None and sharpe < 0:
        status = verdict("blocked", "Current paper/live scorecard is negative; do not treat this as a deployable signal.")
    elif alpha_30d is not None and alpha_30d < 0:
        status = verdict("caution", "Recent benchmark-relative alpha is negative; keep paper-trading.")
    elif latest_equity is not None and latest_equity < 10_000:
        status = verdict("caution", "Paper equity is below initial capital; needs recovery evidence.")
    else:
        status = verdict("candidate", "Current paper metrics are not obviously broken, but still require live/paper history.")

    return {
        "status": status,
        "scorecard_path": "backtests/outputs/alpha_paper/scorecard_latest.json",
        "signal_path": "backtests/outputs/signals/alpha_live_signal.json",
        "period": score.get("period", {}),
        "performance": perf,
        "benchmark": benchmark,
        "positioning": pos,
        "signal": {
            "strategy": signal.get("strategy"),
            "as_of_month": signal.get("as_of_month"),
            "n_weights": len(weights),
            "top_weights": [{"ticker": ticker, "weight": weight} for ticker, weight in top_weights],
        },
    }


def extract_best(summary: dict[str, Any]) -> dict[str, Any]:
    best = summary.get("best")
    if isinstance(best, dict):
        return best
    return summary


def summarize_named_runs(repo: Path) -> list[dict[str, Any]]:
    specs = [
        (
            "multi_asset_trend",
            "backtests/outputs/multi_asset_research_v2/best.json",
            "Risk-managed multi-asset trend allocator.",
        ),
        (
            "crypto_allocator",
            "backtests/outputs/crypto_best_practice_20260108/summary.json",
            "Crypto top-N allocator versus risk-managed benchmark.",
        ),
        (
            "sp500_equity_selector",
            "backtests/outputs/equity_best_practice_sp500_10y_v2/summary.json",
            "SP500 cross-sectional selector.",
        ),
        (
            "nasdaq_equity_selector",
            "backtests/outputs/equity_best_practice_run1_nasdaq/summary.json",
            "Nasdaq cross-sectional selector with known weak holdout.",
        ),
        (
            "alpha_eventproxy_backtest",
            "backtests/outputs/alpha_eventproxy_cache_build_v3/summary.json",
            "Multi-asset alpha runner with event-proxy features.",
        ),
        (
            "alpha_growth_controls",
            "backtests/outputs/control_profile_eval_growth/summary.json",
            "Alpha runner with growth control profile.",
        ),
    ]
    rows = []
    for name, rel, description in specs:
        path = repo / rel
        data = maybe_json(path)
        if not isinstance(data, dict):
            rows.append({"name": name, "path": rel, "description": description, "status": verdict("missing", "Artifact not found.")})
            continue
        best = extract_best(data)
        test = best.get("test") if isinstance(best.get("test"), dict) else {}
        val = best.get("val") if isinstance(best.get("val"), dict) else {}
        metrics_source = test or best
        cagr = safe_float(metrics_source.get("cagr") or metrics_source.get("strategy_cagr"))
        sharpe = safe_float(metrics_source.get("sharpe") or metrics_source.get("strategy_sharpe"))
        mdd = safe_float(metrics_source.get("max_drawdown") or metrics_source.get("strategy_max_dd"))
        info_ratio = safe_float(best.get("test_info_ratio") or best.get("ir_vs_spy_raw"))
        excess = safe_float(best.get("test_excess_ann_ret") or best.get("excess_ann_vs_spy_raw"))

        if name == "nasdaq_equity_selector":
            status = verdict("blocked", "Holdout was materially negative in this artifact.")
        elif name == "multi_asset_trend":
            status = verdict("candidate", "Useful as a diversifier/risk-managed allocator, not a clean SPY-beater.")
        elif name == "crypto_allocator":
            status = verdict("candidate", "Positive holdout, but crypto regime sample is short and volatile.")
        elif name.startswith("alpha_"):
            status = verdict("research-only", "Backtest is strong, but live paper scorecard is currently negative.")
        elif info_ratio is not None and info_ratio < 0:
            status = verdict("caution", "Benchmark-relative holdout is weak.")
        else:
            status = verdict("candidate", "Artifact passes a first sanity check; still needs robustness review.")

        rows.append(
            {
                "name": name,
                "path": rel,
                "description": description,
                "status": status,
                "metrics": {
                    "cagr": cagr,
                    "sharpe": sharpe,
                    "max_drawdown": mdd,
                    "info_ratio": info_ratio,
                    "excess_ann_ret": excess,
                },
                "validation": val,
                "test": test,
            }
        )
    return rows


def summarize_latest_drilldown(repo: Path) -> dict[str, Any]:
    paths = sorted((repo / "backtests/outputs/global_drilldown").glob("country_drilldown_*.json"))
    if not paths:
        return {"status": verdict("missing", "No country drilldown JSON found.")}
    path = paths[-1]
    data = maybe_json(path) or {}
    return {
        "status": verdict("radar-only", "Useful for shortlist/context; not a standalone trading signal."),
        "path": str(path.relative_to(repo)),
        "as_of": data.get("as_of"),
        "universe_size": data.get("universe_size"),
        "top_10": data.get("top_10", [])[:10],
        "bottom_10": data.get("bottom_10", [])[:10],
    }


def summarize_window_csv(repo: Path, rel: str) -> dict[str, Any]:
    path = repo / rel
    if not path.exists():
        return {"path": rel, "status": verdict("missing", "Window file not found.")}
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
    if not rows:
        return {"path": rel, "status": verdict("empty", "Window file has no rows.")}

    def values(key: str) -> list[float]:
        return [x for x in (safe_float(row.get(key)) for row in rows) if x is not None]

    cagr = values("cagr")
    sharpe = values("sharpe")
    mdd = values("max_drawdown")
    cagr_diff_rm = values("cagr_diff_rm")
    sharpe_diff_rm = values("sharpe_diff_rm")
    return {
        "path": rel,
        "n_windows": len(rows),
        "cagr_median": median(cagr) if cagr else None,
        "cagr_min": min(cagr) if cagr else None,
        "sharpe_median": median(sharpe) if sharpe else None,
        "sharpe_min": min(sharpe) if sharpe else None,
        "max_drawdown_worst": min(mdd) if mdd else None,
        "riskmatched_cagr_win_rate": sum(1 for x in cagr_diff_rm if x > 0) / len(cagr_diff_rm) if cagr_diff_rm else None,
        "riskmatched_sharpe_win_rate": sum(1 for x in sharpe_diff_rm if x > 0) / len(sharpe_diff_rm) if sharpe_diff_rm else None,
    }


def scan_top_backtests(repo: Path, limit: int) -> list[dict[str, Any]]:
    out = []
    for path in (repo / "backtests/outputs").glob("**/summary.json"):
        data = maybe_json(path)
        if not isinstance(data, dict):
            continue
        best = extract_best(data)
        test = best.get("test") if isinstance(best.get("test"), dict) else {}
        source = test or best
        cagr = safe_float(source.get("cagr") or source.get("strategy_cagr"))
        sharpe = safe_float(source.get("sharpe") or source.get("strategy_sharpe"))
        mdd = safe_float(source.get("max_drawdown") or source.get("strategy_max_dd"))
        if cagr is None or sharpe is None:
            continue
        if mdd is not None and mdd < -0.35:
            continue
        out.append(
            {
                "path": str(path.relative_to(repo)),
                "cagr": cagr,
                "sharpe": sharpe,
                "max_drawdown": mdd,
            }
        )
    out.sort(key=lambda row: (row["sharpe"], row["cagr"]), reverse=True)
    return out[:limit]


def build_payload(repo: Path, top_backtests: int) -> dict[str, Any]:
    windows = [
        summarize_window_csv(repo, "backtests/outputs/robust_best_dd25_cfg12/windows.csv"),
        summarize_window_csv(repo, "backtests/outputs/robust_eventproxy_cfg12/windows.csv"),
        summarize_window_csv(repo, "backtests/outputs/control_profile_growth_robustness_windows/windows.csv"),
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "repo": str(repo),
        "executive_verdict": {
            "status": "research_cockpit",
            "summary": (
                "The repo is useful as an investment research cockpit and risk-filter. "
                "It is not yet a trustworthy autonomous stock-picking engine."
            ),
        },
        "live_paper": summarize_live(repo),
        "named_runs": summarize_named_runs(repo),
        "country_drilldown": summarize_latest_drilldown(repo),
        "window_robustness": windows,
        "top_backtest_snapshot": scan_top_backtests(repo, top_backtests),
        "operating_doctrine": [
            "Default to broad, low-cost exposure when selection edge is unproven.",
            "Use the price/factor engine for ranking, confirmation, and risk sizing.",
            "Use the news-pattern layer as a quality and deterioration filter.",
            "Only concentrate when price strength, structural thesis, and news-pattern quality agree.",
            "Keep live/paper tracking separate from backtest optimism.",
        ],
        "next_work": [
            "Add news-pattern country/entity signals as features, then test incremental value versus price-only models.",
            "Create a thesis register for every discretionary tilt: thesis, model evidence, news evidence, invalidation trigger.",
            "Promote only strategies that pass holdout, window robustness, cost checks, and paper-trading checks.",
            "Build a dashboard that separates radar, candidate, paper-trade, and deployable systems.",
        ],
    }


def md_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return out


def render_markdown(payload: dict[str, Any]) -> str:
    live = payload["live_paper"]
    live_perf = live.get("performance", {})
    live_bench = live.get("benchmark", {})
    signal = live.get("signal", {})
    lines: list[str] = [
        "# Investment Research Engine Audit",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Verdict: **{payload['executive_verdict']['status']}**",
        "",
        payload["executive_verdict"]["summary"],
        "",
        "## Current Paper/Live Signal",
        "",
        f"- Status: **{live['status']['verdict']}** — {live['status']['reason']}",
        f"- Strategy: `{signal.get('strategy')}` as of `{signal.get('as_of_month')}`",
        f"- Latest equity: {money(live_perf.get('latest_equity'))}",
        f"- CAGR since start: {pct(live_perf.get('cagr_since_start'))}",
        f"- Sharpe: {num(live_perf.get('sharpe_daily_252'))}",
        f"- Latest drawdown: {pct(live_perf.get('latest_drawdown'))}",
        f"- 30d return / alpha vs SPY: {pct(live_perf.get('return_30d'))} / {pct(live_bench.get('alpha_30d'))}",
        "",
    ]
    weight_rows = [
        [row["ticker"], pct(row["weight"])]
        for row in signal.get("top_weights", [])[:8]
    ]
    if weight_rows:
        lines += md_table(["Ticker", "Weight"], weight_rows)
        lines.append("")

    lines += ["## Strategy Modules", ""]
    strategy_rows = []
    for row in payload["named_runs"]:
        m = row.get("metrics", {})
        strategy_rows.append(
            [
                row["name"],
                row["status"]["verdict"],
                pct(m.get("cagr")),
                num(m.get("sharpe")),
                pct(m.get("max_drawdown")),
                row["status"]["reason"],
            ]
        )
    lines += md_table(["Module", "Status", "CAGR", "Sharpe", "MDD", "Reason"], strategy_rows)
    lines.append("")

    drill = payload["country_drilldown"]
    lines += [
        "## Country/Stock Radar",
        "",
        f"- Status: **{drill['status']['verdict']}** — {drill['status']['reason']}",
        f"- Latest file: `{drill.get('path', 'n/a')}`",
        f"- As of: `{drill.get('as_of', 'n/a')}`; universe size: `{drill.get('universe_size', 'n/a')}`",
        "",
    ]
    top_rows = []
    for item in drill.get("top_10", [])[:10]:
        top_rows.append(
            [
                str(item.get("ticker", "")),
                num(item.get("composite_score") or item.get("composite")),
                pct(item.get("mom_12m")),
                num(item.get("sharpe_252") or item.get("sharpe")),
            ]
        )
    if top_rows:
        lines += md_table(["Ticker", "Composite", "12m Mom", "Sharpe"], top_rows)
        lines.append("")

    lines += ["## Window Robustness", ""]
    window_rows = []
    for row in payload["window_robustness"]:
        window_rows.append(
            [
                row["path"],
                str(row.get("n_windows", "n/a")),
                pct(row.get("cagr_median")),
                num(row.get("sharpe_median")),
                pct(row.get("max_drawdown_worst")),
                pct(row.get("riskmatched_cagr_win_rate")),
                pct(row.get("riskmatched_sharpe_win_rate")),
            ]
        )
    lines += md_table(["File", "N", "Median CAGR", "Median Sharpe", "Worst MDD", "RM CAGR Win", "RM Sharpe Win"], window_rows)
    lines.append("")

    lines += ["## Clean Operating Doctrine", ""]
    for item in payload["operating_doctrine"]:
        lines.append(f"- {item}")
    lines.append("")

    lines += ["## Next Work", ""]
    for item in payload["next_work"]:
        lines.append(f"- {item}")
    lines.append("")

    lines += ["## Top Backtest Snapshot", ""]
    bt_rows = [
        [row["path"], pct(row["cagr"]), num(row["sharpe"]), pct(row["max_drawdown"])]
        for row in payload["top_backtest_snapshot"]
    ]
    lines += md_table(["Path", "CAGR", "Sharpe", "MDD"], bt_rows)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(repo, args.top_backtests)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"investment_research_engine_audit_{stamp}.json"
    md_path = out_dir / f"investment_research_engine_audit_{stamp}.md"
    latest_json = out_dir / "latest.json"
    latest_md = out_dir / "latest.md"
    text = render_markdown(payload)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(text + "\n", encoding="utf-8")
    latest_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    latest_md.write_text(text + "\n", encoding="utf-8")
    print(md_path)
    print(latest_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
