"""Live + historical scorecard for IDX operator / position-sheet empirical research."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from idn_eval_splits import time_cutoff


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def ledger_metrics(path: Path, *, initial_equity: float = 10_000.0) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "path": str(path)}
    df = pd.read_csv(path)
    if df.empty or "equity" not in df.columns:
        return {"available": False, "path": str(path), "reason": "empty"}
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    eq = df["equity"].astype(float)
    ret = df["daily_return"].astype(float) if "daily_return" in df.columns else eq.pct_change()
    ret = ret.dropna()
    terminal = float(eq.iloc[-1])
    total_ret_pct = (terminal / initial_equity - 1) * 100
    vol = float(ret.std(ddof=1)) if len(ret) > 1 else 0.0
    sharpe = float(ret.mean() / vol * math.sqrt(252)) if vol > 0 else None
    peak = eq.cummax()
    dd = (eq / peak - 1).min() * 100
    oos_start = time_cutoff(df["date"])
    oos = df[df["date"] >= oos_start]
    oos_ret = None
    if len(oos) >= 2:
        oos_ret = (float(oos["equity"].iloc[-1]) / float(oos["equity"].iloc[0]) - 1) * 100
    return {
        "available": True,
        "path": str(path),
        "strategy": str(df["strategy"].iloc[-1]) if "strategy" in df.columns else None,
        "as_of_week": str(df["as_of_week"].iloc[-1]) if "as_of_week" in df.columns else None,
        "first_date": str(df["date"].iloc[0].date()),
        "last_date": str(df["date"].iloc[-1].date()),
        "trading_days": int(len(df)),
        "initial_equity": initial_equity,
        "terminal_equity": round(terminal, 2),
        "total_return_pct": round(total_ret_pct, 2),
        "max_drawdown_pct": round(float(dd), 2),
        "sharpe_daily": round(sharpe, 3) if sharpe is not None else None,
        "hit_rate_pct": round(float((ret > 0).mean() * 100), 1) if len(ret) else None,
        "return_holdout_pct": round(oos_ret, 2) if oos_ret is not None else None,
    }


def validation_summary(path: Path) -> dict[str, Any]:
    raw = _read_json(path)
    if not raw:
        return {"available": False, "path": str(path)}
    ov = raw.get("overall", {})
    op = raw.get("operator_rules", {})
    retail = (raw.get("retail_playbook") or {}).get("strategies", {})
    return {
        "available": True,
        "path": str(path),
        "built_at_utc": raw.get("built_at_utc"),
        "week_span": raw.get("week_span"),
        "entity_weeks_holdout": raw.get("entity_weeks_holdout"),
        "reliable_signals": ov.get("reliable_signals", []),
        "conditional_signals": ov.get("conditional_signals", []),
        "unreliable_signals": ov.get("unreliable_signals", []),
        "operator_rules_verdict": {
            era: block.get("verdict")
            for era, block in op.items()
            if isinstance(block, dict)
        },
        "operator_rules_excess": {
            era: (block.get("excess") or {})
            for era, block in op.items()
            if isinstance(block, dict)
        },
        "retail_playbook": {
            sid: {
                "verdict": s.get("verdict"),
                "oos_5d_mean_pct": ((s.get("event_study") or {}).get("by_horizon") or {}).get("oos_5d", {}).get("mean_pct"),
                "oos_5d_tstat": ((s.get("event_study") or {}).get("by_horizon") or {}).get("oos_5d", {}).get("tstat"),
            }
            for sid, s in retail.items()
            if isinstance(s, dict)
        },
        "api_rsi_reliable": (raw.get("api_rsi_crosscheck") or {}).get("reliable"),
        "sentiment_snapshots": raw.get("sentiment_snapshots"),
        "trending_history": raw.get("trending_history"),
        "honest_limits": ov.get("honest_limits", []),
    }


def portfolio_snapshot(path: Path) -> dict[str, Any]:
    pf = _read_json(path)
    if not pf:
        return {"available": False, "path": str(path)}
    weights = pf.get("weights") or {}
    return {
        "available": True,
        "path": str(path),
        "strategy": pf.get("strategy"),
        "as_of_week": pf.get("as_of_week"),
        "weights": weights,
        "avoid": pf.get("avoid", []),
        "stance": pf.get("stance"),
        "conviction": pf.get("conviction_1_to_5"),
        "top_holdings": sorted(weights.items(), key=lambda x: -x[1])[:5],
    }


def build_scorecard(
    *,
    position_ledger: Path,
    operator_rules_ledger: Path,
    operator_llm_ledger: Path | None = None,
    validation_json: Path,
    rules_portfolio: Path,
    llm_portfolio: Path | None = None,
    position_portfolio: Path,
    initial_equity: float = 10_000.0,
) -> dict[str, Any]:
    sleeves = {
        "position_sheet": ledger_metrics(position_ledger, initial_equity=initial_equity),
        "operator_rules": ledger_metrics(operator_rules_ledger, initial_equity=initial_equity),
    }
    if operator_llm_ledger:
        sleeves["operator_llm"] = ledger_metrics(operator_llm_ledger, initial_equity=initial_equity)

    portfolios = {
        "position_sheet": portfolio_snapshot(position_portfolio),
        "operator_rules": portfolio_snapshot(rules_portfolio),
    }
    if llm_portfolio:
        portfolios["operator_llm"] = portfolio_snapshot(llm_portfolio)

    val = validation_summary(validation_json)
    return {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "live_paper": sleeves,
        "current_portfolios": portfolios,
        "historical_validation": val,
    }


def write_research_brief(scorecard: dict[str, Any]) -> str:
    val = scorecard.get("historical_validation") or {}
    live = scorecard.get("live_paper") or {}
    ports = scorecard.get("current_portfolios") or {}

    lines = [
        "# IDX empirical research brief",
        f"- built: {scorecard.get('built_at_utc')}",
        "",
        "## What this stack is",
        "",
        "Three layers, one research loop:",
        "",
        "1. **Data** — prices (yfinance), news entity mentions (GDELT), RapidAPI IDX pulse (trending, followers, RSI).",
        "2. **Signals** — operator rules (mom leaders, fade headlines), retail playbook (BBCA support+RSI), LLM reconciliation over full evidence pack.",
        "3. **Receipts** — weekly backtests (517 weeks), event studies, live paper ledgers, daily sentiment archive.",
        "",
        "## Live paper (real marks, not backtest)",
        "",
    ]

    for name, m in live.items():
        if not m.get("available"):
            lines.append(f"- **{name}**: no ledger yet (`{m.get('path', '')}`)")
            continue
        lines.append(
            f"- **{name}** ({m.get('strategy')}): "
            f"{m.get('total_return_pct'):+.2f}% since {m.get('first_date')} "
            f"(equity ${m.get('terminal_equity'):,.0f}, max DD {m.get('max_drawdown_pct'):.1f}%)"
        )
    lines.extend(["", "## Current books", ""])
    for name, p in ports.items():
        if not p.get("available"):
            continue
        tops = ", ".join(f"{t} {w:.0%}" for t, w in (p.get("top_holdings") or [])[:4])
        lines.append(f"- **{name}** ({p.get('strategy')}, week {p.get('as_of_week')}): {tops or 'n/a'}")

    if val.get("available"):
        lines.extend(
            [
                "",
                "## Historical validation (backtest)",
                "",
                f"- Panel: {val.get('week_span', ['?', '?'])[0]} → {val.get('week_span', ['?', '?'])[1]}",
                f"- Entity weeks holdout: {val.get('entity_weeks_holdout')}",
                f"- **Reliable signals**: {', '.join(val.get('reliable_signals') or []) or 'none at weekly bar'}",
                f"- **Conditional**: {', '.join(val.get('conditional_signals') or []) or 'none'}",
                f"- **Unreliable**: {', '.join(val.get('unreliable_signals') or []) or 'none'}",
                "",
                "### Operator rules (mom leader sleeve)",
            ]
        )
        for era, verdict in (val.get("operator_rules_verdict") or {}).items():
            ex = (val.get("operator_rules_excess") or {}).get(era) or {}
            lines.append(
                f"- **{era}**: verdict={verdict} | excess {ex.get('mean_weekly_pct')}%/wk | "
                f"Sharpe {ex.get('sharpe_weekly')} | terminal {ex.get('terminal_x')}x"
            )

        lines.append("")
        lines.append("### Retail playbook (event studies)")
        for sid, s in (val.get("retail_playbook") or {}).items():
            lines.append(
                f"- **{sid}**: {s.get('verdict')} | OOS 5d mean {s.get('oos_5d_mean_pct')}% (t={s.get('oos_5d_tstat')})"
            )

        snap = val.get("sentiment_snapshots") or {}
        trend = val.get("trending_history") or {}
        lines.extend(
            [
                "",
                "## Data health",
                f"- RapidAPI RSI cross-check reliable: **{val.get('api_rsi_reliable')}**",
                f"- Sentiment snapshot days: **{snap.get('snapshot_days', 0)}** ({snap.get('verdict', 'n/a')})",
                f"- Trending history rows: **{trend.get('rows', 0)}**",
                "",
                "## How to read this",
                "",
                "| Use for sizing | Signal |",
                "|----------------|--------|",
                "| High | BBCA support+RSI, blue-chip support (retail playbook OOS) |",
                "| Small / monitor | Operator rules full-sample excess (fails OOS holdout) |",
                "| Context only | RapidAPI trending rank until ≥8 weeks history |",
                "| Not systematic | Weekly mom_leader chase, mention-fade as implemented |",
                "",
                "## Honest limits",
            ]
        )
        for x in val.get("honest_limits") or []:
            lines.append(f"- {x}")
    else:
        lines.append("")
        lines.append("_Historical validation not run yet — see `run_idn_sentiment_signal_validation.py`_")

    lines.append("")
    return "\n".join(lines)
