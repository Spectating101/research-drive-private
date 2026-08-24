# Investment Platform Blueprint

Snapshot date: 2026-06-27.

This is the build plan for turning Sharpe-Renaissance into a serious stock
investment research and operating platform. The product target is not an
autonomous stock picker. The target is an evidence machine that can discover,
test, monitor, explain, and govern stock/ETF allocation ideas with enough
discipline that weak ideas die quickly and strong ideas have a defined path to
capital consideration.

## North Star

The platform should answer five questions every day:

1. What do we currently believe?
2. What evidence supports or weakens that belief?
3. What changed in price, fundamentals, news, risk, and paper/live outcomes?
4. Which strategies are research-only, radar, candidate, or deployable?
5. What must happen before any idea can affect real allocation?

The operating model is:

```text
data -> features -> alpha ideas -> validation -> thesis -> portfolio construction
     -> target weights -> accounting -> scorecard -> capability audit -> promotion gate
```

## Non-Negotiable Rules

1. No strategy without a manifest.
2. No manifest without data/universe/feature/model/portfolio/benchmark metadata.
3. No ranking without a factor tear sheet.
4. No discretionary tilt without a thesis record and invalidation trigger.
5. No portfolio weights directly from an LLM.
6. No promotion without holdout, robustness, costs, benchmark, and forward evidence.
7. No live-adjacent workflow without target weights, orders, fills, positions, cash,
   fees, reconciliation, and a kill switch.
8. No hidden exceptions. Any bypass must be written into the manifest as a risk.

These rules are how we strong-arm the repo into discipline. The point is not
process theater. The point is to prevent attractive but unproven signals from
quietly becoming capital decisions.

## Current Capability Read

Latest generated capability audit:

- Report: `reports/investment_capabilities/latest.md`
- Current summary after the first enforcement build: strong `2`, partial `11`,
  weak `0`, high-priority gaps `0`
- Hard-gate report: `reports/investment_enforcement/latest.md`
- Manifest gate report: `reports/manifest_gates/latest.md`
- Accounting bundle: `reports/accounting_bundle/latest.md`
- Operator dashboard: `reports/investment_operator/latest.md`
- Repo pruning/inventory audit: `reports/repo_inventory/latest.md`
- Query-engine report datasets:
  - `investment_operator_dashboard`
  - `investment_enforcement_latest`
  - `investment_accounting_bundle_latest`
  - `investment_capability_audit_latest`
  - `investment_manifest_gates_latest`
  - `investment_repo_inventory_latest`
  - `investment_thesis_gates_latest`

Strong today:

- Promotion gates and status-tier doctrine.
- Costs, attribution, and failure diagnostics.

Partial today:

- Data connector surface.
- Universe management.
- Factor validation tear sheets.
- LLM equity research layer.
- Portfolio construction.
- Execution/accounting lifecycle.
- Monitoring/operator cockpit.
- Agent tool registry.
- Forward decision evaluation.

No tracked capability is now completely weak, but most capabilities remain
partial because the new enforcement artifacts still need to be wired through
all existing strategy modules.

Current hard-gate result:

- Accounting reconciliation passes for the current alpha paper ledger and
  scorecard.
- Thesis and manifest gates pass for the current blocked candidate manifest.
- The current alpha accounting bundle is `legacy_partial`: target signal, ledger,
  scorecard, safety config, and reconciliation exist; order/fill/position
  artifacts are still absent for that legacy alpha path.
- Enforcement has a user-systemd unit/timer pair:
  `systemd/investment-enforcement.service` and
  `systemd/investment-enforcement.timer`.
- Alpha ideas can now generate explicit validation job specs via
  `scripts/alpha_idea_queue.py generate-jobs`; no current queue row is
  validation-ready, so the generated job report currently has zero runnable jobs.
- Repo pruning now has a non-destructive inventory audit. Current safe first
  quarantine batch is root-level generated screenshots/HTML/reports; large
  generated and local data directories should be externalized or cleaned by
  policy, not deleted blindly.
