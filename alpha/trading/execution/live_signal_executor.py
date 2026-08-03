from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .broker_base import Broker, OrderRequest


@dataclass(frozen=True)
class SafetyConfig:
    allowed_symbols: Optional[List[str]] = None
    treat_cash_symbol_as_cash: bool = True
    cash_symbol: str = "BIL"
    allow_shorts: bool = False
    max_gross_exposure: Optional[float] = None
    max_short_exposure: Optional[float] = None
    max_turnover: float = 0.60
    min_order_notional: float = 50.0
    max_order_notional: float = 50_000.0
    max_orders: int = 20
    order_type: str = "limit"  # limit/market
    limit_buffer_bps: float = 15.0  # limit price away from reference price
    time_in_force: str = "day"
    stale_signal_days: int = 3
    reference_date: Optional[str] = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_signal_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def load_signal(signal_path: Path) -> dict:
    return json.loads(signal_path.read_text())


def _load_live_state(path: Path) -> dict:
    if not path.exists():
        return {"last_executed_as_of": "", "executions": []}
    return json.loads(path.read_text())


def _save_live_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")


def _weights_sum(weights: Dict[str, float]) -> float:
    return float(sum(float(v) for v in weights.values()))


def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    total = _weights_sum(weights)
    if total <= 0:
        return dict(weights)
    return {k: float(v) / total for k, v in weights.items()}


def _bps_to_frac(bps: float) -> float:
    return float(bps) / 10_000.0


