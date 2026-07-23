# Alpha research engine

Walk-forward signals, paper trading, IDN sleeve, research integrity, execution layer.

## Owns

- `alpha/scripts/` — `alpha_live_cycle`, `run_unified_platform_cycle`, IDN suite
- `alpha/src/` — strategy, intelligence, research integrity toolkit
- `alpha/trading/` — brokers, live executor
- `alpha/high_perf/` — Rust extension
- `alpha/engine/` — Refinitiv / LLM services
- `alpha/api/` — FinSight product API (separate from desk `:8765`)
- `alpha/config/` — `platform_integration.json`, tickers, thesis register

## Entry points

```bash
python alpha/scripts/alpha_live_cycle.py
python alpha/scripts/run_unified_platform_cycle.py
bash alpha/scripts/run_research_spine.sh cycle
python alpha/scripts/alpha_daily_scorecard.py
```

Legacy paths under `scripts/` are symlinks into this tree.

## Contract with Drive

- **Reads** registry + panel paths via `kernel/sharpe_kernel/platform_bridge.py`
- Does **not** import `yzu_cluster` or MCP modules
- Shared data root: `data_lake/` (gitignored), `backtests/outputs/`

See `../REPO_LAYOUT.md`.
