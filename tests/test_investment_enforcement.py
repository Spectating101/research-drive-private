from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.research.alpha_idea_queue import idea_queue_report, init_idea_queue, promote_idea, upsert_idea
from src.research.alpha_idea_jobs import generate_idea_validation_jobs
from src.research.accounting_bundle import build_accounting_bundle
from src.research.accounting_reconciliation import reconcile_accounting
from src.research.execution_safety import validate_target_weights
from src.research.frozen_decisions import (
    decision_report,
    evaluate_decisions,
    freeze_decision,
    freeze_from_candidate_registry,
    init_decision_log,
)
from src.research.investment_enforcement import run_investment_enforcement_cycle
from src.research.manifest_gates import manifest_gate_report
from src.research.operator_dashboard import build_operator_dashboard
from src.research.stock_investment_data import (
    data_surface_snapshot,
    make_universe_record,
    panel_freshness,
    universe_from_panel,
    universe_hash,
    upsert_universe_registry,
)
from src.research.thesis_report import build_thesis_report
from src.research.thesis_gates import thesis_gate_report


def _panel(path: Path) -> Path:
    dates = pd.date_range("2026-01-01", periods=6, freq="D")
    rows = []
    prices = {
        "AAA": [100, 101, 102, 103, 104, 105],
        "BBB": [50, 49, 50, 51, 51, 52],
        "SPY": [100, 100, 101, 101, 102, 102],
    }
    for ticker, vals in prices.items():
        for dt, price in zip(dates, vals):
            rows.append({"Instrument": ticker, "Date": dt, "Price_Close": price})
    p = path / "panel.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def test_stock_data_facade_freshness_and_universe(tmp_path: Path):
    panel = _panel(tmp_path)
    fresh = panel_freshness(panel, as_of="2026-01-06", max_staleness_days=1)
    assert fresh.exists is True
    assert fresh.latest_date == "2026-01-06"
    assert fresh.stale is False

    tickers = universe_from_panel(panel)
    assert tickers == ["AAA", "BBB", "SPY"]
    assert universe_hash(["bbb", "AAA"]) == universe_hash(["AAA", "BBB"])

    rec = make_universe_record(universe_id="test", tickers=tickers, source=str(panel), as_of="2026-01-06")
    registry = upsert_universe_registry(tmp_path / "universes.json", rec)
    assert json.loads(registry.read_text())["universes"][0]["universe_hash"] == rec["universe_hash"]


def test_alpha_idea_queue_lifecycle(tmp_path: Path):
    path = tmp_path / "ideas.csv"
    init_idea_queue(path)
    upsert_idea(
        path,
        {
            "idea_id": "quality-revisions",
            "source": "unit",
            "hypothesis": "positive revisions plus quality improves returns",
            "status": "idea",
        },
    )
    promote_idea(path, "quality-revisions", "validated", validation_artifact="tear/summary.json")
    report = idea_queue_report(path)
    assert report["n_ideas"] == 1
    assert report["status_counts"]["validated"] == 1
    assert report["ideas_missing_validation_artifact"] == []


def test_alpha_idea_job_generator_creates_runnable_tearsheet_job(tmp_path: Path):
    queue = tmp_path / "ideas.csv"
    rankings = tmp_path / "rankings.csv"
    pd.DataFrame(
        [
            {"date": "2026-01-01", "instrument": "AAA", "score": 1.0},
            {"date": "2026-01-01", "instrument": "BBB", "score": 0.5},
        ]
    ).to_csv(rankings, index=False)
    init_idea_queue(queue)
    upsert_idea(
        queue,
        {
            "idea_id": "quality-momentum",
            "source": "unit",
            "hypothesis": "quality plus momentum ranks forward returns",
            "status": "feature_ready",
            "validation_artifact": str(rankings),
        },
    )
    report = generate_idea_validation_jobs(
        queue_csv=queue,
        repo=tmp_path,
        panel_csv=tmp_path / "panel.csv",
        out_root=tmp_path / "jobs",
    )
    assert report["n_jobs"] == 1
    assert report["n_runnable"] == 1
    assert report["jobs"][0]["command"][2] == "factor-tearsheet"
    assert (tmp_path / "jobs" / "quality-momentum" / "job.json").exists()