- Frozen-decision evaluation remains negative versus benchmark, so the
  enforcement cycle correctly reports `warn` rather than treating the current
  alpha as deployable.

## Target Architecture

### 1. Data Surface

Goal: one internal stock-investment data facade.

Inputs:

- prices and returns
- stock/ETF universes
- fundamentals
- macro and rates
- news-pattern labels
- entity/country/sector metadata
- paper/live scorecards
- thesis register

Build:

- `src/research/stock_investment_data.py`
- schema validators for every panel
- data freshness report per dataset
- universe registry with `universe_id`, source, timestamp, and hash

Strong-arm rule:

- Strategy runners may not read random CSVs directly once a facade exists. New
  strategy code must call the facade or document why it cannot.

### 2. Experiment Registry

Goal: every run becomes inspectable and comparable.

Existing base:

- `src/research/investment_cockpit.py`
- `scripts/investment_cockpit.py register-candidate`
- `backtests/outputs/investment_cockpit/candidates/registry.csv`

Build:

- wrap major runners so they auto-write manifests:
  - equity best-practice runner
  - alpha live cycle
  - alpha walk-forward runner
  - country/stock radar jobs
  - IDN stock research jobs
- add fields:
  - `universe_id`
  - `universe_hash`
  - `feature_set_id`
  - `label_definition`
  - `benchmark_id`
  - `cost_model_id`
  - `validation_protocol`
  - `failure_mode`
  - `owner`

Strong-arm rule:

- A strategy without a manifest cannot appear as `paper_candidate` or
  `deployable_sleeve`.

### 3. Alpha Idea Queue

Goal: turn human/agent ideas into a controlled factory.

External lesson:

- RD-Agent and QuantaAlpha are useful because they treat idea generation as a
  repeatable R&D loop, not because every generated factor is good.

Build:

- `config/alpha_idea_queue.csv`
- required columns:
  - `idea_id`
  - `source`
  - `created_at`
  - `hypothesis`
  - `universe`
  - `feature_recipe`
  - `expected_mechanism`
  - `risk_of_leakage`
  - `status`
  - `validation_artifact`
  - `owner`
- statuses:
  - `idea`
  - `feature_ready`
  - `backtest_ready`
  - `validated`
  - `rejected`
  - `paper_candidate`

Build scripts:

- `scripts/alpha_idea_queue.py init`
- `scripts/alpha_idea_queue.py add`
- `scripts/alpha_idea_queue.py promote`
- `scripts/alpha_idea_queue.py report`

Strong-arm rule:

- Agent-generated ideas can enter the queue, but cannot skip to strategy status.
  They must generate artifacts.

### 4. Factor Validation Tear Sheets

Goal: judge rankings before judging portfolios.

Existing base:

- `compute_factor_tearsheet(...)`

Build:

- make stock selector runners emit:
  - `factor_tearsheet/summary.json`
  - `factor_tearsheet/ic_by_date.csv`
  - `factor_tearsheet/bucket_returns.csv`
  - `factor_tearsheet/turnover.csv`
  - `factor_tearsheet/top_exposures.csv`
- add checks:
  - rank IC mean
  - IC t-stat
  - top-minus-bottom bucket spread
  - turnover
  - sector/country concentration
  - liquidity/capacity where data exists

Strong-arm rule:

- A stock ranking cannot graduate beyond `radar` without a tear sheet.

### 5. Thesis Register And Research Agents

Goal: make LLM/human research useful without letting it size capital.

Existing base:

- `config/thesis_register.csv`
- `scripts/investment_cockpit.py upsert-thesis`

Build:

- thesis report generator:
  - active theses
  - stale theses
  - invalidation triggers near breach
  - contradiction checks
  - linked strategy IDs
- agent roles:
  - bull analyst
  - bear analyst
  - valuation/fundamental analyst
  - technical/factor analyst
  - risk officer
  - final editor
