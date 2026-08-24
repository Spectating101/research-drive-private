# OSS AI / Stock Investment Landscape

Snapshot date: 2026-06-27.

Scope: stock trading, ETF/global-asset allocation, equity research, portfolio
construction, and paper/live investment infrastructure. Prediction-market and
crypto-only bots are intentionally out of scope for this repo direction.

This is a practical map of open-source projects relevant to the Sharpe-Renaissance
alpha/investment track. It is not an endorsement list. The operating rule for this
repo remains: backtests are research evidence; paper/live scorecards decide
promotion.

## Best Fits For This Repo

| Project | Category | Why it matters here | Suggested use |
| --- | --- | --- | --- |
| Microsoft Qlib | AI quant research platform | Strongest open-source reference for ML-driven quantitative investment lifecycle. | Borrow lifecycle abstractions: data -> feature -> model -> portfolio -> backtest -> report. |
| Microsoft RD-Agent | Automated quant R&D | Multi-agent quant research loop around factor/model discovery, including Qlib workflows. | Study for future automated alpha research, not immediate execution. |
| OpenBB | Financial data and analyst tooling | Good connector/data-access model for stock, macro, fundamentals, and agent-facing tools. | Reference for data surfaces and research cockpit APIs. |
| FinRobot | LLM equity research agents | Financial analysis/reporting agent platform with equity-research emphasis. | Keep as research-report/thesis layer, not direct sizing logic. |
| FinGPT | Financial LLM/text models | Useful for financial text, sentiment, filings/news labels, and financial language benchmarks. | Candidate benchmark for news/activity features. |
| QuantConnect Lean | Production backtest/live engine | Mature multi-asset execution/accounting engine. | Reference for live discipline if this repo grows beyond paper trading. |
| Lumibot | Broker-connected AI/strategy framework | Backtest, paper, and live stock strategies with broker integrations. | Reference for stock paper/live abstraction. License review required. |
| vectorbt / Zipline / Backtrader / bt | Research/backtest libraries | Useful patterns for event studies, fast sweeps, and portfolio simulations. | Use as reference; avoid framework migration unless it removes real work. |
| PyPortfolioOpt / cvxportfolio / skfolio | Portfolio construction | Optimizer/risk-model references for allocation beyond signal generation. | Good candidates if current signal pipeline needs better portfolio construction. |
| TradingAgents / ai-hedge-fund / Vibe-Trading | LLM investment-agent demos | Show current product direction for stock-analysis agents. | Borrow UI/agent-debate/reporting patterns only. |

## Project Classes

### AI Quant Research And Alpha Mining

These are the closest matches to the current Sharpe-Renaissance alpha pipeline:
feature construction, walk-forward testing, portfolio formation, and promotion
gates.

| Project | Focus | Practical read |
| --- | --- | --- |
| `microsoft/qlib` | AI-oriented quantitative investment platform for supervised learning, market dynamics modeling, RL, backtesting, portfolio/risk/order execution. | Strongest architecture reference. |
| `microsoft/RD-Agent` | Automated R&D agent for data-centric factors and model optimization, with Qlib-oriented quant workflows. | Most relevant "AI agent" project for alpha research rather than chatty trading. |
| `AI4Finance-Foundation/FinRL` | Deep RL library for automated stock trading. | Useful for experiments, not promotion without strict paper/live evidence. |
| `AI4Finance-Foundation/FinRL-Trading` | FinRL-X style data/strategy/backtesting/execution interfaces. | More relevant than classic RL demos if research-to-paper consistency matters. |
| `UFund-Me/Qbot` | Local AI quantitative investment research platform with data, AI strategy research, factor mining, backtest, simulation, and live trading claims. | Broad stock-quant workbench reference; inspect maturity before reuse. |
| `QuantaAlpha/QuantaAlpha` | LLM-driven self-evolving factor mining and backtesting UI. | Watch for factor-mining workflow ideas. Needs evidence audit. |
| `huseinzol05/Stock-Prediction-Models` | Collection of ML/deep-learning stock forecasting models, bots, and simulations. | Historical model zoo; useful as baseline inspiration, not architecture. |
| `borisbanushev/stockpredictionai` | Notebook-heavy stock price movement prediction using GAN/LSTM/CNN/RL/NLP features. | Interesting older research artifact; high overfit/leakage risk. |

What to borrow:

- Reproducible experiment layout.
- Feature/model/portfolio separation.
- Walk-forward and holdout discipline.
- Factor-mining idea generation only if every generated factor lands in the same
  validation/promotion machinery as hand-written factors.

What not to borrow:

- Notebook-only prediction claims.
- Direct price forecasts without portfolio/risk accounting.
- Agent-generated factors that skip leakage, cost, and paper/live evaluation.

