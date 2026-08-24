# GDELT expanded fleet — cluster layout

Windows work-steal fleet for **expanded GDELT GKG** (2018 → 2026-07-01), separate from the older Asia monthly backlog. Config: `config/gdelt_expanded_fleet.json`, queue plan: `config/gdelt_expanded_queue.json`.

---

## Where downloads land (optiplex / cluster controller)

**Bulk cache (Transcend USB)** — canonical local bytes for analysis:

```text
/media/phyrexian/Transcend/sharpe-renaissance/data_lake/news_shock_taxonomy/normalized/gdelt_gkg_expanded_bulk/
```

Repo-relative (symlink → same tree):

```text
Sharpe-Renaissance/data_lake/news_shock_taxonomy/normalized/gdelt_gkg_expanded_bulk/
```

Each completed window is a directory:

```text
expanded_gkg_window_YYYYMMDD_YYYYMMDD_20260626TexpandedZ/
  └── asia_gkg_filtered.csv.gz   # normalized bulk artifact
```

**Staging / fetch temp** (workers unpack here during runs):

```text
/media/phyrexian/Transcend/sharpe-renaissance/tmp/gdelt_expanded
```

(`SR_GDELT_TMP` / `sr_gdelt_tmp` in fleet config.)

**Queue state & manifest** (progress, pending windows):

```text
data_lake/news_shock_taxonomy/derived/gdelt_expanded_queue_state/
  queue_manifest.json
  pending_windows.jsonl
  completed_months.txt
```

**Work-steal locks:**

```text
data_lake/news_shock_taxonomy/backfill_status/gdelt_expanded_work_steal_locks/
```

---

## Vault (GDrive)

Long-term archive under collection partition `news.gdelt-expanded`:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/news_shock_taxonomy
```

See `config/collection_partitions.json` (`legacy_local_path` → `gdelt_gkg_expanded_bulk`).

---

## Stablecoin synthesis overlay (different path)

Trust↔engagement synthesis reads **crypto entity overlay**, not the raw expanded bulk tree directly:

```text
data_lake/news_shock_taxonomy/derived/gdelt_crypto_overlay
```

Profile: `config/synthesis_profiles.json` → `stablecoin_trust_engagement.paths.gdelt_overlay`. Full overlay rebuild waits on expanded fleet completion (~Jul 7 handoff).

---

## Ops commands

```bash
# Fleet status (Windows workers)
bash scripts/run_news_shock_gkg_expanded_fleet.sh status

# Ensure workers running
bash scripts/run_news_shock_gkg_expanded_fleet.sh ensure

# Refresh queue plan
python3 scripts/plan_news_shock_gkg_expanded_queue.py

# Single-controller forward queue
bash scripts/run_news_shock_gkg_expanded_forward_queue.sh
```

Collection queue entry: `gdelt_gkg_expanded_full_2018_present` in `config/data_collection_queue.json`.

---

## Progress snapshot (check live manifest)

Read `queue_manifest.json` for current `complete_months` / `total_months` and `run_tag` (e.g. `20260626TexpandedZ`). Bulk dir size:

```bash
du -sh /media/phyrexian/Transcend/sharpe-renaissance/data_lake/news_shock_taxonomy/normalized/gdelt_gkg_expanded_bulk
```

NVMe `data_lake/` hot tier intentionally excludes bulk GDELT — keep heavy paths on Transcend (`config/storage_tiers.json`).

## Troubleshooting (2026-07)

| Symptom | Fix |
|---------|-----|
| `platform_env.sh: No such file` | Run `bash scripts/fix_platform_env_paths.sh` (repo-split regression) |
| `tar: Cannot write: No space left on device` | `/tmp` full — fleet uses `SR_GDELT_TMP` on Transcend; ensure `TMPDIR` set in fleet env |
| Windows `Start-Process` Python missing | Use `C:\Users\user\anaconda3\python.exe` in `gdelt_expanded_fleet.json` (not `py` on all hosts) |
| Stuck at 60/102, fail loop | Check `logs/news_shock_taxonomy/expanded_work_steal/helper_*.log` |

**Ops:** `bash scripts/run_news_shock_gkg_expanded_fleet.sh {status|ensure|probe|stop}`

Retention after 102/102: [`GDELT_RETENTION_PLAN.md`](GDELT_RETENTION_PLAN.md) — `python3 scripts/ops/gdelt_retention_status.py`

## Auto-monitor (stall + recovery)

Install once (user systemd, every 15 min):

```bash
bash scripts/install_gdelt_expanded_fleet_monitor_systemd_user.sh
```

Checks: `complete_months` stall (warn 3h / crit 6h → auto `fleet ensure`), worker count, `/tmp` %, Transcend free space.

| Artifact | Path |
|----------|------|
| Alert JSON | `docs/status/generated/gdelt_expanded_fleet_alert.json` |
| Monitor log | `logs/news_shock_taxonomy/expanded_work_steal/fleet_health_monitor.log` |

6th lane: `helper_optiplex` (`kind: local` in fleet config) — 2 parallel fetch workers on desk host.

