# Investment Research Engine Roadmap

This repo should be treated as an investment research cockpit, not an automatic stock-picking machine.

The valuable form is:

1. Broad default allocation.
2. Price/factor engine for ranking, confirmation, and sizing.
3. News-pattern engine for structural quality, deterioration, and improvement signals.
4. Paper-trading ledger for live evidence.
5. Promotion gates before any strategy graduates from research to capital.

## Core Thesis

The edge is unlikely to come from a generic AI stock picker. Momentum, trend, volatility targeting, and cross-sectional factor ranking are crowded and fragile.

The more plausible edge is the combination:

- price strength says what the market is rewarding now
- news-pattern structure says whether the underlying country/company story is improving, deteriorating, or fake
- risk controls prevent one thesis from dominating the capital base

In plain terms: the engine should help decide where to tilt and where to refuse temptation.

## Strategy Tiers

### Tier 0: Research Only

Use for idea generation and diagnostics.

Examples:

- raw top-10 composite screen
- country drilldown
- single-run backtests
- LLM or narrative-only calls

Capital rule: no direct allocation from this tier.

### Tier 1: Radar

Use for watchlists and context.

Requirements:

- reproducible output file
- clear universe
- no obvious lookahead
- readable ranking table

Examples:

- `backtests/outputs/global_drilldown/*`
- country/sector strength reports

Capital rule: can inform thesis research, not trade sizing.

### Tier 2: Candidate Strategy

Use for paper trading or small sleeve simulation.

Requirements:

- validation/holdout split
- benchmark comparison
- cost assumptions
- max drawdown reported
- turnover visible

Examples:

- multi-asset trend allocator
- crypto best-practice allocator
- SP500 cross-sectional selector when holdout is positive

Capital rule: paper trade first.

### Tier 3: Deployable Sleeve

Use only after a strategy survives live/paper evidence.

Requirements:

- multiple window robustness checks
- benchmark/risk-matched benchmark comparison
- cost and slippage assumptions
- paper-trading history
- explicit kill switch and max allocation
- no unresolved data freshness issue

Capital rule: small sleeve only, with broad portfolio core untouched.

## News-Pattern Layer

The news-pattern dataset should not be a simple sentiment feed. It should classify structural patterns:

- dysfunction: denial cycles, apology/clarification loops, corruption probes, policy reversals, institutional conflict
- stress: FX pressure, capital flight, bond stress, protests, sanctions, trade shocks
- improvement: reform delivery, credible policy coordination, investment inflow, infrastructure execution, export momentum, disinflation, rating improvement

The first empirical test is not whether the labels sound smart.

The test is:

Does the news-pattern layer improve forward return, drawdown, or risk-adjusted allocation after controlling for momentum, volatility, country beta, sector, and market trend?

If yes, it becomes an investment edge. If no, it remains a research dashboard.

## Operating Doctrine

- Broad exposure is the default when selection edge is weak.
- Top-ranked names are candidates, not commands.
- Concentrated positions need three-way agreement: price strength, structural thesis, and news-pattern quality.
- Negative news-pattern deterioration can veto a price-only signal.
- Paper/live scorecard beats backtest optimism.
- Any strategy that cannot beat a simple equal-weight or broad ETF benchmark should be used only as context.

## Promotion Gate

Before any module is trusted:

1. Reproducible artifact exists.
2. Holdout is not negative versus benchmark.
3. Window robustness is not dominated by one lucky period.
4. Risk-matched benchmark is included.
5. Costs and turnover are included.
6. Live/paper scorecard is not deteriorating.
7. Failure mode is written down before capital is allocated.

## Immediate Build Plan

1. Keep the current scraping/backfill jobs running.
2. Use `scripts/investment_research_engine_audit.py` as the regular health report.
3. Add a thesis-register CSV for discretionary tilts.
4. Add news-pattern features to the country/entity panel.
5. Run price-only versus price-plus-news incremental tests.
6. Build a small dashboard only after the evidence layer is stable.
