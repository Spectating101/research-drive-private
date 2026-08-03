"""Execution safety checks for live-adjacent workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class SafetyResult:
    passed: bool
    reasons: list[str]
    metrics: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "reasons": self.reasons, "metrics": self.metrics}


def load_safety_config(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def validate_target_weights(
    weights: Mapping[str, float],
    config: Mapping[str, Any],
    *,
    turnover_pct: float | None = None,
    drawdown: float | None = None,
) -> SafetyResult:
    kill_switch = bool(config.get("kill_switch", False))
    cash_ticker = str(config.get("cash_ticker", "CASH"))
    blocked = {str(t).upper() for t in config.get("blocked_tickers", [])}
    max_gross = float(config.get("max_gross_exposure", 1.0))
    max_name = float(config.get("max_single_name_weight", 1.0))
    max_turnover = float(config.get("max_turnover_per_rebalance", 1.0))
    max_dd = float(config.get("max_drawdown", -1.0))

    clean = {str(k).upper(): float(v) for k, v in weights.items()}
    investable = {k: v for k, v in clean.items() if k != cash_ticker.upper()}
    gross = sum(abs(v) for v in investable.values())
    max_weight = max((abs(v) for v in investable.values()), default=0.0)
    blocked_hits = sorted(t for t in investable if t in blocked and abs(investable[t]) > 1e-12)

    reasons: list[str] = []
    if kill_switch:
        reasons.append("kill_switch_enabled")
    if gross > max_gross + 1e-12:
        reasons.append(f"gross_exposure {gross:.4f} > {max_gross:.4f}")
    if max_weight > max_name + 1e-12:
        reasons.append(f"single_name_weight {max_weight:.4f} > {max_name:.4f}")
    if blocked_hits:
        reasons.append(f"blocked_tickers_present={blocked_hits}")
    if turnover_pct is not None and turnover_pct > max_turnover + 1e-12:
        reasons.append(f"turnover_pct {turnover_pct:.4f} > {max_turnover:.4f}")
    if drawdown is not None and drawdown < max_dd:
        reasons.append(f"drawdown {drawdown:.4f} < {max_dd:.4f}")

    return SafetyResult(
        passed=not reasons,
        reasons=reasons,
        metrics={
            "gross_exposure": gross,
            "max_single_name_weight": max_weight,
            "turnover_pct": float(turnover_pct) if turnover_pct is not None else 0.0,
            "drawdown": float(drawdown) if drawdown is not None else 0.0,
        },
    )
