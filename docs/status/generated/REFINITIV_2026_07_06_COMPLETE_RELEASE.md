# Refinitiv Complete Harvest — Release `2026-07-06-complete`

**Status:** RELEASE FROZEN · query-ready · bulk harvest STOP  
**Platform rating:** 9.0/10 for university-seat research platform; entitled job coverage 100%  
**Canonical path:** `data_lake/refinitiv_backfill/2026-07-06-complete/`  
**GDrive:** `gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/refinitiv_backfill/2026-07-06-complete`

## What this release is

Institutional market spine from LSEG Platform (YZU EDP) plus one desktop Eikon rescue panel. This is the **practical ceiling** of the current license — not a pilot.

```text
570-RIC security spine
548k PIT index membership rows (6 indices, monthly 2010–2026)
2.6k current index members (5 indices; .STI current snapshot blocked)
corporate action adjustment-factor seed
733k risk/SI rows (SI% history + vol/put-call snapshot)
576k EPS estimate revision rows
FY fundamentals (fundamental_and_reference)
analyst consensus snapshot
ESG snapshot
15.6M rescued desktop US vol/skew/SI panel
```

## Do not recollect

| Lane | Policy |
|------|--------|
| Refinitiv OHLCV | **Skip** — yfinance + IDX legacy cover prices |
| Refinitiv news | **Skip** — GDELT expanded fleet is canonical |
| Bulk ownership / supply chain / StarMine | **Blocked** — fields do not resolve on EDP |
| Re-run `--job complete` on this stamp | **Forbidden** — use a new stamp only for targeted probes |

## Entitlement caveats (honest gaps)

| Gap | Mitigation |
|-----|------------|
| Institutional ownership | License-blocked; not pending collection |
| Supply chain graph | License-blocked |
| StarMine / SmartEstimate | License-blocked |
| EDP vol 30/90 **daily history** | Mostly empty; use `rescued_desktop_20251215` for US |
| PIT fundamentals FQ | FQ period blocked; FY via `FRQ=FY` only |
| Corporate actions | Adjustment-factor **snapshot**; not full event-grade CA feed |
| `.STI` current membership | PIT works; current snapshot fails on EDP |

## Raw artifacts (`processed/`)

| File | Rows | Query status |
|------|------|--------------|
| `refinitiv_security_master.parquet` | 570 | query-ready |
| `index_membership_pit.parquet` | 548,460 | query-ready |
| `index_membership_current.parquet` | 2,641 | query-ready (partial: no .STI) |
| `corporate_actions_snapshot.parquet` | 570 | partial — adjustment-factor seed |
| `vol_surface_metrics_daily.parquet` | 733,528 | query-ready; SI history + vol snapshot |
| `estimate_revisions_daily.parquet` | 576,968 | query-ready |
| `fundamentals_panel.parquet` | 797 | FY fundamentals, not FQ PIT |
| `analyst_consensus_snapshot.parquet` | 570 | snapshot |
| `esg_snapshot.parquet` | 570 | snapshot |
| `rescued_desktop_20251215/.../us_risk_vol_skew_daily.parquet` | 15.6M | US desktop Eikon panel |

## Derived panels (`data_lake/research_panels/refinitiv/2026-07-06-complete/`)

Built by `scripts/refinitiv_build_derived_panels.py`:

| Panel | Purpose |
|-------|---------|
| `survivorship_universe_panel.parquet` | PIT index × month × constituent + sector/country |
| `us_risk_overlay.parquet` | SI% + rescued US vol/skew/SI |
| `estimate_revision_panel.parquet` | EPS mean + 1m/3m/6m revision deltas |
| `fundamental_annual_panel.parquet` | FY revenue/income/debt/FCF tidy |
| `entity_market_spine.parquet` | RIC spine + GDELT entity_id + index flags |

## Research Drive

Library path: **Institutional market data → Refinitiv complete harvest 2026-07-06**

Registry: all Refinitiv datasets use `default_run_id: 2026-07-06-complete` with `entitlement_status`, `field_coverage`, `known_gap`, `best_use` metadata.

## Targeted probes only (if license changes)

```bash
.venv-refinitiv/bin/python scripts/refinitiv_value_entitlement_probe.py --env .env.local
```

Probe categories worth re-checking: D8 FQ/LTM, G1 ownership, I1 supply chain, F1 StarMine, desktop Eikon vol refresh.

## Best near-term research angles

1. **GDELT news shocks → analyst revisions** in survivorship-correct index universes  
2. **Short-interest crowding** around news shocks (GDELT + SI history + PIT universe)  
3. **Indonesia institutional panel** (.JKSE PIT + IDX legacy prices + spine)  
4. **ESG/governance event response** (ESG snapshot + GDELT/MOPS + revisions)

## Commands

```bash
# Rebuild derived panels (safe; does not touch frozen raw run)
.venv-refinitiv/bin/python scripts/refinitiv_build_derived_panels.py

# Registry + INDEX refresh
.venv-refinitiv/bin/python scripts/refinitiv_promote_registry.py

# Completion scorecard
.venv-refinitiv/bin/python scripts/refinitiv_harvest_completion.py
```

**Do not** schedule more bulk Refinitiv jobs in `data_collection_queue.json`.
