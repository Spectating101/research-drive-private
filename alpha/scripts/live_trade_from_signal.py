#!/usr/bin/env python3
"""
Safest-possible live executor for `signal.json` (broker optional).

Defaults:
  - DRY RUN (no orders placed)
  - strict preflight checks
  - requires explicit `--execute` to place orders

Supported broker (optional):
  - Alpaca (REST) via env vars:
      ALPACA_API_KEY_ID
      ALPACA_SECRET_KEY
      ALPACA_BASE_URL (default paper endpoint)
      ALPACA_DATA_BASE_URL (optional, for live last prices)

This does not remove market risk. It only reduces "fat-finger / bot-runaway" risk.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

import sys

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
_SR_ROOT = _bmod.bootstrap_repo_paths(__file__)
if str(_SR_ROOT) not in sys.path:
    sys.path.insert(0, str(_SR_ROOT))


def _repo_path(path_like: str | Path) -> Path:
    path = Path(path_like)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == _SR_ROOT.name:
        path = Path(*path.parts[1:]) if len(path.parts) > 1 else Path(".")
    return (_SR_ROOT / path).resolve()

from trading.execution.alpaca_broker import AlpacaBroker  # noqa: E402
from trading.execution.file_broker import FileBroker  # noqa: E402
from trading.execution.broker_base import Broker, OrderRequest  # noqa: E402
from trading.execution.live_signal_executor import (  # noqa: E402
    SafetyConfig,
    compute_rebalance_orders,
    load_signal,
    record_execution,
)
from src.research.execution_safety import load_safety_config, validate_target_weights  # noqa: E402


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def _broker_from_args(args) -> Broker:
    if args.broker == "alpaca":
        return AlpacaBroker(base_url=args.alpaca_base_url, timeout_s=float(args.timeout_s))
    if args.broker == "file":
        if args.file_state is None or args.file_panel is None:
            raise RuntimeError("--broker file requires --file-state and --file-panel")
        return FileBroker(
            state_json=args.file_state,
            panel_csv=args.file_panel,
            cash_symbol=str(args.cash_symbol),
            allow_shorts=bool(args.allow_shorts),
            margin_multiplier=2.0 if bool(args.allow_shorts) else 1.0,
        )
    raise RuntimeError(f"Unsupported broker: {args.broker}")


def _check_platform_safety(signal: dict, config_path: Path) -> dict:
    if not config_path.exists():
        raise SystemExit(f"Refusing to continue: platform safety config missing at {config_path}")
    weights = signal.get("weights") or signal.get("target_weights") or {}
    if not isinstance(weights, dict) or not weights:
        raise SystemExit("Refusing to continue: signal has no weights for platform safety check.")
    result = validate_target_weights(weights, load_safety_config(config_path))
    if not result.passed:
        raise SystemExit(
            "Refusing to continue: platform execution safety failed: "
            + "; ".join(result.reasons)
        )
    return result.as_dict()


def main() -> int:
    ap = argparse.ArgumentParser(description="Live trade executor (safe by default).")
    ap.add_argument("--signal-json", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=_SR_ROOT / "backtests" / "outputs" / "spy_beater" / "live_exec")
    ap.add_argument("--live-state", type=Path, default=_SR_ROOT / "backtests" / "outputs" / "spy_beater" / "live_state.json")
    ap.add_argument("--broker", choices=["alpaca", "file"], default="alpaca")
    ap.add_argument("--timeout-s", type=float, default=10.0)
    ap.add_argument("--alpaca-base-url", type=str, default=None, help="Override ALPACA_BASE_URL")
    ap.add_argument("--file-state", type=Path, default=None, help="(broker=file) JSON with {cash, positions}")
    ap.add_argument("--file-panel", type=Path, default=None, help="(broker=file) tidy panel CSV for last prices")
    ap.add_argument(
        "--platform-safety-config",
        type=Path,
        default=_SR_ROOT / "config" / "execution_safety.json",
        help="Shared platform safety config; kill switch and exposure caps are enforced before broker access.",
    )
    ap.add_argument(
        "--skip-platform-safety",
        action="store_true",
        help="Dry-run/debug only. Forbidden with --execute.",
    )

    ap.add_argument("--execute", action="store_true", help="Actually place orders (otherwise dry-run).")
    ap.add_argument(
        "--ack-live-risk",
        action="store_true",
        help="Required with --execute. Confirms you understand this places live orders and market risk remains.",
    )
    ap.add_argument("--allow-repeat-as-of", action="store_true", help="Allow executing the same as_of twice.")
    ap.add_argument("--treat-cash-symbol-as-cash", action="store_true", help="Do not trade cash proxy (default).")
    ap.add_argument("--cash-symbol", type=str, default="BIL")
    ap.add_argument("--allowed-symbols", nargs="*", default=[], help="Optional allowlist; if set, reject others.")
    ap.add_argument("--allow-shorts", action="store_true", help="Allow negative weights (shorts).")
    ap.add_argument("--max-gross-exposure", type=float, default=0.0, help="If >0, reject targets with gross exposure above this.")
    ap.add_argument("--max-short-exposure", type=float, default=0.0, help="If >0, reject targets with short exposure above this.")
    ap.add_argument("--max-turnover", type=float, default=0.60)
    ap.add_argument("--min-order-notional", type=float, default=50.0)
    ap.add_argument("--max-order-notional", type=float, default=50_000.0)
    ap.add_argument("--max-orders", type=int, default=20)
    ap.add_argument("--order-type", choices=["limit", "market"], default="limit")
    ap.add_argument("--limit-buffer-bps", type=float, default=15.0)
    ap.add_argument("--time-in-force", type=str, default="day")
    ap.add_argument("--stale-signal-days", type=int, default=3)
    ap.add_argument("--reference-date", type=str, default=None, help="Optional YYYY-MM-DD or ISO timestamp for historical replay safety checks.")

    args = ap.parse_args()
    args.signal_json = _repo_path(args.signal_json)
    args.out_dir = _repo_path(args.out_dir)
    args.live_state = _repo_path(args.live_state)
    if args.file_state is not None:
        args.file_state = _repo_path(args.file_state)
    if args.file_panel is not None:
        args.file_panel = _repo_path(args.file_panel)
    if args.platform_safety_config is not None:
        args.platform_safety_config = _repo_path(args.platform_safety_config)

    signal = load_signal(args.signal_json)
    if args.skip_platform_safety and args.execute:
        raise SystemExit("Refusing --execute with --skip-platform-safety.")
    platform_safety = None
    if not args.skip_platform_safety:
        platform_safety = _check_platform_safety(signal, args.platform_safety_config)

    broker = _broker_from_args(args)

    safety = SafetyConfig(
        allowed_symbols=list(args.allowed_symbols) if args.allowed_symbols else None,
        treat_cash_symbol_as_cash=bool(args.treat_cash_symbol_as_cash) or True,
        cash_symbol=str(args.cash_symbol),
        allow_shorts=bool(args.allow_shorts),
        max_gross_exposure=(float(args.max_gross_exposure) if float(args.max_gross_exposure) > 0 else None),
        max_short_exposure=(float(args.max_short_exposure) if float(args.max_short_exposure) > 0 else None),
        max_turnover=float(args.max_turnover),
        min_order_notional=float(args.min_order_notional),
        max_order_notional=float(args.max_order_notional),
        max_orders=int(args.max_orders),
        order_type=str(args.order_type),
        limit_buffer_bps=float(args.limit_buffer_bps),
        time_in_force=str(args.time_in_force),
        stale_signal_days=int(args.stale_signal_days),
        reference_date=(str(args.reference_date) if args.reference_date else None),
    )

    notes, orders = compute_rebalance_orders(
        broker=broker,
        signal=signal,
        safety=safety,
        live_state_path=args.live_state,
        execute=bool(args.execute),
        allow_repeat_as_of=bool(args.allow_repeat_as_of),
    )

    out = {
        "as_of": str(signal.get("as_of") or ""),
        "regime": str(signal.get("regime") or ""),
        "broker": broker.name,
        "execute": bool(args.execute),
        "platform_safety": platform_safety or {"skipped": True},
        "notes": notes,
        "orders": [order.__dict__ for order in orders],
    }
    _write_json(args.out_dir / "orders_proposed.json", out)

    if not args.execute:
        print(json.dumps({"dry_run": True, "n_orders": len(orders), "out": str(args.out_dir / 'orders_proposed.json')}, indent=2))
        return 0
    if not args.ack_live_risk:
        raise SystemExit("Refusing to execute without --ack-live-risk")

    results: List[dict] = []
    for o in orders:
        r = broker.submit_order(o)
        results.append(r.__dict__)

    _write_json(args.out_dir / "orders_submitted.json", {"submitted": results})
    record_execution(
        live_state_path=args.live_state,
        as_of=str(signal.get("as_of") or ""),
        broker_name=broker.name,
        orders=[order.__dict__ for order in orders],
        results=results,
    )
    print(json.dumps({"dry_run": False, "n_submitted": len(results), "out": str(args.out_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
