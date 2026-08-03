from __future__ import annotations

import json
from typing import Any, Dict, Mapping


# Control-layer presets to avoid one-off CLI tuning every run.
CONTROL_PROFILES: Dict[str, Dict[str, Any]] = {
    "off": {
        "min_cash_weight": 0.0,
        "max_crypto_gross": 1.0,
        "cb_dd_trigger": 0.0,
        "cb_alpha_trigger": -0.02,
        "cb_alpha_window": 0,
        "cb_cooldown_months": 0,
        "cb_floor_gross": 1.0,
    },
    # Highest CAGR in recent control tests with materially improved drawdown vs no controls.
    "growth": {
        "min_cash_weight": 0.05,
        "max_crypto_gross": 0.75,
        "cb_dd_trigger": 0.0,
        "cb_alpha_trigger": -0.02,
        "cb_alpha_window": 0,
        "cb_cooldown_months": 0,
        "cb_floor_gross": 1.0,
    },
    # Keeps sleeve caps and enables moderate circuit-breaker behavior.
    "balanced": {
        "min_cash_weight": 0.05,
        "max_crypto_gross": 0.75,
        "cb_dd_trigger": 0.12,
        "cb_alpha_trigger": -0.015,
        "cb_alpha_window": 3,
        "cb_cooldown_months": 2,
        "cb_floor_gross": 0.45,
    },
    # Strongest risk controls; use when capital preservation dominates.
    "defensive": {
        "min_cash_weight": 0.10,
        "max_crypto_gross": 0.45,
        "cb_dd_trigger": 0.10,
        "cb_alpha_trigger": -0.015,
        "cb_alpha_window": 3,
        "cb_cooldown_months": 2,
        "cb_floor_gross": 0.30,
    },
    # Live-book preset: defensive + tighter crypto cap after promotion-gate failures.
    "defensive_live": {
        "min_cash_weight": 0.10,
        "max_crypto_gross": 0.35,
        "cb_dd_trigger": 0.10,
        "cb_alpha_trigger": -0.015,
        "cb_alpha_window": 3,
        "cb_cooldown_months": 2,
        "cb_floor_gross": 0.30,
    },
}


def available_profiles() -> list[str]:
    return sorted(CONTROL_PROFILES.keys())


def resolve_profile(name: str) -> Dict[str, Any]:
    key = str(name or "").strip().lower()
    if key not in CONTROL_PROFILES:
        raise ValueError(f"Unknown control profile: {name!r}. Available: {', '.join(available_profiles())}")
    return dict(CONTROL_PROFILES[key])


def apply_profile_to_namespace(namespace: Any, profile_name: str) -> Mapping[str, Any]:
    prof = resolve_profile(profile_name)
    for k, v in prof.items():
        setattr(namespace, k, v)
    return prof


def profiles_json() -> str:
    return json.dumps(CONTROL_PROFILES, indent=2, sort_keys=True)