def test_execution_safety_blocks_kill_switch_and_caps():
    result = validate_target_weights(
        {"AAA": 0.20, "BBB": 0.10},
        {
            "kill_switch": True,
            "max_gross_exposure": 1.0,
            "max_single_name_weight": 0.15,
            "max_turnover_per_rebalance": 0.30,
            "max_drawdown": -0.10,
            "blocked_tickers": ["BBB"],
        },
        turnover_pct=0.40,
        drawdown=-0.11,
    )
    assert result.passed is False
    assert any("kill_switch" in r for r in result.reasons)
    assert any("single_name" in r for r in result.reasons)
    assert any("blocked_tickers" in r for r in result.reasons)


def test_frozen_decision_freeze_evaluate_and_report(tmp_path: Path):
    panel = _panel(tmp_path)
    weights = tmp_path / "weights.json"
    weights.write_text(json.dumps({"weights": {"AAA": 0.7, "BBB": 0.3}}))
    log = tmp_path / "frozen.csv"
    init_decision_log(log)
    freeze_decision(
        log,
        decision_id="d1",
        strategy="unit",
        as_of="2026-01-01",
        horizon_days=4,
        weights_path=str(weights),
        benchmark="SPY",
    )
    evaluate_decisions(log, panel_csv=panel, as_of="2026-01-06")
    df = pd.read_csv(log)
    assert df.loc[0, "evaluated_at"]
    assert float(df.loc[0, "forward_return"]) != 0
    report = decision_report(log)
    assert report["n_evaluated"] == 1


def test_freeze_from_candidate_registry(tmp_path: Path):
    panel = _panel(tmp_path)
    weights = tmp_path / "weights.json"
    weights.write_text(json.dumps({"strategy": "unit", "as_of": "2026-01-01", "weights": {"AAA": 1.0}}))
    manifest_dir = tmp_path / "candidate"
    manifest_dir.mkdir()
    manifest = {
        "run_id": "run1",
        "strategy": "unit",
        "status": "paper_candidate",
        "params": {"benchmark_id": "SPY"},
        "artifacts": {"signal": {"path": str(weights), "exists": True}},
    }
    manifest_path = manifest_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    registry = tmp_path / "registry.csv"
    pd.DataFrame(
        [{"run_id": "run1", "strategy": "unit", "status": "paper_candidate", "manifest_path": str(manifest_path)}]
    ).to_csv(registry, index=False)
    log = tmp_path / "frozen.csv"
    freeze_from_candidate_registry(log, registry_csv=registry, horizon_days=3)
    evaluate_decisions(log, panel_csv=panel, as_of="2026-01-06")
    report = decision_report(log)
    assert report["n_decisions"] == 1
    assert report["n_evaluated"] == 1


def test_accounting_reconciliation_matches_scorecard_and_ledger(tmp_path: Path):
    ledger = tmp_path / "ledger.csv"
    pd.DataFrame([{"date": "2026-01-01", "equity": 123.45}]).to_csv(ledger, index=False)
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps({"performance": {"latest_equity": 123.45}}))
    report = reconcile_accounting(equity_ledger_path=ledger, scorecard_path=scorecard)
    assert report["passed"] is True
    assert report["checks"]["scorecard_matches_ledger"] is True