- controlled agent tools:
  - get candidate registry
  - get latest scorecard
  - get factor tear sheet
  - get thesis register
  - get capability audit
  - get universe metadata

Strong-arm rule:

- Agents write research records, vetoes, and contradiction checks. They do not
  write executable weights.

### 6. Portfolio Construction

Goal: separate signal quality from position sizing.

Existing base:

- `construct_portfolio_from_scores(...)`
- `src/research/portfolio_estimator.py`

Build:

- benchmark-aware sizing:
  - active weight limits
  - tracking-risk estimate
  - sector/country caps
  - single-name caps
  - turnover penalty
  - cash/T-bill sleeve
- optional optimizer:
  - start simple
  - only add cvx/skfolio-style optimization when constraints justify it
- output:
  - `target_weights.csv`
  - `target_signal.json`
  - `portfolio_constraints.json`
  - `portfolio_summary.json`

Strong-arm rule:

- Rankings are not portfolios. Every investable output must pass through the
  portfolio constructor.

### 7. Accounting And Execution Lifecycle

Goal: build Lean/Lumibot-style accounting discipline before any real execution.

Artifacts:

- signal
- target weights
- rebalance intent
- orders
- fills
- positions
- cash
- fees
- reconciliation
- scorecard
- kill switch

Build:

- one canonical schema under `backtests/outputs/investment_cockpit/accounting/`
- reconcile:
  - target exposure vs actual exposure
  - expected cash vs actual cash
  - fees and slippage
  - missing prices
  - stale positions
- add `config/execution_safety.json`:
  - max gross exposure
  - max single-name weight
  - max turnover per rebalance
  - max daily loss
  - max drawdown
  - allowed universes
  - blocked tickers
  - kill switch

Strong-arm rule:

- No broker-facing code should run unless safety config exists and passes checks.

### 8. Forward Decision Evaluation

Goal: evaluate frozen decisions after time passes.

Build:

- `backtests/outputs/investment_cockpit/frozen_decisions.csv`
- columns:
  - `decision_id`
  - `strategy`
  - `as_of`
  - `horizon_days`
  - `signal_path`
  - `weights_path`
  - `thesis_id`
  - `benchmark`
  - `status_at_decision`
  - `evaluation_due`
  - `evaluated_at`
  - `forward_return`
  - `benchmark_return`
  - `active_return`
  - `max_drawdown`
  - `thesis_invalidated`

Build scripts:

- `scripts/frozen_decision_tracker.py freeze`
- `scripts/frozen_decision_tracker.py evaluate`
- `scripts/frozen_decision_tracker.py report`

Strong-arm rule:

- A strategy with good backtests but bad frozen-decision outcomes stays blocked.

### 9. Capability Audit And Operator Cockpit

Goal: one command tells us what exists, what is weak, and what to build.

Existing base:

- `config/investment_capability_map.json`
- `scripts/investment_capability_audit.py`
- `reports/investment_capabilities/latest.md`
- `scripts/platform_status.py`
- `bash scripts/run_research_spine.sh capabilities`

Build:

- add capability deltas:
  - new strengths
  - worsening gaps
  - stale artifacts
  - missing expected outputs
- add top action queue:
  - top 5 next engineering actions
  - owner
  - due status
- integrate into any future UI/dashboard.

Strong-arm rule:

- Weekly platform work starts from the capability audit, not from whatever
  experiment looks exciting that day.

## Build Phases

### Phase 0: Freeze The Operating Doctrine

Duration: immediate.

Deliverables:

- capability map exists
- blueprint exists
- status command surfaces capability gaps
- all new work must declare which capability it improves

Exit criteria:

- `bash scripts/run_research_spine.sh capabilities` works
- platform status shows capability summary
- blueprint is linked from tracker docs

Current status: mostly done.

### Phase 1: Make Every Existing Strategy Accountable

Objective: stop disconnected artifacts.