### LLM Stock / Investment Agents

This is the noisy part of the ecosystem. Most projects are product/research demos,
but several are still useful references for workflow design.

| Project | Focus | Practical read |
| --- | --- | --- |
| `AI4Finance-Foundation/FinRobot` | Equity research reports, financial analysis agents, valuation/risk workflows. | Best aligned with a research-note layer. |
| `TauricResearch/TradingAgents` | Multi-agent trading-firm simulation: analysts, bull/bear debate, risk team, trader. | Strong product/reference architecture; use outputs as notes, not orders. |
| `virattt/ai-hedge-fund` | Educational multi-agent hedge-fund proof of concept. | Useful for agent roles and UX; explicitly not production trading. |
| `Open-Finance-Lab/AgenticTrading` | Agentic trading research/orchestration framework. | Watchlist; inspect evaluation protocol before adopting. |
| `HKUDS/AI-Trader` | Agent-native trading platform. | Ambitious platform idea; maturity and benchmarks need audit. |
| `HKUDS/Vibe-Trading` | Personal trading agent with MCP/tool integration and IBKR read-only flow. | Useful connector/tool-registry pattern for a research cockpit. |
| `pipiku915/FinMem-LLM-StockTrading` | Memory-enhanced LLM trading agent for stocks/funds. | Relevant to agent memory; risky for execution unless calibrated. |
| `TradingGoose/TradingGoose.github.io` | Multi-agent LLM stock/portfolio analysis framework. | Similar value to TradingAgents; license caution. |
| `MingyuJ666/Stockagent` | Multi-agent LLM simulation of investor trading behavior in stock markets. | More useful for behavioral simulation/evaluation than direct trading. |
| `zhound420/swarm-trader` | Multi-agent stock research/trading system using SEC/yfinance/Alpaca. | Small but representative of "named investor agents" pattern. |
| `novalgo-x/LingTrade` | Local A-share AI research workstation with multi-agent analysis and simulated trading loop. | Useful regional stock-agent reference. |
| `pseudo-longinus/quant-buddy-skills` | A/HK/US stock quant agent skill set for market data, fundamentals, factor analysis, screening, backtesting. | Interesting operator-tooling pattern for Asian/US stocks. |

Design lesson for Sharpe-Renaissance: multi-agent debate is a UI/research pattern.
It should produce a thesis, risk notes, contradiction checks, and vetoes. The
deterministic strategy/risk code should still own weights and execution.

### Backtest, Paper, And Live Stock Infrastructure

These projects matter because a profitable-looking model is irrelevant without
execution accounting, broker assumptions, costs, and reconciliation.

| Project | Core angle | Practical read |
| --- | --- | --- |
| `QuantConnect/Lean` | Multi-asset backtest/live engine with mature accounting. | Best production-discipline reference. |
| `Lumiwealth/lumibot` | Backtestable AI agents and deterministic strategies for stocks/options/futures/forex with broker integrations. | Strong stock paper/live abstraction reference; GPL constraints. |
| `nautechsystems/nautilus_trader` | Event-driven execution engine with serious accounting/risk architecture. | Future live-engine reference; heavy for current scope. |
| `backtrader/backtrader` / `mementum/backtrader` | Classic Python backtesting framework. | Useful reference, but older and GPL. |
| `stefan-jansen/zipline-reloaded` | Maintained Zipline fork for equities-style research. | Good reference for pipeline-style equity backtests. |
| `polakowo/vectorbt` | Fast vectorized strategy research. | Useful if current alpha sweeps become too slow. |
| `pmorissette/bt` | Flexible portfolio backtesting. | Simple reference for portfolio-level simulations. |
| `vnpy/vnpy` | Python quant platform with broker gateways, strong China/Asia ecosystem. | Useful gateway/plugin architecture reference. |
| `StockSharp/StockSharp` | C# algo-trading platform for stocks, futures, options, and FX. | Mature platform scope comparison. |
| `blankly-finance/blankly` | One Python strategy interface for backtest, paper, live. | Simple abstraction reference, but check activity. |
| `marketcalls/openalgo` | Self-hosted strategy/execution platform for Indian brokers. | Useful Asian broker-bridge reference. |

What matters for this repo:

- Paper/live ledger continuity.
- Trade cost, slippage, fill, and benchmark accounting.
- Idempotent runs and reproducible daily/monthly cycles.
- Broker integration only after paper evidence is acceptable.

### Data, Fundamentals, And Research Workbenches