def test_accounting_bundle_marks_complete_when_all_artifacts_exist(tmp_path: Path):
    target = tmp_path / "target_signal.json"
    target.write_text(json.dumps({"weights": {"AAA": 0.5, "CASH": 0.5}}))
    orders = tmp_path / "orders.csv"
    pd.DataFrame([{"instrument": "AAA", "fee": 1.0}]).to_csv(orders, index=False)
    fills = tmp_path / "fills.csv"
    pd.DataFrame([{"instrument": "AAA", "fee": 1.0, "fill_status": "filled"}]).to_csv(fills, index=False)
    positions = tmp_path / "positions.csv"
    pd.DataFrame([{"instrument": "AAA", "market_value": 50.0, "weight": 0.5}]).to_csv(positions, index=False)
    ledger = tmp_path / "ledger.csv"
    pd.DataFrame([{"date": "2026-01-01", "equity": 100.0, "cash_after": 50.0}]).to_csv(ledger, index=False)
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps({"performance": {"latest_equity": 100.0}}))
    safety = tmp_path / "safety.json"
    safety.write_text(json.dumps({"kill_switch": True}))

    bundle = build_accounting_bundle(
        repo=tmp_path,
        strategy="unit",
        run_id="run1",
        target_signal_path=target,
        orders_path=orders,
        fills_path=fills,
        positions_path=positions,
        equity_ledger_path=ledger,
        scorecard_path=scorecard,
        safety_config_path=safety,
    )
    assert bundle["status"] == "complete"
    assert bundle["complete"] is True
    assert bundle["checks"]["reconciliation_passed"] is True


def test_thesis_gate_requires_thesis_for_candidate_when_flagged(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "run_id": "r1",
                "strategy": "s",
                "status": "paper_candidate",
                "params": {"requires_thesis": True},
            }
        )
    )
    registry = tmp_path / "registry.csv"
    pd.DataFrame([{"run_id": "r1", "manifest_path": str(manifest)}]).to_csv(registry, index=False)
    thesis = tmp_path / "thesis.csv"
    pd.DataFrame(columns=["thesis_id", "invalidation_trigger", "contradiction_checks"]).to_csv(thesis, index=False)
    report = thesis_gate_report(registry, thesis)
    assert report["passed"] is False
    assert report["results"][0]["reasons"] == ["missing_thesis_id"]


def test_manifest_gate_enforces_candidate_provenance(tmp_path: Path):
    signal = tmp_path / "signal.json"
    signal.write_text(json.dumps({"as_of": "2026-01-01", "weights": {"AAA": 1.0}}))
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps({"performance": {"latest_equity": 100.0}}))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "run_id": "r1",
                "strategy": "unit",
                "status": "paper_candidate",
                "created_at": "2026-01-01T00:00:00+00:00",
                "params": {"benchmark_id": "SPY", "validation_protocol": "walk_forward"},
                "artifacts": {
                    "signal": {"path": str(signal), "exists": True},
                    "scorecard": {"path": str(scorecard), "exists": True},
                },
                "metrics": {"sharpe": 1.0},
            }
        )
    )
    registry = tmp_path / "registry.csv"
    pd.DataFrame([{"run_id": "r1", "manifest_path": str(manifest)}]).to_csv(registry, index=False)
    report = manifest_gate_report(registry, repo=tmp_path)
    assert report["passed"] is False
    assert "r1: missing_param:universe_id" in report["reasons"]