Work:

1. Wrap major strategy runners with candidate manifest writing.
2. Add `universe_id`, `benchmark_id`, `cost_model_id`, and `validation_protocol`.
3. Generate candidate registry for current major stock/ETF strategies.
4. Attach current scorecard and promotion status.

Priority runners:

- `scripts/best_practice_equity_runner.py`
- `scripts/alpha_insights_walkforward_runner.py`
- `scripts/alpha_live_cycle.py`
- `scripts/country_drilldown.py`
- IDN stock research runners that produce candidate portfolios.

Exit criteria:

- candidate registry contains all current stock/ETF strategies
- every candidate has a status
- missing artifacts are visible

### Phase 2: Force Stock Rankings Through Tear Sheets

Objective: make factor quality visible.

Work:

1. Standardize ranking CSV schema.
2. Emit factor tear sheets from stock selector jobs.
3. Add tear sheet summary to candidate manifest.
4. Add promotion checks:
   - IC not negative
   - turnover acceptable
   - top bucket beats bottom bucket
   - concentration controlled

Exit criteria:

- stock selector outputs include tear sheets
- promotion report refuses candidates without tear sheets

### Phase 3: Build Thesis And Agent Research Layer

Objective: use LLMs as analysts and risk officers.

Work:

1. Expand `thesis_register.csv`.
2. Add thesis report generator.
3. Add agent tool wrappers around scorecard, registry, tear sheets, and capability audit.
4. Connect thesis IDs to candidate manifests and frozen decisions.
5. Add stale-thesis and invalidation-trigger checks.

Exit criteria:

- every discretionary tilt has `thesis_id`
- agent output is stored as research evidence
- invalidation triggers are visible in operator reports

### Phase 4: Upgrade Portfolio Construction

Objective: make sizing a first-class discipline.

Work:

1. Add benchmark-aware constraints.
2. Add sector/country caps.
3. Add turnover penalty.
4. Add cash/T-bill sleeve logic.
5. Add portfolio risk estimate into target output.
6. Save all constraints with every target-weight artifact.

Exit criteria:

- every target-weight file has a constraint summary
- no rank-only strategy can call itself investable

### Phase 5: Unify Accounting

Objective: make execution state auditable even before broker integration.

Work:

1. Define canonical accounting schema.
2. Unify target weights, orders, fills, positions, cash, and scorecards.
3. Add reconciliation checks.
4. Add safety config and kill-switch checks.
5. Add operator report for accounting state.

Exit criteria:

- platform can explain current target, simulated orders, positions, cash, fees,
  and scorecard in one report
- safety config gates any live-adjacent flow

### Phase 6: Frozen Decision Evaluation

Objective: kill retrospective storytelling.

Work:

1. Freeze every candidate decision when made.
2. Evaluate after horizon expiry.
3. Compare to benchmark.
4. Track thesis invalidation.
5. Feed results into promotion/demotion.

Exit criteria:

- every candidate decision has an evaluation due date
- scorecard includes frozen-decision results
- bad forward evidence blocks promotion even when backtest is good

### Phase 7: Operator Dashboard

Objective: make the platform legible.

Work:

1. One page for platform health.
2. One page for capability gaps.
3. One page for strategy registry.
4. One page for active theses.
5. One page for current target/book/accounting.
6. One page for promotion gate decisions.

Exit criteria:

- status, evidence, and next action are visible without reading raw files
- dashboard reflects artifacts, not manual copy

## First 10 Engineering Tickets

1. Done: add candidate manifest writing to `best_practice_equity_runner.py`.
2. Done: add candidate manifest writing to `alpha_live_cycle.py`.
3. Done: create `config/alpha_idea_queue.csv` and `scripts/alpha_idea_queue.py`.
4. Remaining: wire factor tear sheet output directly into equity selector runs.
5. Done: add `universe_id` and `universe_hash` generation.
6. Done: add thesis report generator from `config/thesis_register.csv`.
7. Done: add benchmark-aware caps to portfolio construction.
8. Done: create `config/execution_safety.json`.
9. Done: create `scripts/frozen_decision_tracker.py`.
10. Done: add top next-action queue to capability audit.

