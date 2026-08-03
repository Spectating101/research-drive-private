"""Tool library for IDX analyst agent — LLM invokes these to compute, not narrate."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
BROADCAST = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
ENTITY = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/ticker_week_entity_market_panel.parquet"
SENTIMENT_JSON = REPO / "data_lake/sentiment/idn_public_sentiment_latest.json"
INDEX = "^JKSE"


def _rsi14(rets: pd.Series) -> float | None:
    if len(rets) < 14:
        return None
    delta = rets.iloc[-14:]
    up = delta.clip(lower=0).mean()
    down = (-delta.clip(upper=0)).mean()
    if not down or down <= 0:
        return 100.0
    return float(100 - 100 / (1 + up / down))


@dataclass
class AnalystDataContext:
    liquid: list[str]
    as_of: pd.Timestamp | None = None
    _broadcast: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)
    _entity: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)

    def __post_init__(self) -> None:
        if BROADCAST.exists():
            b = pd.read_parquet(BROADCAST)
            b["week_end"] = pd.to_datetime(b["week_end"])
            b = b[(b["country_iso3"] == "IDN") & (b["yahoo_symbol"].isin(self.liquid))].copy()
            if self.as_of is not None:
                b = b[b["week_end"] <= self.as_of]
            self._broadcast = b.sort_values(["yahoo_symbol", "week_end"])
        if ENTITY.exists():
            e = pd.read_parquet(ENTITY)
            e["week_end"] = pd.to_datetime(e["week_end"])
            e = e[(e["country_iso3"] == "IDN") & (e["yahoo_symbol"].isin(self.liquid))].copy()
            if self.as_of is not None:
                e = e[e["week_end"] <= self.as_of]
            self._entity = e.sort_values(["yahoo_symbol", "week_end"])

    @property
    def last_week(self) -> pd.Timestamp | None:
        if self._broadcast.empty:
            return None
        return pd.Timestamp(self._broadcast["week_end"].max())

    def latest_broadcast_row(self, ticker: str) -> dict[str, Any] | None:
        sub = self._broadcast[self._broadcast["yahoo_symbol"] == ticker]
        if sub.empty:
            return None
        row = sub.iloc[-1]
        return {
            "week_end": str(row["week_end"].date()),
            "return_1w": round(float(row.get("return_1w", 0) or 0) * 100, 2),
            "fwd_return_1w": round(float(row["fwd_return_1w"]) * 100, 2)
            if pd.notna(row.get("fwd_return_1w"))
            else None,
        }

    def latest_entity_row(self, ticker: str) -> dict[str, Any] | None:
        sub = self._entity[self._entity["yahoo_symbol"] == ticker]
        if sub.empty:
            return None
        row = sub.iloc[-1]
        return {
            "week_end": str(row["week_end"].date()),
            "entity_mention_rows": int(row.get("entity_mention_rows") or 0),
            "mean_tone_avg": round(float(row.get("mean_tone_avg") or 0), 3)
            if pd.notna(row.get("mean_tone_avg"))
            else None,
        }


def tool_get_regime(ctx: AnalystDataContext, *, lookback_days: int = 120) -> dict[str, Any]:
    from idn_spike_explainer import fetch_history

    end = (ctx.as_of or pd.Timestamp.utcnow()).date() + timedelta(days=1)
    start = (end - timedelta(days=lookback_days + 30)).isoformat()
    close, _ = fetch_history([INDEX], start, str(end))
    if close.empty or INDEX not in close.columns:
        return {"ok": False, "error": "no_index_data"}
    if ctx.as_of is not None:
        close = close[close.index <= ctx.as_of]
    idx = close[INDEX].dropna()
    if len(idx) < 65:
        return {"ok": False, "error": "insufficient_history"}
    last = float(idx.iloc[-1])
    high63 = float(idx.iloc[-63:].max())
    low20 = float(idx.iloc[-20:].min())
    dd63 = last / high63 - 1.0
    bounce20 = last / low20 - 1.0
    ret5 = last / float(idx.iloc[-6]) - 1.0 if len(idx) >= 6 else None
    regime = "neutral"
    if dd63 <= -0.10 and bounce20 < 0.08:
        regime = "washout"
    elif dd63 <= -0.10 and bounce20 >= 0.08:
        regime = "recovery"
    elif bounce20 >= 0.12 and ret5 is not None and ret5 >= 0.05:
        regime = "extended_bounce"
    return {
        "ok": True,
        "as_of": str(idx.index[-1].date()),
        "regime": regime,
        "dd_63d_pct": round(dd63 * 100, 2),
        "bounce_20d_pct": round(bounce20 * 100, 2),
        "ret_5d_pct": round(ret5 * 100, 2) if ret5 is not None else None,
    }


def tool_screen_universe(
    ctx: AnalystDataContext,
    *,
    sort_by: str = "mom_4w",
    top_n: int = 15,
    bottom_n: int = 0,
) -> dict[str, Any]:
    if ctx._broadcast.empty:
        return {"ok": False, "error": "no_broadcast_panel"}
    wk = ctx.last_week
    if wk is None:
        return {"ok": False, "error": "no_week_snapshot"}
    hist = ctx._broadcast[ctx._broadcast["week_end"] <= wk].copy()
    rows_raw: list[dict[str, Any]] = []
    for sym, g in hist.groupby("yahoo_symbol"):
        g = g.sort_values("week_end")
        if g["week_end"].iloc[-1] != wk:
            continue
        mom4 = float(g["return_1w"].iloc[-4:].sum()) if len(g) >= 4 else float(g["return_1w"].sum())
        rows_raw.append(
            {
                "yahoo_symbol": sym,
                "return_1w": float(g["return_1w"].iloc[-1]),
                "mom_4w": mom4,
            }
        )
    snap = pd.DataFrame(rows_raw)
    if snap.empty:
        return {"ok": False, "error": "empty_week"}
    if not ctx._entity.empty:
        ent = ctx._entity[ctx._entity["week_end"] == wk][["yahoo_symbol", "entity_mention_rows", "mean_tone_avg"]]
        snap = snap.merge(ent, on="yahoo_symbol", how="left")
    sort_col = sort_by if sort_by in snap.columns else "return_1w"
    snap = snap.dropna(subset=[sort_col])
    top = snap.nlargest(int(top_n), sort_col)
    rows = []
    for _, r in top.iterrows():
        rows.append(
            {
                "ticker": r["yahoo_symbol"],
                "return_1w_pct": round(float(r.get("return_1w", 0) or 0) * 100, 2),
                "mom_4w_pct": round(float(r.get("mom_4w", 0) or 0) * 100, 2),
                "mention_rows": int(r.get("entity_mention_rows") or 0)
                if pd.notna(r.get("entity_mention_rows"))
                else None,
                "tone": round(float(r.get("mean_tone_avg") or 0), 3)
                if pd.notna(r.get("mean_tone_avg"))
                else None,
            }
        )
    bottom = []
    if bottom_n > 0:
        for _, r in snap.nsmallest(int(bottom_n), sort_col).iterrows():
            bottom.append({"ticker": r["yahoo_symbol"], sort_col: round(float(r[sort_col]) * 100, 2)})
    return {"ok": True, "week_end": str(wk.date()), "sort_by": sort_col, "top": rows, "bottom": bottom}


def tool_analyze_ticker(ctx: AnalystDataContext, *, ticker: str) -> dict[str, Any]:
    if ticker not in ctx.liquid:
        return {"ok": False, "error": "not_in_liquid_universe", "ticker": ticker}
    from idn_spike_explainer import fetch_history

    end = (ctx.as_of or pd.Timestamp.utcnow()).date() + timedelta(days=1)
    start = (end - timedelta(days=400)).isoformat()
    close, vol = fetch_history([ticker, INDEX], start, str(end))
    if ctx.as_of is not None:
        close = close[close.index <= ctx.as_of]
        vol = vol[vol.index <= ctx.as_of]
    if ticker not in close.columns or close[ticker].dropna().empty:
        return {"ok": False, "error": "no_price_data", "ticker": ticker}
    px = close[ticker].dropna()
    ret = px.pct_change()
    last = float(px.iloc[-1])
    d5 = (last / float(px.iloc[-6]) - 1) * 100 if len(px) >= 6 else None
    d20 = (last / float(px.iloc[-21]) - 1) * 100 if len(px) >= 21 else None
    d60 = (last / float(px.iloc[-61]) - 1) * 100 if len(px) >= 61 else None
    low60 = float(px.iloc[-60:].min()) if len(px) >= 60 else last
    dist_low60 = (last / low60 - 1) * 100 if low60 else None
    weekly = px.resample("W-FRI").last().pct_change()
    mom4w = float(weekly.iloc[-5:-1].sum() * 100) if len(weekly) >= 5 else None
    rs_vs_ihsg = None
    if INDEX in close.columns:
        ih = close[INDEX].dropna()
        if len(ih) >= 21 and len(px) >= 21:
            rs_vs_ihsg = round(
                (last / float(px.iloc[-21]) - 1) * 100 - (float(ih.iloc[-1]) / float(ih.iloc[-21]) - 1) * 100,
                2,
            )
    broadcast = ctx.latest_broadcast_row(ticker)
    entity = ctx.latest_entity_row(ticker)
    retail = tool_check_retail_signals(ctx, ticker=ticker)
    return {
        "ok": True,
        "ticker": ticker,
        "price_date": str(px.index[-1].date()),
        "close": round(last, 0),
        "ret_5d_pct": round(d5, 2) if d5 is not None else None,
        "ret_20d_pct": round(d20, 2) if d20 is not None else None,
        "ret_60d_pct": round(d60, 2) if d60 is not None else None,
        "dist_from_60d_low_pct": round(dist_low60, 2) if dist_low60 is not None else None,
        "mom_4w_pct": round(mom4w, 2) if mom4w is not None else None,
        "rsi14": round(_rsi14(ret), 1) if _rsi14(ret) is not None else None,
        "rs_vs_ihsg_20d_pct": rs_vs_ihsg,
        "weekly_panel": broadcast,
        "entity_news": entity,
        "retail_signals": retail.get("active_strategies", []),
        "volume_z20": _volume_z(vol[ticker].dropna()) if ticker in vol.columns else None,
    }


def _volume_z(vol: pd.Series) -> float | None:
    if len(vol) < 25:
        return None
    v = vol.iloc[-20:]
    mu = float(v.mean())
    sd = float(v.std(ddof=1))
    if sd <= 0:
        return None
    return round((float(vol.iloc[-1]) - mu) / sd, 2)


def tool_compare_tickers(ctx: AnalystDataContext, *, tickers: list[str]) -> dict[str, Any]:
    rows = []
    for t in tickers[:8]:
        a = tool_analyze_ticker(ctx, ticker=t)
        if a.get("ok"):
            rows.append(
                {
                    "ticker": t,
                    "ret_5d_pct": a.get("ret_5d_pct"),
                    "mom_4w_pct": a.get("mom_4w_pct"),
                    "rsi14": a.get("rsi14"),
                    "mention_rows": (a.get("entity_news") or {}).get("entity_mention_rows"),
                    "retail_active": len(a.get("retail_signals") or []),
                }
            )
    return {"ok": True, "comparison": rows}


def tool_check_retail_signals(ctx: AnalystDataContext, *, ticker: str) -> dict[str, Any]:
    from idn_retail_strategies import PLAYBOOK, build_all_signals

    if ticker not in ctx.liquid:
        return {"ok": False, "error": "not_in_liquid_universe"}
    from idn_spike_explainer import fetch_history

    end = (ctx.as_of or pd.Timestamp.utcnow()).date() + timedelta(days=1)
    start = (end - timedelta(days=400)).isoformat()
    close, vol = fetch_history(ctx.liquid, start, str(end))
    if ctx.as_of is not None:
        close = close[close.index <= ctx.as_of]
        vol = vol[vol.index <= ctx.as_of]
    signals = build_all_signals(close, vol, ctx.liquid)
    as_of_dt = ctx.as_of if ctx.as_of is not None else close.index.max()
    active = []
    for strat in PLAYBOOK:
        fired = signals.get(strat.id, {})
        # signals keyed by date — find fires on or before as_of for this ticker
        for dt, syms in fired.items():
            if pd.Timestamp(dt) > as_of_dt:
                continue
            if ticker in syms and (as_of_dt - pd.Timestamp(dt)).days <= strat.hold_days:
                active.append(
                    {
                        "strategy_id": strat.id,
                        "jargon": strat.retail_jargon,
                        "fired_date": str(pd.Timestamp(dt).date()),
                        "hold_days": strat.hold_days,
                    }
                )
    return {"ok": True, "ticker": ticker, "active_strategies": active}


def tool_get_sentiment(ctx: AnalystDataContext, *, ticker: str) -> dict[str, Any]:
    if not SENTIMENT_JSON.exists():
        return {"ok": False, "error": "no_sentiment_snapshot"}
    raw = json.loads(SENTIMENT_JSON.read_text(encoding="utf-8"))
    sym = ticker.replace(".JK", "")
    pulse = raw.get("ticker_pulse") or []
    row = next((p for p in pulse if p.get("yahoo_symbol") == ticker or p.get("symbol") == sym), None)
    if not row:
        return {"ok": True, "ticker": ticker, "found": False, "note": "not in latest pulse"}
    return {
        "ok": True,
        "ticker": ticker,
        "found": True,
        "collected_at_utc": raw.get("collected_at_utc"),
        "attention_score": row.get("attention_score"),
        "trending_rank": row.get("trending_rank"),
        "followers": row.get("followers"),
        "api_recommendation": row.get("api_recommendation"),
        "rsi_api": row.get("rsi"),
    }


def tool_factor_summary(ctx: AnalystDataContext) -> dict[str, Any]:
    path = REPO / "backtests/outputs/platform/idn_factor_screen/latest.json"
    if not path.exists():
        return {"ok": False, "error": "no_factor_screen"}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        "ok": True,
        "recommendation": raw.get("recommendation"),
        "mom_picks": raw.get("ticker_mom_picks", [])[:5],
        "mom_avoids": raw.get("ticker_mom_avoids", [])[:5],
        "attention_picks_oos": raw.get("ticker_picks_oos", [])[:5],
        "top_factors": [
            {"factor": f.get("factor"), "verdict": f.get("verdict"), "ret_1w_2024_t": f.get("ret_1w_2024_t")}
            for f in raw.get("factor_summary_liquid", [])[:6]
            if f.get("verdict") not in (None, "skip")
        ],
    }


def tool_score_ticker(ctx: AnalystDataContext, *, ticker: str) -> dict[str, Any]:
    """Deterministic composite score from tool outputs — used for backtest baseline."""
    a = tool_analyze_ticker(ctx, ticker=ticker)
    if not a.get("ok"):
        return a
    score = 0.0
    reasons: list[str] = []
    mom = a.get("mom_4w_pct") or 0
    if mom > 5:
        score += 0.3
        reasons.append(f"mom_4w={mom}%")
    rsi = a.get("rsi14")
    if rsi is not None and 30 <= rsi <= 55:
        score += 0.2
        reasons.append(f"rsi={rsi}")
    retail_n = len(a.get("retail_signals") or [])
    if retail_n > 0:
        score += 0.35
        reasons.append(f"retail_active={retail_n}")
    ent = a.get("entity_news") or {}
    mentions = ent.get("entity_mention_rows") or 0
    if mentions > 0 and mentions < 80:
        score += 0.1
        reasons.append(f"mentions={mentions}")
    if mentions >= 120:
        score -= 0.15
        reasons.append(f"high_mention_fade={mentions}")
    r5 = a.get("ret_5d_pct") or 0
    if r5 > 15:
        score -= 0.1
        reasons.append(f"extended_5d={r5}%")
    return {"ok": True, "ticker": ticker, "score": round(score, 3), "reasons": reasons, "analysis": a}


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_regime",
        "description": "IHSG drawdown/bounce regime as of analysis date.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "screen_universe",
        "description": "Rank liquid IDX universe by momentum, weekly return, or mentions.",
        "parameters": {
            "type": "object",
            "properties": {
                "sort_by": {"type": "string", "enum": ["mom_4w", "return_1w", "entity_mention_rows"]},
                "top_n": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "analyze_ticker",
        "description": "Full single-name analysis: price, RSI, momentum, news mentions, retail signals.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "compare_tickers",
        "description": "Side-by-side comparison of 2-8 tickers.",
        "parameters": {
            "type": "object",
            "properties": {"tickers": {"type": "array", "items": {"type": "string"}}},
            "required": ["tickers"],
        },
    },
    {
        "name": "check_retail_signals",
        "description": "Which retail playbook strategies are active for a ticker.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_sentiment",
        "description": "Latest RapidAPI/public sentiment pulse for a ticker (live only).",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "factor_summary",
        "description": "Pre-computed factor screen summary (empirical priors).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "score_ticker",
        "description": "Deterministic composite score from computed features.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
]

_TOOL_FN: dict[str, Callable[..., dict[str, Any]]] = {
    "get_regime": lambda ctx, **kw: tool_get_regime(ctx, **kw),
    "screen_universe": lambda ctx, **kw: tool_screen_universe(ctx, **kw),
    "analyze_ticker": lambda ctx, **kw: tool_analyze_ticker(ctx, **kw),
    "compare_tickers": lambda ctx, **kw: tool_compare_tickers(ctx, **kw),
    "check_retail_signals": lambda ctx, **kw: tool_check_retail_signals(ctx, **kw),
    "get_sentiment": lambda ctx, **kw: tool_get_sentiment(ctx, **kw),
    "factor_summary": lambda ctx, **kw: tool_factor_summary(ctx),
    "score_ticker": lambda ctx, **kw: tool_score_ticker(ctx, **kw),
}


def execute_tool(ctx: AnalystDataContext, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    fn = _TOOL_FN.get(name)
    if not fn:
        return {"ok": False, "error": f"unknown_tool:{name}"}
    try:
        return fn(ctx, **(arguments or {}))
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tool": name}


def tools_prompt_block() -> str:
    return json.dumps(TOOL_SPECS, indent=2)


def deterministic_analyst_picks_panel(
    g: pd.DataFrame,
    *,
    seed_tickers: list[str] | None = None,
    max_picks: int = 3,
) -> dict[str, Any]:
    """Fast panel-only analyst for historical backtest (no yfinance)."""
    candidates: list[str] = []
    if seed_tickers:
        candidates.extend(seed_tickers)
    top = g.nlargest(12, "mom_4w")["yahoo_symbol"].tolist()
    candidates.extend(top)
    candidates = list(dict.fromkeys(candidates))[:12]

    scored = []
    for sym in candidates:
        row = g[g["yahoo_symbol"] == sym]
        if row.empty:
            continue
        r = row.iloc[0]
        score = 0.0
        reasons: list[str] = []
        mom = float(r.get("mom_4w") or 0) * 100
        if mom > 5:
            score += 0.3
            reasons.append(f"mom_4w={mom:.1f}%")
        ment = r.get("mention_rank_pct")
        if pd.notna(ment) and float(ment) < 0.8:
            score += 0.15
            reasons.append(f"mention_rank={float(ment):.2f}")
        if pd.notna(ment) and float(ment) >= 0.8:
            score -= 0.2
            reasons.append("high_mention_fade")
        r1 = float(r.get("return_1w") or 0) * 100
        if r1 > 12:
            score -= 0.1
            reasons.append(f"hot_week={r1:.1f}%")
        scored.append({"ticker": sym, "score": round(score, 3), "reasons": reasons})
    scored.sort(key=lambda x: -x["score"])
    return {"mode": "deterministic_panel", "picks": scored[:max_picks]}


def deterministic_analyst_picks(
    ctx: AnalystDataContext,
    *,
    seed_tickers: list[str] | None = None,
    max_picks: int = 3,
) -> dict[str, Any]:
    """Live tool pipeline (uses yfinance for technicals)."""
    regime = tool_get_regime(ctx)
    screen = tool_screen_universe(ctx, sort_by="mom_4w", top_n=12)
    candidates: list[str] = []
    if seed_tickers:
        candidates.extend(seed_tickers)
    for row in screen.get("top", [])[:8]:
        candidates.append(row["ticker"])
    candidates = list(dict.fromkeys([c for c in candidates if c in ctx.liquid]))[:12]
    scored = []
    for t in candidates:
        s = tool_score_ticker(ctx, ticker=t)
        if s.get("ok"):
            scored.append(s)
    scored.sort(key=lambda x: -x["score"])
    picks = scored[:max_picks]
    return {
        "mode": "deterministic_tools",
        "regime": regime,
        "picks": picks,
        "trace": [{"tool": "screen_universe", "result": screen}, {"tool": "score_batch", "n": len(scored)}],
    }
