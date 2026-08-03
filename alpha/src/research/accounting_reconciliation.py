"""Accounting reconciliation for investment cockpit artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.research.investment_cockpit import load_weights


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path | None) -> dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    obj = json.loads(Path(path).read_text())
    return obj if isinstance(obj, dict) else {}


def _latest_row(path: Path | None) -> dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    df = pd.read_csv(path)
    if df.empty:
        return {}
    return df.iloc[-1].to_dict()


def reconcile_accounting(
    *,
    target_weights_path: Path | None = None,
    orders_path: Path | None = None,
    fills_path: Path | None = None,
    positions_path: Path | None = None,
    equity_ledger_path: Path | None = None,
    scorecard_path: Path | None = None,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    """Reconcile the available accounting artifacts.

    The report is intentionally tolerant of missing artifacts because legacy
    strategies may only have a signal and equity ledger. Missing files become
    explicit checks instead of exceptions.
    """
    checks: dict[str, bool] = {}
    reasons: list[str] = []
    metrics: dict[str, float] = {}

    if target_weights_path:
        checks["target_weights_exists"] = Path(target_weights_path).exists()
        if checks["target_weights_exists"]:
            weights = load_weights(Path(target_weights_path))
            gross = sum(abs(float(v)) for k, v in weights.items() if str(k).upper() != "CASH")
            net = sum(float(v) for v in weights.values())
            metrics["target_gross"] = gross
            metrics["target_net"] = net
            checks["target_gross_le_1"] = gross <= 1.0 + tolerance
            checks["target_net_le_1"] = net <= 1.0 + tolerance
        else:
            reasons.append(f"missing target weights: {target_weights_path}")

    if orders_path:
        checks["orders_exists"] = Path(orders_path).exists()
        if checks["orders_exists"]:
            orders = pd.read_csv(orders_path)
            metrics["n_orders"] = float(len(orders))
            fee_col = "fee" if "fee" in orders.columns else None
            if fee_col:
                fees = pd.to_numeric(orders[fee_col], errors="coerce").fillna(0.0)
                metrics["order_fees"] = float(fees.sum())
                checks["order_fees_nonnegative"] = bool((fees >= 0).all())

    if fills_path:
        checks["fills_exists"] = Path(fills_path).exists()
        if checks.get("orders_exists") and checks["fills_exists"]:
            orders = pd.read_csv(orders_path)
            fills = pd.read_csv(fills_path)
            checks["fills_cover_orders"] = len(fills) >= len(orders)
            metrics["n_fills"] = float(len(fills))

    latest_ledger = _latest_row(equity_ledger_path)
    if equity_ledger_path:
        checks["equity_ledger_exists"] = Path(equity_ledger_path).exists()
        if latest_ledger:
            equity_key = "equity_after" if "equity_after" in latest_ledger else "equity"
            try:
                metrics["ledger_equity"] = float(latest_ledger[equity_key])
            except Exception:
                pass
            if "cash_after" in latest_ledger:
                try:
                    metrics["ledger_cash_after"] = float(latest_ledger["cash_after"])
                except Exception:
                    pass

    if positions_path:
        checks["positions_exists"] = Path(positions_path).exists()
        if checks["positions_exists"]:
            positions = pd.read_csv(positions_path)
            if "market_value" in positions.columns:
                mv = pd.to_numeric(positions["market_value"], errors="coerce").fillna(0.0)
                metrics["positions_market_value"] = float(mv.sum())
            if "weight" in positions.columns:
                w = pd.to_numeric(positions["weight"], errors="coerce").fillna(0.0)
                metrics["positions_gross_weight"] = float(w.abs().sum())
                checks["positions_gross_le_1"] = float(w.abs().sum()) <= 1.0 + tolerance

    if "positions_market_value" in metrics and "ledger_cash_after" in metrics and "ledger_equity" in metrics:
        reconstructed = metrics["positions_market_value"] + metrics["ledger_cash_after"]
        metrics["reconstructed_equity"] = reconstructed
        checks["positions_cash_match_equity"] = abs(reconstructed - metrics["ledger_equity"]) <= max(
            tolerance, abs(metrics["ledger_equity"]) * 1e-6
        )

    scorecard = _read_json(scorecard_path)
    if scorecard_path:
        checks["scorecard_exists"] = Path(scorecard_path).exists()
        perf = scorecard.get("performance", {}) if isinstance(scorecard, dict) else {}
        try:
            metrics["scorecard_latest_equity"] = float(perf["latest_equity"])
        except Exception:
            pass
        if "scorecard_latest_equity" in metrics and "ledger_equity" in metrics:
            checks["scorecard_matches_ledger"] = abs(metrics["scorecard_latest_equity"] - metrics["ledger_equity"]) <= max(
                tolerance, abs(metrics["ledger_equity"]) * 1e-6
            )

    for key, ok in checks.items():
        if not ok:
            reasons.append(key)
    return {
        "generated_at": _utc_now(),
        "passed": not reasons,
        "checks": checks,
        "metrics": metrics,
        "reasons": reasons,
        "inputs": {
            "target_weights_path": str(target_weights_path) if target_weights_path else None,
            "orders_path": str(orders_path) if orders_path else None,
            "fills_path": str(fills_path) if fills_path else None,
            "positions_path": str(positions_path) if positions_path else None,
            "equity_ledger_path": str(equity_ledger_path) if equity_ledger_path else None,
            "scorecard_path": str(scorecard_path) if scorecard_path else None,
        },
    }


def render_reconciliation_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Accounting Reconciliation",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Passed: `{report.get('passed')}`",
        "",
        "## Checks",
        "",
    ]
    for key, value in (report.get("checks") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Reasons", ""])
    reasons = report.get("reasons") or []
    if reasons:
        for reason in reasons:
            lines.append(f"- {reason}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def write_reconciliation_report(report: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / "latest.json"
    mp = out_dir / "latest.md"
    jp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    mp.write_text(render_reconciliation_markdown(report))
    return {"json": str(jp), "markdown": str(mp)}
