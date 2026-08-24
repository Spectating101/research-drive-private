# Investment Capability Tracker

This tracker answers a different question from the scorecard:

> What can the platform do today, what did we learn from external stock-investment
> projects, and what capability gaps should drive the next build cycle?

It is generated from:

- `config/investment_capability_map.json`
- local artifact checks across `src/`, `scripts/`, `config/`, `backtests/outputs/`,
  and `reports/`

The build blueprint is in
[`docs/INVESTMENT_PLATFORM_BLUEPRINT.md`](INVESTMENT_PLATFORM_BLUEPRINT.md).

## Run

```bash
bash scripts/run_research_spine.sh capabilities
```

or directly:

```bash
python scripts/investment_capability_audit.py
```

Outputs:

- `reports/investment_capabilities/latest.json`
- `reports/investment_capabilities/latest.md`

## What It Tracks

| Capability | External pattern source | Local question |
| --- | --- | --- |
| Research lifecycle registry | Qlib, RD-Agent | Do runs have manifests, hashes, metrics, status, and artifact links? |
| Data connector surface | OpenBB, Qlib | Do investment modules use stable data surfaces instead of scattered CSV reads? |
| Universe management | Qlib, OpenBB | Are stock universes versioned, sourced, and tied to runs? |
| Factor validation tear sheets | Alphalens, mlfinlab, Qlib | Do rankings have IC, bucket, turnover, exposure, and cost diagnostics? |
| Automated alpha idea queue | RD-Agent, QuantaAlpha, Qbot | Is there a controlled idea -> factor -> validation workflow? |
| LLM equity research layer | FinRobot, TradingAgents, Vibe-Trading | Are agent theses recorded with evidence, contradiction checks, and invalidation triggers? |
| Portfolio construction layer | PyPortfolioOpt, cvxportfolio, skfolio | Is ranking separated from constrained sizing? |
| Execution accounting discipline | Lean, Lumibot, Nautilus | Are signals, orders, fills, positions, cash, fees, and kill switches separate? |
| Promotion gates | Qlib, Lean | Are strategy tiers objective and artifact-backed? |
| Monitoring/operator cockpit | OpenBB, nofx-style tools | Can one command show health, evidence, gaps, and next actions? |
| Agent tool registry | Vibe-Trading, OpenBB, FinRobot | Do agents use controlled tools and typed outputs? |
| Forward evaluation harness | LiveTradeBench, InvestorBench, StockBench | Are frozen decisions evaluated later, not narrated retrospectively? |
| Costs/attribution/failure analysis | Alphalens, mlfinlab, Lean | Can every strategy explain returns, costs, turnover, and failure modes? |

## Interpretation

The tracker uses two signals:

1. **Artifact coverage:** whether expected local files/globs exist.
2. **Current read:** the human maturity label in the capability map.

That second signal matters. A capability can have many files and still be
`partial` if the files are not integrated into one operating workflow.

Use high-priority gaps as the next engineering queue.