def test_investment_enforcement_cycle_writes_hard_gate_summary(tmp_path: Path):
    panel = _panel(tmp_path)
    weights = tmp_path / "weights.json"
    weights.write_text(json.dumps({"as_of": "2026-01-01", "weights": {"AAA": 0.7, "BBB": 0.3}}))
    ledger = tmp_path / "ledger.csv"
    pd.DataFrame([{"date": "2026-01-06", "equity": 123.45}]).to_csv(ledger, index=False)
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps({"performance": {"latest_equity": 123.45}}))
    thesis = tmp_path / "thesis.csv"
    pd.DataFrame(columns=["thesis_id", "status", "updated_at", "invalidation_trigger", "contradiction_checks"]).to_csv(
        thesis, index=False
    )
    cap_map = tmp_path / "capabilities.json"
    cap_map.write_text(
        json.dumps(
            {
                "scope": "unit",
                "principle": "unit",
                "capabilities": [
                    {
                        "id": "unit_gate",
                        "area": "Governance",
                        "local_artifacts": ["weights.json"],
                        "current_read": "Partial",
                        "next_actions": ["keep wiring gates"],
                    }
                ],
            }
        )
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "run_id": "r1",
                "strategy": "unit",
                "status": "blocked",
                "created_at": "2026-01-01T00:00:00+00:00",
                "notes": "blocked in unit test",
                "params": {"benchmark_id": "SPY"},
                "artifacts": {"signal": {"path": str(weights), "exists": True}},
            }
        )
    )
    registry = tmp_path / "registry.csv"
    pd.DataFrame([{"run_id": "r1", "strategy": "unit", "status": "blocked", "manifest_path": str(manifest)}]).to_csv(
        registry, index=False
    )

    report = run_investment_enforcement_cycle(
        repo=tmp_path,
        registry_csv=registry,
        decision_log=tmp_path / "decisions.csv",
        panel_csv=panel,
        thesis_register=thesis,
        capability_map=cap_map,
        equity_ledger=ledger,
        scorecard=scorecard,
        out_dir=tmp_path / "reports" / "investment_enforcement",
        horizon_days=3,
        as_of="2026-01-06",
    )
    assert report["passed"] is True
    assert report["hard_checks"]["manifest_gates"] is True
    assert (tmp_path / "reports" / "investment_enforcement" / "latest.json").exists()


def test_thesis_report_flags_missing_fields(tmp_path: Path):
    path = tmp_path / "thesis.csv"
    pd.DataFrame(
        [
            {
                "thesis_id": "t1",
                "ticker": "AAA",
                "status": "radar",
                "updated_at": "2020-01-01T00:00:00+00:00",
                "invalidation_trigger": "",
                "contradiction_checks": "",
            }
        ]
    ).to_csv(path, index=False)
    report = build_thesis_report(path, stale_days=1)
    assert report["n_theses"] == 1
    assert report["stale_thesis_ids"] == ["t1"]
    assert report["missing_invalidation_trigger"] == ["t1"]


def test_data_surface_snapshot_handles_missing_repo(tmp_path: Path):
    snap = data_surface_snapshot(tmp_path)
    assert snap["price_panel"]["exists"] is False


def test_operator_dashboard_passes_when_reports_are_clean(tmp_path: Path):
    (tmp_path / "backtests/outputs/signals").mkdir(parents=True)
    (tmp_path / "backtests/outputs/alpha_paper").mkdir(parents=True)
    (tmp_path / "reports/investment_enforcement").mkdir(parents=True)
    (tmp_path / "reports/manifest_gates").mkdir(parents=True)
    (tmp_path / "reports/accounting_bundle").mkdir(parents=True)
    (tmp_path / "reports/investment_capabilities").mkdir(parents=True)
    (tmp_path / "reports/thesis_gates").mkdir(parents=True)

    (tmp_path / "backtests/outputs/signals/alpha_live_signal.json").write_text(
        json.dumps({"strategy": "unit", "as_of_month": "2026-01-31"})
    )
    (tmp_path / "backtests/outputs/alpha_paper/scorecard_latest.json").write_text(
        json.dumps({"performance": {"latest_equity": 101.0, "sharpe_daily_252": 1.2}})
    )
    (tmp_path / "backtests/outputs/alpha_paper/edge_readiness_latest.json").write_text(
        json.dumps({"status": "ready", "checks": {}})
    )
    (tmp_path / "reports/investment_enforcement/latest.json").write_text(json.dumps({"status": "pass", "passed": True}))
    (tmp_path / "reports/manifest_gates/latest.json").write_text(json.dumps({"passed": True, "n_failing": 0}))
    (tmp_path / "reports/accounting_bundle/latest.json").write_text(json.dumps({"status": "complete", "complete": True}))
    (tmp_path / "reports/thesis_gates/latest.json").write_text(json.dumps({"passed": True}))
    (tmp_path / "reports/investment_capabilities/latest.json").write_text(
        json.dumps({"summary": {"priority_counts": {"high": 0}, "status_counts": {"strong": 1}, "top_actions": []}})
    )

    report = build_operator_dashboard(tmp_path)
    assert report["status"] == "pass"
    assert report["warnings"] == []
