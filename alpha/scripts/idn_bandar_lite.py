"""Bandarmology proxies from price + volume only (no broker-summary API).

Heuristics inspired by quiet accumulation / chase / distribution labels.
Not a substitute for per-broker IDX data — use when Spectator/API lane is down.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _vol_ratio_series(vol: pd.Series, window: int = 20) -> pd.Series:
    base = vol.rolling(window, min_periods=5).mean().shift(1)
    return vol / base.replace(0, np.nan)


def bandar_lite_features(
    prices: pd.Series,
    volume: pd.Series,
    as_of: pd.Timestamp,
    *,
    lookback: int = 5,
) -> dict[str, Any]:
    """Compute pre-spike flow proxies on T-lookback..T-1 (excludes spike day)."""
    px = pd.to_numeric(prices, errors="coerce").dropna()
    vol = pd.to_numeric(volume, errors="coerce").reindex(px.index)
    if as_of not in px.index:
        return {"available": False, "reason": "as_of_not_in_panel"}

    loc = px.index.get_loc(as_of)
    if loc < lookback + 1:
        return {"available": False, "reason": "insufficient_history"}

    pre_idx = px.index[loc - lookback : loc]
    spike_prev = px.index[loc - 1]
    rets = px.pct_change().loc[pre_idx]
    vrat = _vol_ratio_series(vol).loc[pre_idx]

    quiet_days = int(((vrat >= 1.25) & (rets.abs() <= 0.03)).sum())
    chase_days = int(((vrat >= 1.5) & (rets > 0.03)).sum())
    vol5 = float(vol.loc[pre_idx].sum())
    vol20 = float(vol.iloc[max(0, loc - 20) : loc].sum())
    vol_intensity = (vol5 / vol20 * (20 / lookback)) if vol20 > 0 else float("nan")

    prior_5d_ret = float(px.loc[spike_prev] / px.loc[pre_idx[0]] - 1.0)
    prior_1d_ret = float(px.loc[spike_prev] / px.loc[px.index[loc - 2]] - 1.0) if loc >= 2 else float("nan")

    labels: list[str] = []
    if quiet_days >= 3 and prior_5d_ret < 0.08:
        labels.append("quiet_volume_build")
    if prior_5d_ret >= 0.12 and chase_days >= 2:
        labels.append("chase_into_spike")
    if prior_5d_ret >= 0.15 and vol_intensity >= 1.8:
        labels.append("momentum_chase")
    if prior_5d_ret <= -0.08 and vol_intensity >= 1.4:
        labels.append("squeeze_from_drawdown")
    if not labels:
        labels.append("unclear")

    return {
        "available": True,
        "lookback_days": lookback,
        "window_start": str(pre_idx[0].date()),
        "window_end": str(spike_prev.date()),
        "prior_5d_return_pct": round(prior_5d_ret * 100, 2),
        "prior_1d_return_pct": round(prior_1d_ret * 100, 2) if np.isfinite(prior_1d_ret) else None,
        "quiet_accum_days": quiet_days,
        "chase_days": chase_days,
        "vol_intensity_vs_20d": round(vol_intensity, 2) if np.isfinite(vol_intensity) else None,
        "labels": labels,
        "primary_label": labels[0],
        "note": "volume/price proxy only — not broker-code bandarmology",
    }


def bandar_lite_hypotheses(facts: dict) -> list[dict]:
    bl = facts.get("bandar_lite") or {}
    if not bl.get("available"):
        return []

    hyps: list[dict] = []
    label = bl.get("primary_label")
    if label == "quiet_volume_build":
        hyps.append(
            {
                "id": "bandar_lite_quiet_accum",
                "confidence": 0.6,
                "text": (
                    f"Pre-spike: {bl.get('quiet_accum_days')} quiet high-volume days in prior 5 sessions "
                    f"(price flat, volume elevated) — pattern consistent with accumulation before a limit-up day, "
                    "but broker codes unverified."
                ),
            }
        )
    elif label in {"chase_into_spike", "momentum_chase"}:
        hyps.append(
            {
                "id": "bandar_lite_chase",
                "confidence": 0.65,
                "text": (
                    f"Prior 5d return {bl.get('prior_5d_return_pct'):+.1f}% with elevated volume into spike — "
                    "looks like chase/momentum, not quiet bandar accumulation."
                ),
            }
        )
    elif label == "squeeze_from_drawdown":
        hyps.append(
            {
                "id": "bandar_lite_squeeze",
                "confidence": 0.7,
                "text": (
                    "Volume built after a drawdown into the spike — short-cover / mean-reversion squeeze pattern "
                    "(common on IDX ARA days)."
                ),
            }
        )

    broker = facts.get("bandar_broker")
    if broker and broker.get("available"):
        hyps.append(
            {
                "id": "bandar_broker_data",
                "confidence": 0.75,
                "text": broker.get("summary_text", "Broker-summary data present for this window."),
            }
        )

    return hyps