| Project | Focus | Practical read |
| --- | --- | --- |
| `OpenBB-finance/OpenBB` | Data terminal/platform for stocks, ETFs, macro, options, fundamentals, and analyst workflows. | Best data connector and research UX reference. |
| `AI4Finance-Foundation/FinGPT` | Financial LLMs, sentiment, forecasting, datasets, and benchmarks. | Useful for text/news labels and financial-language baselines. |
| `AI4Finance-Foundation/Awesome_AI4Finance` | Curated AI finance project list. | Discovery index, not a system to adopt. |
| `leoncuhk/awesome-quant-ai` | Curated AI quant/trading resources. | Good watchlist for newer AI quant projects. |
| `Sasha-Cui/Awesome-Applied-Agents-for-Investment` | Curated applied investment-agent papers/artifacts. | Good reading-pack source for stock-agent methods. |
| `Tom-roujiang/Awesome-LLM-Quantitative-Trading-Papers` | LLM quantitative trading paper/code list. | Useful for factor-mining and agent-research survey work. |

### Portfolio Construction, Risk, And Evaluation

| Project | Focus | Practical read |
| --- | --- | --- |
| `PyPortfolio/PyPortfolioOpt` | Mean-variance, Black-Litterman, covariance shrinkage, HRP. | Lightweight optimizer reference. |
| `cvxgrp/cvxportfolio` | Convex multi-period portfolio optimization and simulation. | More serious optimizer/backtest reference. |
| `skfolio/skfolio` | scikit-learn-compatible portfolio optimization and risk management. | Good if cross-validation and stress testing become central. |
| `hudson-and-thames/mlfinlab` | Financial ML techniques: labeling, purged CV, feature importance, fractional differentiation. | Strong concept reference; license/current package status needs care. |
| `baobach/mlfinpy` | Open implementation inspired by financial ML methods. | Candidate for ideas, not dependency without audit. |
| `quantopian/alphalens` | Factor return/IC/turnover analysis. | Useful factor-reporting reference; project age matters. |
| `ranaroussi/quantstats` | Portfolio analytics/reporting. | Good report reference; this repo already has DSR/PBO and scorecards. |
| `jankrepl/deepdow` | Deep-learning portfolio optimization. | Research reference if neural portfolio construction becomes a track. |

### Benchmarks And Evaluation Work

These are more valuable than another trading-agent demo because they address the
core question: whether an agent or model has evidence instead of narration.

| Project / benchmark | Focus | Practical read |
| --- | --- | --- |
| `ulab-uiuc/live-trade-bench` | Live LLM trading-agent evaluation, including stocks. | Useful for live-evaluation design; ignore non-stock tracks. |
| `felis33/INVESTOR-BENCH` / InvestorBench | Financial decision-making benchmark across stocks, ETFs, and other assets. | Good task taxonomy; use stock/ETF tasks only and inspect leakage/cost assumptions. |
| StockBench | LLM stock-trading benchmark. | Useful benchmark reference; verify baselines and market simulator realism. |
| FinLLM-Leaderboard / PIXIU / FinEval-style work | Financial LLM/data evaluation ecosystem. | Useful for model selection on financial text, not direct trading edge. |

## Current Metadata Checked

GitHub API and source-page metadata was checked for representative projects. Star
counts are popularity signals, not quality. Missing/uncertain license fields require
a source audit before any reuse.

| Repo | Snapshot metadata | Initial verdict |
| --- | --- | --- |
| `microsoft/qlib` | ~45k stars, MIT, active 2026 | Strongest AI quant architecture reference. |
| `microsoft/RD-Agent` | active 2026, MIT source surfaced | Automated quant R&D reference. |
| `OpenBB-finance/OpenBB` | ~70k stars, active 2026, mixed/noassertion | Strong data-layer reference. |
| `QuantConnect/Lean` | ~20k stars, Apache-2.0, active 2026 | Live/backtest engine reference. |
| `TauricResearch/TradingAgents` | very high-star, Apache-2.0, active 2026 | Product/agent-reference pattern. |
| `virattt/ai-hedge-fund` | very high-star, MIT, active 2026 | Educational agent architecture reference. |
| `AI4Finance-Foundation/FinGPT` | ~20k stars, MIT, active 2026 | Financial text/LLM reference. |
| `AI4Finance-Foundation/FinRL` | ~15k stars, MIT, active 2026 | RL stock-trading research reference. |
| `AI4Finance-Foundation/FinRobot` | ~7k stars, Apache-2.0, active 2026 | Equity-research agent reference. |
| `UFund-Me/Qbot` | ~18k stars from source pages, MIT surfaced | Broad AI quant platform; audit code maturity. |
| `QuantaAlpha/QuantaAlpha` | active source page | Watchlist for LLM factor mining. |
| `Lumiwealth/lumibot` | ~1.7k stars, GPL-3.0, active 2026 | Broker-connected AI/stock strategy framework. |
| `polakowo/vectorbt` | ~8k stars, active 2026 | Fast research sweeps. |
| `ranaroussi/quantstats` | ~7k stars, Apache-2.0, active 2026 | Reporting/analytics reference. |
| `huseinzol05/Stock-Prediction-Models` | ~9k stars, Apache-2.0 surfaced, older | Model zoo; high overfit risk. |
| `borisbanushev/stockpredictionai` | ~5.6k stars, older notebook | Historical deep-learning stock-prediction artifact. |
| `PyPortfolio/PyPortfolioOpt` | active docs/source | Portfolio optimizer reference. |
| `cvxgrp/cvxportfolio` | active docs/source | Convex optimizer/backtester reference. |
| `skfolio/skfolio` | active source | Portfolio optimization/risk reference. |

