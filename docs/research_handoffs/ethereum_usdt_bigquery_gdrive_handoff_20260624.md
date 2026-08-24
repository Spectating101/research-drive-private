# Ethereum USDT (Tether) — BigQuery + GDrive Handoff

**Date:** 2026-06-24  
**Scope:** USDT on Ethereum mainnet via Google BigQuery public dataset; local exports + GDrive vault  
**Status:** Daily history **complete**; raw monthly export **paused** at 2019-06  
**GCP project:** `search-485108`  
**Registry dataset:** `ethereum_usdt_transfers`

---

## Executive summary

We validated BigQuery as the replacement for Etherscan bulk download of USDT transfer history. Etherscan pagination cannot archive ~562M transfers (USDT alone peaks ~1.5M/day). BigQuery public blockchain data is queryable by any GCP project with ADC + billing; it is **not** tied to Google One/Workspace Pro.

**Two deliverable tiers exist:**

| Tier | What | Status | Re-query BigQuery? |
|---|---|---|---|
| **Daily panel** | 1 row/day aggregates (volume, counts, large-tx stats) | **Done** — 2017-11-28 → 2026-06-24 | **No** (use CSV on Drive) |
| **Raw transfers** | Every ERC-20 Transfer event, month shards | **Paused** — 20 months, 617,885 rows | **Yes** for months not exported |

**BigQuery billing model (critical):** quota is charged on **bytes scanned**, not rows returned. ~545 GiB scan produced 3,081 daily rows. Full raw export requires a **separate** scan pass (~300–500 GiB estimated total).

---

## Source of truth

| Field | Value |
|---|---|
| Token | USDT (Tether USD) |
| Chain | Ethereum mainnet only |
| Contract | `0xdac17f958d2ee523a2206206994597c13d831ec7` |
| BigQuery table | `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.token_transfers` |
| Filter | `WHERE address = '<contract>'` + **always** `DATE(block_timestamp)` bounds |

**Not included:** Tron/BSC/other-chain USDT; exchange/wallet labels; Etherscan UI metadata.

---

## Credentials & environment

```bash
export GOOGLE_CLOUD_PROJECT=search-485108
# ADC file (already present):
# ~/.config/gcloud/application_default_credentials.json
# type: authorized_user, quota_project_id: search-485108
```

Optional `.env`:

```
GOOGLE_CLOUD_PROJECT=search-485108
```

`gcloud` CLI not required for queries if ADC exists; needed to refresh OAuth.

**Free tier:** ~1 TiB query bytes processed / month / billing project. Overage ~$6.25/TiB.

---

## What is on Google Drive

**Vault root:** `gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data`

### 1. Professor package (summaries)

```
collection/markets/ethereum-usdt/professor_package/
  daily_usdt_flows_all.csv      # 3,081 days, full history
  monthly_usdt_summary.csv      # 104 months
  usdt_large_transfers_recent_7d.csv
  token_info.json
  README.md
```

### 2. Daily history shards

```
collection/markets/ethereum-usdt/bigquery_history/
  daily_usdt_flows_all.csv
  shards/daily_usdt_flows_YYYY.csv
  manifest.json
```

### 3. Raw transfers (partial)

```
collection/markets/ethereum-usdt/raw_transfers/
  usdt_transfers_2017-11.parquet
  ...
  usdt_transfers_2019-06.parquet   # last completed month
```

**Checkpoint:** 20 months, **617,885** transfers (~0.11% of 562,045,593 total).  
**Stopped:** user-cancelled 2026-06-24; schema bug on 2019-04 fixed (`value_usdt` → float).

---

## Local paths (repo)

| Path | Contents |
|---|---|
| `data/usdt_catalogue/bigquery_history/` | Daily panel + manifest |
| `data/usdt_catalogue/professor_package/` | Professor-facing bundle |
| `data/usdt_catalogue/raw_transfers/manifest.json` | Raw export job state |
| `sql/bigquery/usdt/*.sql` | Guarded SQL templates |
| `scripts/usdt_catalogue/bigquery_usdt_pilot.py` | Single-SQL dry-run/run |
| `scripts/usdt_catalogue/bigquery_usdt_history_harvest.py` | Yearly daily harvest |
| `scripts/usdt_catalogue/bigquery_usdt_raw_harvest.py` | Monthly raw → Parquet → rclone |

---

## BigQuery quota spent (this session, approximate)

| Job | GiB scanned | Output |
|---|---|---|
| Daily harvest 2017–2026 | ~545 | 3,081 rows CSV |
| Pilot / probes | ~20 | small samples |
| Raw export (20 months) | ~40 | 617,885 rows Parquet |
| **Total** | **~590 / 1024 GiB free tier** | |

