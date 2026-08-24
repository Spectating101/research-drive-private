# Investment Cockpit Components

These components turn external stock-investment project patterns into local,
testable repo tools. They do not place broker orders.

For platform-level capability tracking, see
[`docs/INVESTMENT_CAPABILITY_TRACKER.md`](INVESTMENT_CAPABILITY_TRACKER.md).

## Components

| Component | What it does | Primary output |
| --- | --- | --- |
| Candidate registry | Records one strategy/config/run with artifact hashes, parameters, status, and extracted metrics. | `backtests/outputs/investment_cockpit/candidates/<run_id>/manifest.json` |
| Factor tear sheet | Scores a stock ranking by forward returns, rank IC, bucket returns, top-name turnover, and exposures. | `observations.csv`, `ic_by_date.csv`, `bucket_returns.csv`, `turnover.csv`, `summary.json` |
| Thesis register | Stores human/agent research theses, evidence links, contradiction checks, and invalidation triggers. | `config/thesis_register.csv` |
| Portfolio constructor | Converts stock scores into constrained long-only target weights with max-name and group caps. | `target_weights.csv`, `target_signal.json` |
| Paper order ledger | Simulates target-weight rebalance into orders, fills, latest positions, and an equity ledger. | `orders.csv`, `fills.csv`, `positions_latest.csv`, `equity_ledger.csv` |
| Alpha idea queue | Tracks idea -> feature -> backtest -> validation -> candidate lifecycle. | `config/alpha_idea_queue.csv` |
| Alpha idea validation jobs | Converts validation-ready idea rows into explicit factor-tearsheet job specs when a rankings CSV exists. | `backtests/outputs/investment_cockpit/idea_jobs/jobs.json` |
| Frozen decision tracker | Freezes candidate decisions and evaluates them after the horizon expires. | `backtests/outputs/investment_cockpit/frozen_decisions.csv` |
| Execution safety | Checks kill switch, gross exposure, single-name caps, turnover, drawdown, and blocked tickers. | `config/execution_safety.json` |
| Data/universe facade | Provides panel freshness, universe extraction, universe hashing, and data-surface snapshots. | `config/stock_universe_registry.json` |
| Accounting reconciliation | Checks ledger/scorecard consistency plus orders/fills/positions/cash where available. | `reports/accounting_reconciliation/latest.json` |
| Accounting bundle | Collects target signal/weights, orders, fills, positions, ledger, scorecard, safety config, and reconciliation into one canonical run bundle. | `reports/accounting_bundle/latest.json` |
| Thesis gates | Checks candidate manifests against thesis requirements when a thesis is required. | `reports/thesis_gates/latest.json` |
| Manifest gates | Verifies candidate manifests, artifact hashes, required metadata, strict candidate evidence, and deployable prerequisites. | `reports/manifest_gates/latest.json` |
| Enforcement cycle | Runs frozen-decision evaluation, accounting, thesis, manifest, and capability checks as one operator command. | `reports/investment_enforcement/latest.json` |
| Operator dashboard | Summarizes active alpha, edge readiness, gates, accounting bundle, and capability status in one report. | `reports/investment_operator/latest.json` |
| Repo inventory audit | Classifies active investment core, legacy investment scripts, generated artifacts, procurement side tracks, crypto side tracks, and quarantine candidates. | `reports/repo_inventory/latest.json` |
| Agent read tools | Provides controlled JSON reads for capabilities, registry, thesis, ideas, decisions, accounting, and data status. | `scripts/investment_agent_tools.py` |

## CLI

Register a candidate run:

```bash
python scripts/investment_cockpit.py register-candidate \
  --strategy sp500_selector \
  --status paper_candidate \
  --run-dir backtests/outputs/equity_best_practice_sp500_10y \
  --artifact summary=backtests/outputs/equity_best_practice_sp500_10y/summary.json
```

Build a factor tear sheet from a ranking CSV:

```bash
python scripts/investment_cockpit.py factor-tearsheet \
  --rankings path/to/rankings.csv \
  --panel data_lake/daily_alpha_panel.csv \
  --score-col score \
  --horizon-days 21 \
  --out-dir backtests/outputs/investment_cockpit/factor_tearsheet
```

Add or update a thesis:

```bash
python scripts/investment_cockpit.py upsert-thesis \
  --field thesis_id=nvda-ai-capex \
  --field ticker=NVDA \
  --field status=radar \
  --field 'thesis=AI capex revisions remain supportive' \
  --field 'invalidation_trigger=Revenue revisions turn negative'
```

Run idea queue report:

```bash
python scripts/alpha_idea_queue.py report
python scripts/alpha_idea_queue.py generate-jobs
```

Register a universe from the current alpha panel:

```bash
python scripts/stock_investment_data_status.py register-universe \
  --universe-id global_alpha_panel
```

Initialize and use frozen decision tracking:

```bash
python scripts/frozen_decision_tracker.py init
python scripts/frozen_decision_tracker.py report
```

Freeze/evaluate decisions from the candidate registry:

```bash
python scripts/frozen_decision_tracker.py freeze-from-registry
python scripts/frozen_decision_tracker.py evaluate
```

Run accounting and thesis gates:

```bash
python scripts/accounting_reconcile.py
python scripts/accounting_bundle.py
python scripts/thesis_gates.py
python scripts/manifest_gates.py
python scripts/investment_enforcement_cycle.py
python scripts/investment_operator_dashboard.py
python scripts/investment_repo_inventory.py
```

Use controlled agent read tools:

```bash
python scripts/investment_agent_tools.py capability-status
python scripts/investment_agent_tools.py operator-dashboard
python scripts/investment_agent_tools.py accounting-bundle
python scripts/investment_agent_tools.py candidate-registry
python scripts/investment_agent_tools.py accounting-report
```

Query the same investment reports through the local query engine:

```bash
python scripts/research_query_engine_cli.py search --q investment
python scripts/research_query_engine_cli.py query investment_operator_dashboard fields=status,warnings
python scripts/research_query_engine_cli.py query investment_accounting_bundle_latest fields=status,missing_artifacts
```

Refresh enforcement on a schedule:

```bash
bash scripts/install_platform_systemd_user.sh
systemctl --user list-timers | rg investment-enforcement
```

Construct weights from rankings:

```bash
python scripts/investment_cockpit.py construct-portfolio \
  --rankings path/to/rankings.csv \
  --score-col score \
  --top-n 10 \
  --max-weight 0.15 \
  --gross-target 0.95 \
  --group-cap sector=0.35
```

Simulate a paper rebalance:

```bash
python scripts/investment_cockpit.py paper-rebalance \
  --weights backtests/outputs/investment_cockpit/portfolio/target_signal.json \
  --panel data_lake/daily_alpha_panel.csv \
  --fee-bps 1
```

## Operating Rule

The LLM/research layer can write theses and contradiction checks. The portfolio
constructor and paper ledger own executable target weights and accounting. A
strategy remains `research_only`, `radar`, or `paper_candidate` until the paper/live
scorecard and promotion gates support escalation.
