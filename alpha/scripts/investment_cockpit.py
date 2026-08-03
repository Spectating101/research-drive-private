#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
ROOT = _bmod.bootstrap_repo_paths(__file__)

from src.research.investment_cockpit import (
    compute_factor_tearsheet,
    construct_portfolio_from_scores,
    init_thesis_register,
    latest_prices_from_panel,
    load_positions,
    load_weights,
    register_candidate_run,
    simulate_paper_rebalance,
    upsert_thesis,
)


DEFAULT_OUT = Path("backtests/outputs/investment_cockpit")


def _parse_key_values(items: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"expected key=value, got {item!r}")
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _parse_float_map(items: list[str] | None) -> dict[str, float]:
    return {k: float(v) for k, v in _parse_key_values(items).items()}


def cmd_register_candidate(args: argparse.Namespace) -> int:
    artifacts = _parse_key_values(args.artifact)
    params = _parse_key_values(args.param)
    path = register_candidate_run(
        strategy=args.strategy,
        status=args.status,
        run_id=args.run_id,
        run_dir=args.run_dir,
        out_dir=args.out_dir,
        artifacts=artifacts,
        params=params,
        notes=args.notes or "",
    )
    print(path)
    return 0


def cmd_factor_tearsheet(args: argparse.Namespace) -> int:
    rankings = pd.read_csv(args.rankings)
    sheet = compute_factor_tearsheet(
        rankings,
        args.panel,
        date_col=args.date_col,
        instrument_col=args.instrument_col,
        score_col=args.score_col,
        horizon_days=args.horizon_days,
        quantiles=args.quantiles,
        top_n=args.top_n,
        exposure_cols=args.exposure_col,
    )
    paths = sheet.write(args.out_dir)
    print(json.dumps(paths, indent=2, sort_keys=True))
    return 0


def cmd_init_thesis(args: argparse.Namespace) -> int:
    path = init_thesis_register(args.path, overwrite=args.overwrite)
    print(path)
    return 0


def cmd_upsert_thesis(args: argparse.Namespace) -> int:
    row = _parse_key_values(args.field)
    path = upsert_thesis(args.path, row)
    print(path)
    return 0


def cmd_construct_portfolio(args: argparse.Namespace) -> int:
    scores = pd.read_csv(args.rankings)
    benchmark_weights = load_weights(args.benchmark_weights) if args.benchmark_weights else None
    result = construct_portfolio_from_scores(
        scores,
        instrument_col=args.instrument_col,
        score_col=args.score_col,
        date_col=args.date_col,
        as_of=args.as_of,
        top_n=args.top_n,
        max_weight=args.max_weight,
        gross_target=args.gross_target,
        min_score=args.min_score,
        group_caps=_parse_float_map(args.group_cap),
        benchmark_weights=benchmark_weights,
        max_active_weight=args.max_active_weight,
        cash_ticker=args.cash_ticker,
    )
    paths = result.write(args.out_dir, strategy=args.strategy, as_of=args.as_of)
    print(json.dumps(paths, indent=2, sort_keys=True))
    return 0


def cmd_paper_rebalance(args: argparse.Namespace) -> int:
    weights = load_weights(args.weights)
    as_of, prices = latest_prices_from_panel(args.panel, as_of=args.as_of)
    positions, cash_from_positions = load_positions(args.positions)
    cash = args.cash if args.cash is not None else cash_from_positions
    if cash is None:
        cash = 10_000.0
    result = simulate_paper_rebalance(
        target_weights=weights,
        prices=prices,
        positions=positions,
        cash=float(cash),
        as_of=as_of,
        fee_bps=args.fee_bps,
        min_trade_value=args.min_trade_value,
        cash_ticker=args.cash_ticker,
    )
    paths = result.write(args.out_dir)
    print(json.dumps(paths, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stock investment cockpit utilities.")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("register-candidate", help="write a candidate run manifest and registry row")
    c.add_argument("--strategy", required=True)
    c.add_argument("--status", default="research_only")
    c.add_argument("--run-id")
    c.add_argument("--run-dir", type=Path)
    c.add_argument("--out-dir", type=Path, default=DEFAULT_OUT / "candidates")
    c.add_argument("--artifact", action="append", help="name=path, repeatable")
    c.add_argument("--param", action="append", help="name=value, repeatable")
    c.add_argument("--notes", default="")
    c.set_defaults(func=cmd_register_candidate)

    c = sub.add_parser("factor-tearsheet", help="compute ranking IC, buckets, turnover, and exposures")
    c.add_argument("--rankings", type=Path, required=True)
    c.add_argument("--panel", type=Path, required=True)
    c.add_argument("--out-dir", type=Path, default=DEFAULT_OUT / "factor_tearsheet")
    c.add_argument("--date-col")
    c.add_argument("--instrument-col")
    c.add_argument("--score-col", default="score")
    c.add_argument("--horizon-days", type=int, default=21)
    c.add_argument("--quantiles", type=int, default=5)
    c.add_argument("--top-n", type=int, default=10)
    c.add_argument("--exposure-col", action="append", default=["sector", "country"])
    c.set_defaults(func=cmd_factor_tearsheet)

    c = sub.add_parser("init-thesis", help="create an empty thesis register CSV")
    c.add_argument("--path", type=Path, default=Path("config/thesis_register.csv"))
    c.add_argument("--overwrite", action="store_true")
    c.set_defaults(func=cmd_init_thesis)

    c = sub.add_parser("upsert-thesis", help="insert/update a thesis row")
    c.add_argument("--path", type=Path, default=Path("config/thesis_register.csv"))
    c.add_argument("--field", action="append", required=True, help="column=value, repeatable")
    c.set_defaults(func=cmd_upsert_thesis)

    c = sub.add_parser("construct-portfolio", help="turn stock scores into constrained weights")
    c.add_argument("--rankings", type=Path, required=True)
    c.add_argument("--out-dir", type=Path, default=DEFAULT_OUT / "portfolio")
    c.add_argument("--strategy", default="constructed_stock_portfolio")
    c.add_argument("--date-col")
    c.add_argument("--instrument-col")
    c.add_argument("--score-col", default="score")
    c.add_argument("--as-of")
    c.add_argument("--top-n", type=int, default=10)
    c.add_argument("--max-weight", type=float, default=0.15)
    c.add_argument("--gross-target", type=float, default=1.0)
    c.add_argument("--min-score", type=float)
    c.add_argument("--group-cap", action="append", help="column=max_weight, repeatable; e.g. sector=0.35")
    c.add_argument("--benchmark-weights", type=Path, help="benchmark weights CSV/JSON for active-weight caps")
    c.add_argument("--max-active-weight", type=float, help="max active weight above benchmark per name")
    c.add_argument("--cash-ticker", default="CASH")
    c.set_defaults(func=cmd_construct_portfolio)

    c = sub.add_parser("paper-rebalance", help="simulate orders/fills/positions from target weights")
    c.add_argument("--weights", type=Path, required=True, help="target_signal.json or target_weights.csv")
    c.add_argument("--panel", type=Path, required=True)
    c.add_argument("--positions", type=Path)
    c.add_argument("--cash", type=float)
    c.add_argument("--as-of")
    c.add_argument("--out-dir", type=Path, default=DEFAULT_OUT / "paper_order_ledger")
    c.add_argument("--fee-bps", type=float, default=0.0)
    c.add_argument("--min-trade-value", type=float, default=0.0)
    c.add_argument("--cash-ticker", default="CASH")
    c.set_defaults(func=cmd_paper_rebalance)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
