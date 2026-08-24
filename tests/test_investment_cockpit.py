from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.research.investment_cockpit import (
    THESIS_COLUMNS,
    compute_factor_tearsheet,
    construct_portfolio_from_scores,
    init_thesis_register,
    register_candidate_run,
    simulate_paper_rebalance,
    upsert_thesis,
)


def _panel(path: Path) -> Path:
    dates = pd.date_range("2026-01-01", periods=8, freq="B")
    rows = []
    prices = {
        "AAA": [100, 101, 102, 104, 106, 108, 110, 112],
        "BBB": [100, 100, 101, 101, 102, 102, 103, 103],
        "CCC": [100, 99, 98, 97, 96, 95, 94, 93],
        "DDD": [100, 100, 100, 99, 98, 97, 96, 95],
    }
    for ticker, vals in prices.items():
        for dt, price in zip(dates, vals):
            rows.append({"Instrument": ticker, "Date": dt, "Price_Close": price})
    panel_csv = path / "panel.csv"
    pd.DataFrame(rows).to_csv(panel_csv, index=False)
    return panel_csv


def test_factor_tearsheet_computes_positive_rank_ic(tmp_path: Path):
    panel_csv = _panel(tmp_path)
    rankings = pd.DataFrame(
        [
            {"date": "2026-01-01", "ticker": "AAA", "score": 4, "sector": "tech"},
            {"date": "2026-01-01", "ticker": "BBB", "score": 3, "sector": "health"},
            {"date": "2026-01-01", "ticker": "CCC", "score": 1, "sector": "finance"},
            {"date": "2026-01-01", "ticker": "DDD", "score": 2, "sector": "finance"},
            {"date": "2026-01-05", "ticker": "AAA", "score": 4, "sector": "tech"},
            {"date": "2026-01-05", "ticker": "BBB", "score": 3, "sector": "health"},
            {"date": "2026-01-05", "ticker": "CCC", "score": 1, "sector": "finance"},
            {"date": "2026-01-05", "ticker": "DDD", "score": 2, "sector": "finance"},
        ]
    )
    sheet = compute_factor_tearsheet(rankings, panel_csv, horizon_days=2, quantiles=2, top_n=2)

    assert sheet.ic_summary["mean_rank_ic"] > 0
    assert not sheet.bucket_returns.empty
    assert "sector" in set(sheet.top_exposures["field"])

    paths = sheet.write(tmp_path / "tear")
    assert Path(paths["summary"]).exists()


def test_construct_portfolio_enforces_caps_and_cash(tmp_path: Path):
    scores = pd.DataFrame(
        [
            {"date": "2026-01-31", "ticker": "AAA", "score": 10.0, "sector": "tech"},
            {"date": "2026-01-31", "ticker": "BBB", "score": 8.0, "sector": "tech"},
            {"date": "2026-01-31", "ticker": "CCC", "score": 6.0, "sector": "finance"},
            {"date": "2026-01-31", "ticker": "DDD", "score": 4.0, "sector": "health"},
        ]
    )
    result = construct_portfolio_from_scores(
        scores,
        top_n=4,
        max_weight=0.30,
        gross_target=0.90,
        group_caps={"sector": 0.45},
        cash_ticker="CASH",
    )
    weights = result.weights.set_index("instrument")["weight"]

    assert float(weights.drop(index="CASH").max()) <= 0.30 + 1e-12
    assert float(weights["CASH"]) >= 0.10 - 1e-12
    assert weights.sum() == pytest.approx(1.0)
    assert float(weights[["AAA", "BBB"]].sum()) <= 0.45 + 1e-12


def test_construct_portfolio_enforces_benchmark_active_caps():
    scores = pd.DataFrame(
        [
            {"date": "2026-01-31", "ticker": "AAA", "score": 100.0},
            {"date": "2026-01-31", "ticker": "BBB", "score": 10.0},
            {"date": "2026-01-31", "ticker": "CCC", "score": 1.0},
        ]
    )
    result = construct_portfolio_from_scores(
        scores,
        top_n=3,
        max_weight=0.80,
        gross_target=1.0,
        benchmark_weights={"AAA": 0.20, "BBB": 0.20, "CCC": 0.20},
        max_active_weight=0.10,
        cash_ticker="CASH",
    )
    weights = result.weights.set_index("instrument")["weight"]
    assert float(weights["AAA"]) <= 0.30 + 1e-12
    assert result.summary["benchmark_aware"] is True


def test_thesis_register_init_and_upsert(tmp_path: Path):
    path = tmp_path / "thesis.csv"
    init_thesis_register(path)
    df = pd.read_csv(path)
    assert list(df.columns) == THESIS_COLUMNS

    upsert_thesis(
        path,
        {
            "thesis_id": "AAA-ai-capex",
            "ticker": "AAA",
            "entity": "AAA Corp",
            "status": "radar",
            "thesis": "AI capex creates durable earnings revision support.",
            "invalidation_trigger": "Revenue revisions turn negative.",
        },
    )
    upsert_thesis(path, {"thesis_id": "AAA-ai-capex", "ticker": "AAA", "status": "paper_candidate"})
    df = pd.read_csv(path)
    assert len(df) == 1
    assert df.loc[0, "status"] == "paper_candidate"


def test_register_candidate_writes_manifest_and_registry(tmp_path: Path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"sharpe": 1.2, "cagr": 0.18, "max_drawdown": -0.09}))
    manifest = register_candidate_run(
        strategy="sp500_selector",
        status="paper_candidate",
        run_id="sp500-selector-test",
        out_dir=tmp_path / "candidates",
        artifacts={"summary": summary},
        params={"top_n": 10},
        notes="unit test",
    )

    data = json.loads(manifest.read_text())
    assert data["metrics"]["summary.sharpe"] == pytest.approx(1.2)
    registry = pd.read_csv(tmp_path / "candidates" / "registry.csv")
    assert registry.loc[0, "run_id"] == "sp500-selector-test"


def test_paper_rebalance_accounts_for_fees_and_positions():
    result = simulate_paper_rebalance(
        target_weights={"AAA": 0.6, "BBB": 0.3, "CASH": 0.1},
        prices={"AAA": 100.0, "BBB": 50.0},
        positions={},
        cash=10_000.0,
        as_of="2026-01-31",
        fee_bps=10,
    )

    assert len(result.orders) == 2
    assert result.ledger_row["n_orders"] == 2
    assert result.ledger_row["fees"] == pytest.approx(9.0)
    assert result.ledger_row["equity_after"] == pytest.approx(9_991.0)
    pos = result.positions.set_index("instrument")
    assert pos.loc["AAA", "shares"] == pytest.approx(60.0)
    assert pos.loc["BBB", "shares"] == pytest.approx(60.0)
