"""Transparent beta fallback when alpha promotion gates fail.

Keeps capital invested in a declared multi-asset book without crypto
concentration and without reusing a rejected alpha prior.
"""

from __future__ import annotations

from typing import Any, Mapping

# No crypto: honest "still invested" book while research continues.
DEFAULT_BETA_CORE_WEIGHTS: dict[str, float] = {
    "BIL": 0.20,
    "SPY": 0.18,
    "EFA": 0.12,
    "EEM": 0.10,
    "TLT": 0.12,
    "IEF": 0.08,
    "GLD": 0.10,
    "DBC": 0.10,
}

STRATEGY_ID = "beta_core_fallback"


def beta_core_weights(
    *,
    template: Mapping[str, float] | None = None,
    available: set[str] | None = None,
) -> dict[str, float]:
    """Return normalized beta weights, optionally restricted to available tickers."""
    raw = dict(template or DEFAULT_BETA_CORE_WEIGHTS)
    if available is not None:
        raw = {k: float(v) for k, v in raw.items() if k in available and float(v) > 0}
    if not raw:
        raw = {"BIL": 1.0}
    total = sum(float(v) for v in raw.values())
    if total <= 0:
        return {"BIL": 1.0}
    return {str(k): float(v) / total for k, v in raw.items()}


def apply_beta_fallback(
    signal: dict[str, Any],
    *,
    reasons: list[str] | None = None,
    available: set[str] | None = None,
) -> dict[str, Any]:
    """Mutate signal in place to beta_core fallback; return the same dict."""
    weights = beta_core_weights(available=available)
    prior_strategy = signal.get("strategy")
    prior_weights = dict(signal.get("weights") or {})
    signal["strategy"] = STRATEGY_ID
    signal["weights"] = weights
    signal["alpha_book"] = "beta"
    gate = signal.setdefault("promotion_gate", {})
    if not isinstance(gate, dict):
        gate = {}
        signal["promotion_gate"] = gate
    gate["blocked"] = True
    gate["kept_prior_weights"] = False
    gate["fallback"] = STRATEGY_ID
    gate["fallback_reasons"] = list(reasons or gate.get("reasons") or [])
    gate["rejected_strategy"] = prior_strategy
    gate["rejected_weights"] = prior_weights
    return signal
