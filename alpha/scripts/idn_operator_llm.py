"""LLM reasoning layer for IDX operator brief.

Rules engine produces candidates; LLM reconciles momentum vs retail bounce vs sentiment.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)

from idn_operator_evidence import gather_full_platform_evidence

OPERATOR_DECISION_SCHEMA = {
    "stance": "aggressive | standard | defensive",
    "conviction_1_to_5": "integer 1-5",
    "final_picks": [
        {
            "ticker": "SYMBOL.JK from liquid universe only",
            "weight_hint": "0.0-1.0 — should sum to ~1 across picks",
            "primary_driver": "mom_leader | retail_bbca | washout_bounce | theme_banks | quiet_momentum | rules_override",
            "reason": "one sentence tied to evidence fields",
        }
    ],
    "avoid": [{"ticker": "SYMBOL.JK", "reason": "string"}],
    "watch": [{"ticker": "SYMBOL.JK", "reason": "string"}],
    "sentiment_crosscheck": "how public/retail narrative compares to quant inputs",
    "rules_vs_reality": "where lagging weekly rules disagree with fresh daily data",
    "reconcile_notes": "how you merged position sheet vs operator rules",
    "evidence_used": ["list of evidence sections actually consulted, e.g. regime_ihsg, factor_screen, retail_playbook_signals"],
    "evidence_missing": ["sections unavailable per evidence_catalog"],
    "kill_conditions": ["list — when to exit or stand down"],
    "falsifiers": ["list — what would prove this week's book wrong"],
    "summary": "2-3 sentences — actionable",
}


def _rsi14(rets) -> float | None:
    if len(rets) < 14:
        return None
    delta = rets.iloc[-14:]
    up = delta.clip(lower=0).mean()
    down = (-delta.clip(upper=0)).mean()
    if not down or down <= 0:
        return 100.0
    return float(100 - 100 / (1 + up / down))


def enrich_daily_crosscheck(manifest: dict[str, Any], liquid: list[str]) -> dict[str, Any]:
    """Attach fresh daily metrics for key names (rules picks + banks + movers)."""
    from idn_spike_explainer import fetch_history

    focus: set[str] = set()
    for key in ("pick", "avoid", "watch", "movers_up", "movers_down"):
        for row in manifest.get(key, []):
            sym = row.get("ticker") or row.get("yahoo_symbol")
            if sym:
                focus.add(str(sym))
    for sym in ("BBCA.JK", "BBRI.JK", "BMRI.JK", "BRIS.JK", "^JKSE"):
        focus.add(sym)
    focus = [s for s in sorted(focus) if s in liquid or s == "^JKSE"]

    end = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    close, _ = fetch_history(focus, "2025-01-01", end)
    if close.empty:
        manifest["daily_crosscheck"] = {"as_of": None, "names": []}
        return manifest

    weekly = close.resample("W-FRI").last().pct_change()
    rows: list[dict[str, Any]] = []
    for sym in focus:
        if sym == "^JKSE" or sym not in close.columns:
            continue
        s = close[sym].dropna()
        if len(s) < 10:
            continue
        ret = s.pct_change()
        last = float(s.iloc[-1])
        d5 = (last / float(s.iloc[-6]) - 1) * 100 if len(s) >= 6 else None
        d20 = (last / float(s.iloc[-21]) - 1) * 100 if len(s) >= 21 else None
        mom4w = None
        if sym in weekly.columns and len(weekly) >= 5:
            mom4w = float(weekly.iloc[-5:-1][sym].sum() * 100)
        rows.append(
            {
                "ticker": sym,
                "price_date": str(s.index[-1].date()),
                "close": round(last, 0),
                "ret_5d_pct": round(d5, 2) if d5 is not None else None,
                "ret_20d_pct": round(d20, 2) if d20 is not None else None,
                "mom_4w_fresh_pct": round(mom4w, 2) if mom4w is not None else None,
                "rsi14": round(_rsi14(ret), 1) if _rsi14(ret) is not None else None,
                "in_rules_pick": sym in {p["ticker"] for p in manifest.get("pick", [])},
                "in_rules_avoid": sym in {a["ticker"] for a in manifest.get("avoid", [])},
            }
        )

    manifest["daily_crosscheck"] = {
        "as_of": str(close.index[-1].date()),
        "names": sorted(rows, key=lambda x: -(x.get("ret_5d_pct") or -999)),
    }
    return manifest


def load_position_sheet_context() -> dict[str, Any]:
    root = REPO / "backtests/outputs/idn_weekly_position_sheet"
    port_path = root / "latest_portfolio.json"
    md_path = root / "latest.md"
    ctx: dict[str, Any] = {"available": False}
    if port_path.exists():
        port = json.loads(port_path.read_text(encoding="utf-8"))
        weights = port.get("weights") or {}
        top = sorted(
            [(k, v) for k, v in weights.items() if k != "CASH" and float(v) > 0],
            key=lambda x: -float(x[1]),
        )[:8]
        ctx = {
            "available": True,
            "as_of_week": port.get("as_of_week"),
            "weight_mode": port.get("weight_mode"),
            "regime": port.get("regime"),
            "top_weights": {k: round(float(v), 4) for k, v in top},
            "retail_active": port.get("retail_active"),
        }
    if md_path.exists():
        lines = md_path.read_text(encoding="utf-8").splitlines()
        ctx["actions"] = [ln.lstrip("- ").strip() for ln in lines if ln.startswith("- BUY") or ln.startswith("- OVERWEIGHT")][:5]
        ctx["retail_signals"] = [
            ln.lstrip("- ").strip() for ln in lines if ln.startswith("- **") and ("in_hold" in ln or "new_today" in ln)
        ][:6]
    return ctx


def build_evidence_pack(manifest: dict[str, Any], *, liquid: list[str]) -> dict[str, Any]:
    platform = gather_full_platform_evidence(manifest, liquid=liquid)
    return {
        "country": "IDN",
        "as_of_week": manifest.get("as_of_week"),
        "daily_as_of": (manifest.get("daily_crosscheck") or {}).get("as_of"),
        "ihsg": manifest.get("ihsg"),
        "mode": manifest.get("mode"),
        "data_freshness": manifest.get("data_freshness"),
        "philosophy": manifest.get("philosophy"),
        "evidence_catalog": platform.get("evidence_catalog"),
        "platform_evidence": platform.get("sections"),
        "rules_engine": {
            "pick": manifest.get("pick", []),
            "avoid": manifest.get("avoid", []),
            "watch": manifest.get("watch", []),
            "movers_up": manifest.get("movers_up", [])[:8],
            "movers_down": manifest.get("movers_down", [])[:8],
            "spikes_5d": manifest.get("spikes_5d", [])[:12],
            "theme_groups": manifest.get("theme_groups", [])[:6],
        },
        "daily_crosscheck": manifest.get("daily_crosscheck", {}),
        "position_sheet": load_position_sheet_context(),
        "liquid_universe_count": len(liquid),
        "allowed_tickers": sorted(liquid),
        "decision_schema": OPERATOR_DECISION_SCHEMA,
        "constraints": [
            "Only pick tickers from allowed_tickers.",
            "You MUST ground every pick/avoid in numeric fields from platform_evidence and rules_engine — cite section names.",
            "Respect research_empirics.lanes marked OFF — do not deploy killed strategies (news_ridge, spike_chase, mom20_breakout, broker_accdist).",
            "Weight factor_screen.recommendation and research_empirics.metrics before narrative.",
            "If entity_coverage shows entity_weeks_holdout < 40, down-weight fade_headline on mention rank; prefer absolute mention counts.",
            "Reconcile rules_engine with regime_ihsg, retail_playbook_signals, public_sentiment, and daily_crosscheck when they conflict.",
            "public_sentiment.ticker_pulse is retail attention — weight heavily for opportunity-first books.",
            "final_picks: 3-5 names for aggressive, 2-4 for standard; weights sum to 1.0.",
            "In reconcile_notes list which evidence sections you used and which were missing.",
        ],
        "gathered_at_utc": platform.get("gathered_at_utc"),
    }


def extract_operator_decision(text: str) -> dict | None:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "final_picks" not in data:
        return None
    return data


def _system_prompt() -> str:
    return (
        "You are a senior Indonesia equity operator on a quant desk. "
        "You receive a structured EVIDENCE_JSON assembled from the full research platform: "
        "factor screens, walk-forward/backtest metrics, GDELT entity/news layers, "
        "retail playbook signals, spike/bandar proxies, public sentiment APIs (RapidAPI trending, Reddit IDX), "
        "rules engine, and fresh daily prices. "
        "Your job is to DECIDE the weekly book by synthesizing ALL available sections — "
        "not to narrate vibes or mimic Telegram. "
        "Every pick and avoid MUST cite specific evidence paths (e.g. platform_evidence.regime_ihsg, "
        "platform_evidence.factor_screen, rules_engine.pick, daily_crosscheck.names). "
        "If a section is missing per evidence_catalog, say so and do not pretend you saw it. "
        "Strategies marked OFF in research_empirics.lanes are forbidden. "
        "Output fenced ```json matching decision_schema FIRST, then markdown sections."
    )


def _user_prompt(pack: dict[str, Any]) -> str:
    return (
        "Produce the IDX operator decision for this week.\n\n"
        f"EVIDENCE_JSON:\n{json.dumps(pack, indent=2, default=str)}\n\n"
        "Resolve tensions explicitly (e.g. BBCA rebound vs stale mom_leader on MAPI/UNVR/ISAT)."
    )


def synthesize_operator_decision(
    pack: dict[str, Any],
    *,
    backend: str = "auto",
    model: str = "",
    out_dir: Path | None = None,
    max_tokens: int = 2200,
) -> dict[str, Any]:
    from quant_ai.llm import _call_backend

    system = _system_prompt()
    user = _user_prompt(pack)
    result = _call_backend(system, user, backend, model, out_dir, max_tokens, pack=pack)
    result["operator_decision"] = extract_operator_decision(result.get("text", ""))
    return result


def normalize_llm_weights(picks: list[dict], *, liquid: set[str], max_names: int = 5) -> dict[str, float]:
    rows: list[tuple[str, float]] = []
    for p in picks[:max_names]:
        sym = str(p.get("ticker", "")).strip()
        if sym not in liquid:
            continue
        w = float(p.get("weight_hint", 0) or 0)
        if w <= 0:
            w = 1.0
        rows.append((sym, w))
    if not rows:
        return {}
    total = sum(w for _, w in rows)
    return {sym: round(w / total, 4) for sym, w in rows}


def portfolio_from_decision(
    decision: dict | None,
    manifest: dict[str, Any],
    *,
    liquid: list[str],
    max_names: int = 5,
) -> dict[str, Any] | None:
    if not decision or not decision.get("final_picks"):
        return None
    liquid_set = set(liquid)
    avoid = {str(a.get("ticker")) for a in decision.get("avoid", [])}
    weights = normalize_llm_weights(
        [p for p in decision["final_picks"] if str(p.get("ticker")) not in avoid],
        liquid=liquid_set,
        max_names=max_names,
    )
    if not weights:
        return None
    return {
        "strategy": "idn_operator_llm_reconciled",
        "as_of_week": manifest.get("as_of_week"),
        "built_at_utc": manifest.get("built_at_utc"),
        "daily_as_of": (manifest.get("daily_crosscheck") or {}).get("as_of"),
        "weights": weights,
        "avoid": sorted(avoid),
        "stance": decision.get("stance"),
        "conviction_1_to_5": decision.get("conviction_1_to_5"),
        "llm_summary": decision.get("summary"),
        "note": "LLM-reconciled book — full platform evidence pack (see evidence_pack.json).",
    }