## Recommended Sharpe-Renaissance Engineering Response

1. Do not migrate to a framework just because it is popular. This repo's current
   bottleneck is evidence quality, not framework choice.
2. Borrow Qlib/RD-Agent vocabulary for the research lifecycle:
   dataset -> feature -> model -> portfolio -> backtest -> risk -> paper/live ->
   report.
3. Keep FinRobot/FinGPT/TradingAgents-style LLM output behind a strict research-note
   interface:
   - thesis
   - evidence links
   - contradiction checks
   - risk notes
   - veto/confirm label
4. Let deterministic code own all executable portfolio weights.
5. Use Lean/Lumibot/Nautilus as references for execution/accounting only when live
   trading becomes a near-term target.
6. Add a project-intake rubric before adopting any external repo:
   - license clear
   - data assumptions clear
   - leakage controls present
   - transaction costs modeled
   - paper/live ledger available
   - reproducible examples
   - no direct capital allocation by opaque agent output
7. Keep current strategy statuses:
   - `research_only`
   - `radar`
   - `paper_candidate`
   - `deployable_sleeve`

## Out Of Scope

Prediction-market, Kalshi/Polymarket, crypto-only, DeFi, and cross-venue arbitrage
bots are not part of this repo's current direction. They can be revisited only if
the product scope changes.

## Sources

- https://github.com/microsoft/qlib
- https://github.com/microsoft/RD-Agent
- https://github.com/AI4Finance-Foundation/FinRL
- https://github.com/AI4Finance-Foundation/FinRL-Trading
- https://github.com/AI4Finance-Foundation/FinGPT
- https://github.com/AI4Finance-Foundation/FinRobot
- https://github.com/OpenBB-finance/OpenBB
- https://github.com/QuantConnect/Lean
- https://github.com/Lumiwealth/lumibot
- https://github.com/nautechsystems/nautilus_trader
- https://github.com/backtrader/backtrader
- https://github.com/mementum/backtrader
- https://github.com/stefan-jansen/zipline-reloaded
- https://github.com/polakowo/vectorbt
- https://github.com/pmorissette/bt
- https://github.com/vnpy/vnpy
- https://github.com/StockSharp/StockSharp
- https://github.com/blankly-finance/blankly
- https://github.com/marketcalls/openalgo
- https://github.com/UFund-Me/Qbot
- https://github.com/QuantaAlpha/QuantaAlpha
- https://github.com/huseinzol05/Stock-Prediction-Models
- https://github.com/borisbanushev/stockpredictionai
- https://github.com/TauricResearch/TradingAgents
- https://github.com/virattt/ai-hedge-fund
- https://github.com/Open-Finance-Lab/AgenticTrading
- https://github.com/Open-Finance-Lab/FinLLM-Leaderboard
- https://github.com/HKUDS/AI-Trader
- https://github.com/HKUDS/Vibe-Trading
- https://github.com/pipiku915/FinMem-LLM-StockTrading
- https://github.com/TradingGoose/TradingGoose.github.io
- https://github.com/MingyuJ666/Stockagent
- https://github.com/zhound420/swarm-trader
- https://github.com/novalgo-x/LingTrade
- https://github.com/pseudo-longinus/quant-buddy-skills
- https://github.com/PyPortfolio/PyPortfolioOpt
- https://github.com/cvxgrp/cvxportfolio
- https://github.com/skfolio/skfolio
- https://github.com/hudson-and-thames/mlfinlab
- https://github.com/baobach/mlfinpy
- https://github.com/quantopian/alphalens
- https://github.com/ranaroussi/quantstats
- https://github.com/jankrepl/deepdow
- https://github.com/ulab-uiuc/live-trade-bench
- https://github.com/felis33/INVESTOR-BENCH
- https://github.com/AI4Finance-Foundation/Awesome_AI4Finance
- https://github.com/leoncuhk/awesome-quant-ai
- https://github.com/Sasha-Cui/Awesome-Applied-Agents-for-Investment
- https://github.com/Tom-roujiang/Awesome-LLM-Quantitative-Trading-Papers