Next 10 tickets:

1. Make factor tear sheets mandatory inside stock selector runners.
2. Done: auto-freeze candidate decisions from candidate manifests.
3. Done: auto-evaluate frozen decisions manually from the tracker; remaining
   work is scheduling it after platform cycles.
4. Partial: thesis gate report exists; remaining work is connecting it to
   promotion-gate reports.
5. Done: add accounting reconciliation report over target weights, orders, fills,
   positions, cash, fees, and scorecards.
6. Remaining: make `execution_safety` checks mandatory for any live-adjacent command.
7. Migrate stock strategy modules to `stock_investment_data`.
8. Backfill existing stock strategy manifests with universe hashes.
9. Done: add controlled agent read tools for registry, capabilities, thesis,
   decisions, accounting, ideas, data status, and tear sheets.
10. Surface capability and thesis reports in the UI/operator dashboard.

## Promotion Gate Contract

Every candidate must include:

- manifest path
- universe hash
- feature set
- model/config
- benchmark
- cost model
- validation split
- robustness evidence
- factor tear sheet if ranking-based
- thesis ID if discretionary/narrative component exists
- target-weight constraints
- scorecard
- known failure mode

Promotion decisions:

```text
research_only -> radar:
  reproducible output, clear universe, no obvious lookahead

radar -> paper_candidate:
  holdout nonnegative vs benchmark, costs modeled, tear sheet acceptable

paper_candidate -> deployable_sleeve:
  paper/live evidence acceptable, drawdown controlled, robustness passed,
  safety config present, max allocation defined, kill switch present

any status -> blocked:
  stale data, negative forward evidence, broken fingerprint, invalidated thesis,
  unmodeled costs, or unexplained accounting mismatch
```

## What We Steal From External Projects

| External project | What to steal | What not to steal |
| --- | --- | --- |
| Qlib | lifecycle vocabulary, experiment structure, dataset/model/portfolio separation | wholesale migration |
| RD-Agent | automated idea/factor queue | trusting generated alpha without validation |
| OpenBB | connector-first data surfaces | turning the platform into a generic terminal |
| FinRobot | equity research report structure | LLM-generated weights |
| TradingAgents / ai-hedge-fund | analyst debate roles and risk-team framing | treating roleplay as evidence |
| Vibe-Trading | controlled tool registry for agents | agent autonomy over execution |
| Lean | accounting separation and live discipline | adopting a heavy engine too early |
| Lumibot | broker/paper/live abstraction ideas | GPL-bound code reuse without review |
| PyPortfolioOpt / cvxportfolio / skfolio | constrained portfolio construction | optimizer worship before signal quality |
| Alphalens / mlfinlab | factor diagnostics and leakage defense | assuming library output means truth |

## Weekly Operating Rhythm

1. Run:

   ```bash
   bash scripts/run_research_spine.sh status
   bash scripts/run_research_spine.sh capabilities
   ```

2. Review:

   - edge readiness
   - paper/live scorecard
   - capability high-priority gaps
   - candidate registry
   - stale theses
   - frozen decisions due for evaluation

3. Pick work only from:

   - high-priority capability gaps
   - blocked strategy root causes
   - stale/invalid thesis issues
   - failing data/accounting checks

4. Do not chase new alpha until the current evidence system is healthy.

## Definition Of Done

The platform is strong when:

- every strategy is registered
- every stock ranking has a tear sheet
- every thesis has invalidation triggers
- every target portfolio has constraints
- every accounting state reconciles
- every candidate decision is frozen and later evaluated
- promotion gates are artifact-backed
- status command shows no high-priority capability gaps

Until then, the repo remains a research cockpit with improving operating
discipline, not a capital allocator.
