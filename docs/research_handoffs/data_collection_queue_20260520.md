# Data Collection Queue

Date: 2026-05-20

This repo now has a lightweight local queue for safe, no-login data collection tasks.

## Files

- `config/data_collection_queue.json` - task catalog.
- `scripts/run_data_collection_queue.py` - sequential queue runner.
- `scripts/check_data_collection_queue.py` - compact status report.
- `data_lake/data_collection_queue/status.jsonl` - append-only queue status.
- `logs/data_collection_queue/` - per-task logs.

## Current Auto-Run Tasks

Enabled no-login tasks:

- Public macro/market baseline.
- SEC ticker-to-CIK mapping.
- SEC EDGAR submissions for the S&P 500 ticker list.
- 10-year yfinance global drilldown panel.
- Bounded GDELT DOC headline pilot for IDN/USA, 2024-01 through 2026-05.

Blocked/manual tasks are cataloged but not run:

- Full GDELT DOC headline backfill.
- Refinitiv/LSEG IDX core backfill.
- WRDS CRSP/Compustat/CCM backfill.

## Commands

Start queue:

```bash
nohup nice -n 10 ionice -c2 -n7 .venv/bin/python scripts/run_data_collection_queue.py \
  > logs/data_collection_queue/queue_nohup.log 2>&1 &
```

Check queue:

```bash
.venv/bin/python scripts/check_data_collection_queue.py
```

Tail current logs:

```bash
tail -f logs/data_collection_queue/queue_nohup.log
```

## Rule

The runner does not execute tasks that require credentials. Lab/paid datasets stay in the catalog until the user resolves access manually.
