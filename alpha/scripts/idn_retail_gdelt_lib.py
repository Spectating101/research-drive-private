"""GDELT entity context, bandar confirm, and position caps for IDX retail sheet."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from idn_fry_gdelt_crossref_lib import SHOCK_COLS
from idn_panel_cache import (
    REPO,
    load_bandar_lite_snapshot,
    load_entity_idn_daily,
)

# OOS-validated retail rules — prefer when multiple compounders fire.
VALIDATED_RETAIL_PRIORITY = (
    "BBCA.JK",
    "BBRI.JK",
    "BMRI.JK",
    "BBNI.JK",
)

BANDAR_BULLISH_LABELS = frozenset({"squeeze_from_drawdown", "unclear"})
BANDAR_BEARISH_LABELS = frozenset({"chase_into_spike", "momentum_chase"})
BANDAR_WEAK_LABELS = frozenset({"quiet_volume_build"})

SENTIMENT_LATEST = REPO / "data_lake/sentiment/idn_public_sentiment_latest.json"


def _load_sentiment_pulse_map() -> dict[str, dict[str, Any]]:
    if not SENTIMENT_LATEST.exists():
        return {}
    try:
        data = json.loads(SENTIMENT_LATEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in data.get("ticker_pulse", []) or []:
        sym = row.get("yahoo_symbol")
        if sym:
            out[str(sym)] = row
    for row in (data.get("providers", {}).get("rapidapi_symbol_intel", {}) or {}).get("symbols", []) or []:
        sym = row.get("yahoo_symbol")
        if sym and sym not in out:
            out[str(sym)] = row
        elif sym:
            out[str(sym)] = {**out[str(sym)], **row}
    return out


def entity_scores_for_symbols(
    symbols: list[str],
    as_of: str | pd.Timestamp,
    *,
    lookback_days: int = 5,
) -> dict[str, dict[str, Any]]:
    """Rolling GDELT entity mention/shock stats per symbol (cached .JK panel)."""
    out: dict[str, dict[str, Any]] = {}
    if not symbols:
        return out

    df = load_entity_idn_daily()
    as_of_ts = pd.Timestamp(as_of)
    if df.empty:
        for sym in symbols:
            out[sym] = {
                "available": False,
                "mention_rows_sum": 0,
                "shock_rows_sum": 0,
                "active_days": 0,
                "score": 0.0,
            }
        return out

    start = as_of_ts - pd.Timedelta(days=int(lookback_days))
    sub = df[
        df["yahoo_symbol"].isin(symbols)
        & (df["date"] >= start)
        & (df["date"] <= as_of_ts)
    ].copy()
    shock_cols = [c for c in SHOCK_COLS if c in sub.columns]
    if shock_cols:
        sub["shock_row_sum"] = sub[shock_cols].sum(axis=1)
    else:
        sub["shock_row_sum"] = 0

    for sym in symbols:
        rows = sub[sub["yahoo_symbol"] == sym]
        if rows.empty:
            out[sym] = {
                "available": True,
                "mention_rows_sum": 0,
                "shock_rows_sum": 0,
                "active_days": 0,
                "score": 0.0,
            }
            continue
        mention = int(rows["entity_mention_rows"].fillna(0).sum()) if "entity_mention_rows" in rows else 0
        shock = float(rows["shock_row_sum"].sum())
        active_days = int((rows["entity_mention_rows"].fillna(0) > 0).sum()) if "entity_mention_rows" in rows else 0
        out[sym] = {
            "available": True,
            "mention_rows_sum": mention,
            "shock_rows_sum": shock,
            "active_days": active_days,
            "score": float(mention + 0.25 * shock),
        }
    return out


def _accumulation_signal(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    accum = row.get("bandar_accumulation") or row.get("accumulation")
    if isinstance(accum, dict):
        sig = accum.get("signal") or accum.get("status") or accum.get("recommendation")
        if sig:
            return str(sig).lower()
    if isinstance(accum, str) and accum.strip():
        return accum.lower()
    return None


def bandar_scores_for_symbols(
    symbols: list[str],
    as_of: str | pd.Timestamp,
) -> dict[str, dict[str, Any]]:
    """Bandar-lite + cached broker + sentiment accumulation context."""
    as_of_ts = pd.Timestamp(as_of)
    as_of_str = str(as_of_ts.date())
    labels = {}
    snap = load_bandar_lite_snapshot(as_of_ts)
    if not snap.empty:
        labels = snap.set_index("yahoo_symbol")["bandar_lite_label"].astype(str).to_dict()

    pulse = _load_sentiment_pulse_map()
    out: dict[str, dict[str, Any]] = {}

    for sym in symbols:
        label = str(labels.get(sym, "unclear"))
        pulse_row = pulse.get(sym, {})
        accum_sig = _accumulation_signal(pulse_row)

        broker_ctx: dict[str, Any] = {"available": False}
        try:
            from idn_fry_broker_lib import broker_context_for_symbol

            broker_ctx = broker_context_for_symbol(sym, as_of_str)
        except Exception:
            broker_ctx = {"available": False}

        broker_accdist = broker_ctx.get("broker_accdist") if broker_ctx.get("available") else None
        confirmed = (
            label in BANDAR_BULLISH_LABELS
            or broker_accdist == "Acc"
            or (accum_sig is not None and any(k in accum_sig for k in ("acc", "accum", "buy")))
        )
        rejected = (
            label in BANDAR_BEARISH_LABELS
            or broker_accdist == "Dist"
            or (accum_sig is not None and any(k in accum_sig for k in ("dist", "sell", "distribution")))
        )

        score = 0.0
        if label == "squeeze_from_drawdown":
            score += 2.0
        elif label in BANDAR_WEAK_LABELS:
            score -= 0.5
        if broker_accdist == "Acc":
            score += 1.5
        elif broker_accdist == "Dist":
            score -= 2.0
        if accum_sig and any(k in accum_sig for k in ("acc", "accum")):
            score += 1.0
        if confirmed:
            score += 0.5
        if rejected:
            score -= 2.5

        out[sym] = {
            "available": bool(labels) or pulse_row or broker_ctx.get("available"),
            "bandar_lite_label": label,
            "broker_accdist": broker_accdist,
            "broker_available": bool(broker_ctx.get("available")),
            "accumulation_signal": accum_sig,
            "confirmed": bool(confirmed and not rejected),
            "rejected": bool(rejected),
            "score": float(score),
        }
    return out


def _rank_symbols(
    symbols: list[str],
    gdelt_scores: dict[str, dict[str, Any]],
    bandar_scores: dict[str, dict[str, Any]] | None,
) -> list[str]:
    bandar_scores = bandar_scores or {}

    def _key(sym: str) -> tuple:
        b = bandar_scores.get(sym, {})
        g = gdelt_scores.get(sym, {})
        return (
            sym in VALIDATED_RETAIL_PRIORITY,
            -int(b.get("rejected", False)),
            int(b.get("confirmed", False)),
            VALIDATED_RETAIL_PRIORITY.index(sym) if sym in VALIDATED_RETAIL_PRIORITY else 99,
            float(g.get("score", 0.0)) + float(b.get("score", 0.0)),
        )

    return sorted(symbols, key=_key, reverse=True)


def filter_retail_symbols(
    symbols: list[str],
    scores: dict[str, dict[str, Any]],
    *,
    mode: str = "prefer",
    min_mention_rows: int = 1,
    bandar_scores: dict[str, dict[str, Any]] | None = None,
    bandar_mode: str = "off",
) -> tuple[list[str], dict[str, Any]]:
    """Apply GDELT + optional bandar conditioning to retail entry candidates."""
    mode = (mode or "off").strip().lower()
    bandar_mode = (bandar_mode or "off").strip().lower()
    report: dict[str, Any] = {
        "mode": mode,
        "bandar_mode": bandar_mode,
        "input_symbols": list(symbols),
        "min_mention_rows": int(min_mention_rows),
        "scores": scores,
        "bandar_scores": bandar_scores or {},
    }
    if not symbols:
        report["output_symbols"] = []
        report["action"] = "empty"
        return [], report

    if mode == "off" and bandar_mode == "off":
        report["output_symbols"] = list(symbols)
        report["action"] = "passthrough"
        return list(symbols), report

    ranked = _rank_symbols(symbols, scores, bandar_scores)

    if bandar_mode == "require" and bandar_scores:
        kept = [s for s in ranked if bandar_scores.get(s, {}).get("confirmed") and not bandar_scores.get(s, {}).get("rejected")]
        if kept:
            ranked = kept
            report["bandar_action"] = "required_confirmed"
        else:
            report["bandar_action"] = "fail_open_bandar_require_empty"

    if mode == "require":
        panel_available = any(v.get("available") for v in scores.values())
        if not panel_available:
            report["output_symbols"] = ranked
            report["action"] = "fail_open_no_gdelt_panel"
            return ranked, report
        kept = [
            s
            for s in ranked
            if int(scores.get(s, {}).get("mention_rows_sum", 0)) >= int(min_mention_rows)
            or int(scores.get(s, {}).get("active_days", 0)) > 0
        ]
        if kept:
            report["output_symbols"] = kept
            report["action"] = "required_mentions"
            return kept, report
        report["output_symbols"] = ranked
        report["action"] = "fail_open_require_empty"
        return ranked, report

    report["output_symbols"] = ranked
    report["action"] = "prefer_ranked"
    return ranked, report


def cap_single_name_weights(
    weights: dict[str, float],
    rationale: dict[str, str],
    *,
    max_weight: float = 0.25,
) -> tuple[dict[str, float], dict[str, str], dict[str, Any]]:
    """Cap any non-cash line; excess flows to CASH."""
    cap = float(max_weight)
    meta: dict[str, Any] = {"max_single_name_weight": cap, "capped": []}
    if cap <= 0 or cap >= 1.0:
        return weights, rationale, meta

    freed = 0.0
    for sym, wt in list(weights.items()):
        if sym == "CASH" or wt <= cap + 1e-12:
            continue
        freed += wt - cap
        weights[sym] = cap
        rationale[sym] = (rationale.get(sym, "") + f" [cap {cap:.0%}]").strip()
        meta["capped"].append({"symbol": sym, "to": cap})

    if freed > 1e-9:
        weights["CASH"] = weights.get("CASH", 0.0) + freed
        rationale["CASH"] = (rationale.get("CASH", "") + f" +{freed:.1%} from single-name cap").strip()

    return weights, rationale, meta