Full raw export (remaining ~99.9% of rows) estimated **~300–500 GiB additional** scan.

---

## History volume (why raw export is huge)

| Year | USDT transfers (Ethereum) |
|---|---|
| 2017 | 35 |
| 2018 | 37,698 |
| 2019 | 14,828,632 |
| 2020 | 66,180,042 |
| 2024 | 59,886,884 |
| 2025 | 130,707,534 |
| 2026 YTD | 150,893,200 |
| **Total** | **562,045,593** |

Early months are tiny; **61% of rows are 2024+**. Export runtime and Drive size grow sharply after 2019.

---

## Commands

### Status

```bash
export GOOGLE_CLOUD_PROJECT=search-485108
PYTHONPATH=. .venv/bin/python scripts/research_query_engine_cli.py \
  query ethereum_usdt_transfers action=status
```

### Dry-run cost (any SQL file)

```bash
.venv/bin/python scripts/usdt_catalogue/bigquery_usdt_pilot.py \
  --project search-485108 \
  --sql sql/bigquery/usdt/03_large_usdt_transfers_recent.sql
```

### Refresh daily history (skips existing year shards)

```bash
.venv/bin/python scripts/usdt_catalogue/bigquery_usdt_history_harvest.py \
  --project search-485108 --start-year 2017
```

### Resume raw monthly export → GDrive

```bash
.venv/bin/python scripts/usdt_catalogue/bigquery_usdt_raw_harvest.py \
  --project search-485108 \
  --start-month 2017-11 \
  --upload-remote 'gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/markets/ethereum-usdt/raw_transfers'
```

Skips months in `data/usdt_catalogue/raw_transfers/manifest.json` with `status: ok`.

### Sync summaries to Drive

```bash
rclone copy data/usdt_catalogue \
  "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/markets/ethereum-usdt" \
  --exclude "bigquery_history_harvest.log" --exclude "raw_transfers_harvest.log"
```

### List raw files on Drive

```bash
rclone lsf "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/markets/ethereum-usdt/raw_transfers"
```

---

## Procurement stack integration

| Surface | Entry |
|---|---|
| Registry | `config/research_query_registry.json` → `ethereum_usdt_transfers` |
| Query engine | `scripts/research_query_engine_cli.py query ethereum_usdt_transfers action=dry_run` |
| MCP tools | `bigquery_status`, `bigquery_dry_run`, `bigquery_read_query` |
| HTTP | `/library/extensions/bigquery/status` (query engine :8765) |
| YZU job type | `bigquery_query` |

**Recommended procurement pattern:**

1. `dry_run` / `bigquery_dry_run` — byte estimate before spend  
2. Export bounded slice (month / large-tx template)  
3. `rclone` to `collection/markets/ethereum-usdt/`  
4. Register in flywheel; **read from Drive** for repeat analysis (no re-scan)

**Do not** rely on multi-account free-tier rotation as architecture (ToS risk). Prefer export-once + Drive canonical copy.

---

## Decision guide

| Research question | Use |
|---|---|
| Volume trends 2017–now | `daily_usdt_flows_all.csv` on Drive |
| Monthly aggregates | `monthly_usdt_summary.csv` |
| Recent whale txs (≥$1M, 7d) | `usdt_large_transfers_recent_7d.csv` or SQL template 03 |
| Individual txs, month already on Drive | Parquet for that month (DuckDB/pandas) |
| Individual txs, month not exported | BigQuery SQL + date filter (costs scan) OR resume raw harvest |
| Full history, never pay BQ again | Complete raw harvest once (~300–500 GiB scan) |

---

## Known issues / fixes applied

| Issue | Fix |
|---|---|
| 2025 daily harvest exceeded 100 GiB guard | Raised `max_bytes_billed` to 160 GiB for recent years |
| Raw export crash 2019-04 | PyArrow decimal schema mismatch — cast `value_usdt` to float in `bigquery_usdt_raw_harvest.py` |
| `professor_package` symlink | Replaced with real `daily_usdt_flows_all.csv` before Drive upload |

---

## Next steps (pick one)

1. **Resume raw export** — finish 2019-07 → present (~561M rows, largest work item)  
2. **USDC / DAI** — clone harvest scripts + registry entry (same BigQuery table, different `address`)  
3. **Professor deliverable only** — daily + monthly + 7d large txs may suffice without full raw  
4. **Wire procurement** — add stablecoin BigQuery export as registered pipeline in `yzu_cluster.json`

---

## Related docs

- `docs/research_data_mcp.md` — BigQuery MCP tools  
- `docs/PROCUREMENT_PIPELINE.md` — canonical procurement architecture  
- `config/collection_partitions.json` — GDrive vault layout (`markets` domain)  
- `data/usdt_catalogue/professor_package/README.md` — package interpretation