def compute_rebalance_orders(
    *,
    broker: Broker,
    signal: dict,
    safety: SafetyConfig,
    live_state_path: Path,
    execute: bool,
    allow_repeat_as_of: bool,
) -> Tuple[List[dict], List[OrderRequest]]:
    """
    Returns:
      (preflight_notes, orders)
    """
    notes: List[dict] = []

    if os.getenv("TRADING_KILL_SWITCH", "").strip() == "1":
        raise RuntimeError("TRADING_KILL_SWITCH=1 set; refusing to trade.")

    as_of = str(signal.get("as_of") or "")
    if not as_of:
        raise ValueError("signal.json missing as_of.")

    # Staleness check (date-only).
    as_of_dt = _parse_signal_datetime(as_of)
    reference_dt = _parse_signal_datetime(str(safety.reference_date)) if safety.reference_date else _now_utc()
    age_days = int((reference_dt.date() - as_of_dt.date()).days)
    if age_days < 0:
        raise RuntimeError(f"Signal as_of={as_of} is in the future relative to reference_date={reference_dt.date()}.")
    if age_days > int(safety.stale_signal_days):
        raise RuntimeError(f"Signal is stale (age_days={age_days} > {safety.stale_signal_days}).")

    weights = {str(k): float(v) for k, v in (signal.get("weights") or {}).items()}
    if not weights:
        raise ValueError("signal.json missing weights.")
    if not bool(safety.allow_shorts):
        for sym, w in weights.items():
            if w < -1e-9:
                raise RuntimeError(f"Negative weight not allowed for live executor: {sym}={w}")

    total = _weights_sum(weights)
    if abs(total - 1.0) > 1e-3:
        notes.append({"type": "normalize_weights", "old_sum": total})
        weights = _normalize_weights(weights)

    allowed = set(safety.allowed_symbols or [])
    if allowed:
        bad = [s for s in weights.keys() if s not in allowed]
        if bad:
            raise RuntimeError(f"Signal contains symbols not in allowed list: {bad}")

    account = broker.get_account()
    positions = {p.symbol: p for p in broker.list_positions()}
    equity = float(account.equity)
    if equity <= 0:
        raise RuntimeError("Broker reported non-positive equity.")

    cash_symbol = str(safety.cash_symbol or "")
    if safety.treat_cash_symbol_as_cash and cash_symbol in weights:
        # We treat this as "hold cash" and avoid trading the ETF.
        notes.append({"type": "cash_symbol_as_cash", "symbol": cash_symbol, "weight": weights[cash_symbol]})
        weights = dict(weights)
        weights.pop(cash_symbol, None)

    # Convert target weights -> target dollars.
    targets_usd = {sym: float(w) * equity for sym, w in weights.items()}

    # Current dollars (approx via market_value).
    cur_usd = {sym: float(pos.market_value) for sym, pos in positions.items()}

    # Gross / short exposure gates (important for shorting / margin-style behaviour).
    if bool(safety.allow_shorts):
        gross_target = float(sum(abs(v) for v in targets_usd.values())) / max(1e-9, equity)
        short_target = float(sum(-v for v in targets_usd.values() if v < 0.0)) / max(1e-9, equity)
        notes.append({"type": "target_exposure", "gross": gross_target, "short": short_target})
        if safety.max_gross_exposure is not None and gross_target > float(safety.max_gross_exposure) + 1e-9:
            raise RuntimeError(f"Target gross exposure too high: {gross_target:.3f} > {float(safety.max_gross_exposure):.3f}")
        if safety.max_short_exposure is not None and short_target > float(safety.max_short_exposure) + 1e-9:
            raise RuntimeError(f"Target short exposure too high: {short_target:.3f} > {float(safety.max_short_exposure):.3f}")

    # Turnover check (sum abs dollar changes / equity).
    turnover = float(
        sum(abs(targets_usd.get(s, 0.0) - cur_usd.get(s, 0.0)) for s in set(targets_usd) | set(cur_usd))
    ) / max(1e-9, equity)
    invested_ratio = float(sum(abs(v) for v in cur_usd.values())) / max(1e-9, equity)
    # Bootstrapping: when starting from (near) all-cash, turnover will naturally be high.
    # Only enforce the turnover gate once the portfolio has meaningful exposure.
    if invested_ratio >= 0.05 and turnover > float(safety.max_turnover):
        raise RuntimeError(
            f"Turnover too high for live execution: {turnover:.2f} > {safety.max_turnover:.2f} (invested_ratio={invested_ratio:.2f})"
        )

    # Build orders: close positions not in targets, then adjust remaining.
    close_orders: List[OrderRequest] = []
    rebalance_orders: List[OrderRequest] = []

    # Close out-of-signal positions.
    for sym, pos in positions.items():
        if sym in targets_usd:
            continue
        if cash_symbol and safety.treat_cash_symbol_as_cash and sym == cash_symbol:
            continue
        px = broker.get_last_price(sym)
        ref_price = float(px) if px else None
        if ref_price is None:
            # If no live price available, skip forcing a close.
            notes.append({"type": "skip_close_no_price", "symbol": sym})
            continue
        notional = float(abs(float(pos.qty))) * ref_price
        if notional < float(safety.min_order_notional):
            continue
        side = "SELL" if float(pos.qty) > 0 else "BUY"
        limit_price = None
        if safety.order_type == "limit":
            if side == "SELL":
                limit_price = ref_price * (1.0 - _bps_to_frac(safety.limit_buffer_bps))
            else:
                limit_price = ref_price * (1.0 + _bps_to_frac(safety.limit_buffer_bps))
        close_orders.append(
            OrderRequest(
                symbol=sym,
                side=side,
                qty=float(abs(float(pos.qty))),
                order_type=safety.order_type,
                time_in_force=safety.time_in_force,
                limit_price=limit_price,
            )
        )

    # Adjust in-signal symbols using notional deltas (if possible).
    for sym, tgt in targets_usd.items():
        px = broker.get_last_price(sym)
        ref_price = float(px) if px else None
        if ref_price is None:
            notes.append({"type": "skip_rebalance_no_price", "symbol": sym})
            continue
        cur = float(cur_usd.get(sym, 0.0))
        delta = float(tgt - cur)
        if abs(delta) < float(safety.min_order_notional):
            continue
        if abs(delta) > float(safety.max_order_notional):
            raise RuntimeError(f"Order too large for {sym}: {abs(delta):.2f} > {safety.max_order_notional:.2f}")
        side = "BUY" if delta > 0 else "SELL"
        if side == "SELL":
            if not bool(safety.allow_shorts):
                # Cap sell size by current qty (avoid shorting).
                pos = positions.get(sym)
                if not pos or pos.qty <= 0:
                    continue
                qty = min(float(pos.qty), abs(delta) / ref_price)
                if qty * ref_price < float(safety.min_order_notional):
                    continue
                rebalance_orders.append(
                    OrderRequest(
                        symbol=sym,
                        side="SELL",
                        qty=float(qty),
                        order_type=safety.order_type,
                        time_in_force=safety.time_in_force,
                        limit_price=(ref_price * (1.0 - _bps_to_frac(safety.limit_buffer_bps))) if safety.order_type == "limit" else None,
                    )
                )
            else:
                # Qty-based sells so a broker can short (SELL beyond current holdings).
                qty = float(abs(delta) / ref_price)
                if qty * ref_price < float(safety.min_order_notional):
                    continue
                rebalance_orders.append(
                    OrderRequest(
                        symbol=sym,
                        side="SELL",
                        qty=float(qty),
                        order_type=safety.order_type,
                        time_in_force=safety.time_in_force,
                        limit_price=(ref_price * (1.0 - _bps_to_frac(safety.limit_buffer_bps))) if safety.order_type == "limit" else None,
                    )
                )
        else:
            # Prefer notional buys (fractional-friendly), but allow qty if broker doesn't support it downstream.
            rebalance_orders.append(
                OrderRequest(
                    symbol=sym,
                    side="BUY",
                    notional=float(abs(delta)),
                    order_type=safety.order_type,
                    time_in_force=safety.time_in_force,
                    limit_price=(ref_price * (1.0 + _bps_to_frac(safety.limit_buffer_bps))) if safety.order_type == "limit" else None,
                )
            )

    # Execution ordering (cash-friendly): closes first, and SELL before BUY.
    close_orders = sorted(close_orders, key=lambda o: 0 if str(o.side).upper() == "SELL" else 1)
    rebalance_orders = sorted(rebalance_orders, key=lambda o: 0 if str(o.side).upper() == "SELL" else 1)
    orders: List[OrderRequest] = close_orders + rebalance_orders

    if len(orders) > int(safety.max_orders):
        raise RuntimeError(f"Too many orders ({len(orders)}) > max_orders={safety.max_orders}")

    # Idempotency: refuse to execute same as_of twice unless forced.
    state = _load_live_state(live_state_path)
    last = str(state.get("last_executed_as_of") or "")
    if execute and (not allow_repeat_as_of) and last == as_of:
        raise RuntimeError(f"Refusing to execute as_of={as_of} twice (use --allow-repeat-as-of to override).")

    return notes, orders


def record_execution(
    *,
    live_state_path: Path,
    as_of: str,
    broker_name: str,
    orders: List[dict],
    results: List[dict],
) -> None:
    state = _load_live_state(live_state_path)
    state["last_executed_as_of"] = as_of
    state.setdefault("executions", [])
    state["executions"].append(
        {
            "timestamp_utc": _now_utc().isoformat(),
            "as_of": as_of,
            "broker": broker_name,
            "orders": orders,
            "results": results,
        }
    )
    # Cap growth.
    state["executions"] = state["executions"][-200:]
    _save_live_state(live_state_path, state)
