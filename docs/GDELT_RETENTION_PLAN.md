# GDELT retention plan

**Goal:** end with **queryable datasets** (overlays + published panels), not ~500 GB of duplicate pipeline shards forever.

Snapshot: run `python3 scripts/ops/gdelt_retention_status.py` → `docs/status/generated/gdelt_retention_snapshot.json`

Related: [`GDELT_EXPANDED_FLEET.md`](GDELT_EXPANDED_FLEET.md), [`STORAGE_ARCHITECTURE.md`](STORAGE_ARCHITECTURE.md)

---

## What the ~343 GB is today (not “raw GDELT zips”)

| Layer | Path | Role | Typical size (66/102 mo) |
|-------|------|------|--------------------------|
| **Normalized expanded** | `normalized/gdelt_gkg_expanded_bulk/` | Filtered GKG per month (`asia_gkg_filtered.csv.gz`) | **~156 GB** |
| **Processed expanded** | `processed/expanded_gkg_window_*` | Scored + shock panels (duplicate pass) | **~172 GB** |
| **Asia legacy bulk** | `normalized/gdelt_gkg_asia_bulk/` | Pre-expanded Asia backfill | **~7 GB** |
| **Derived** | `derived/gdelt_crypto_overlay`, `gdelt_entity_ticker_overlay`, … | **Dataset layer** for synthesis/registry | **~1.5 GB** |
| **Raw** | `raw/` | Staging scraps | **&lt;1 GB** |

**Published datasets** (what professors/query engine should cite):

- `data/datasets/stablecoin_trust_engagement/` — weekly trust↔engagement panel (**~40 MB**)
- Factor slices under `.../factors/gdelt_*_panel_*.csv` inside that bundle

The fleet downloads raw zips to **tmp** (`SR_GDELT_TMP` on Transcend); they are **not** the 343 GB.

---

## Projected size at **102/102** (if nothing is compacted)

| Layer | Projected |
|-------|-----------|
| Normalized expanded | **~241 GB** |
| Processed expanded | **~258 GB** |
| Asia legacy + derived + raw | **~9 GB** |
| **Total** | **~508 GB** |

That is **pipeline maximum**, not the target steady state.

---

## Retention scenarios (after fleet completes)

### Scenario A — **Keep everything** (debug / re-score)

- Keep normalized + processed on Transcend (+ GDrive canonical).
- **~500 GB** local.
- Use when: still tuning scoring, re-running overlays, forensic QA.

### Scenario B — **Recommended steady state**

1. Finish **102/102** expanded queue.
2. **Rebuild overlays** on full bulk:
   ```bash
   # crypto overlay (stablecoin synthesis input)
   python3 scripts/news_shock_taxonomy/build_gdelt_crypto_overlay.py \
     --scan-dir data_lake/news_shock_taxonomy/normalized/gdelt_gkg_expanded_bulk
   # entity overlay + fused panels (if needed)
   bash scripts/run_gdelt_entity_tier3_pipeline.sh
   ```
3. **Refresh synthesis dataset** (`stablecoin_trust_engagement` with `validate_existing: false` once).
4. **rclone copy + check** canonical month dirs to GDrive `collection/news/gdelt-asia/`.
5. **Drop processed expanded** month dirs locally (scored copies — reproducible from normalized):
   ```bash
   DRY_RUN=1 bash scripts/ops/gdelt_compact_expanded_processed.sh
   bash scripts/ops/gdelt_compact_expanded_processed.sh
   ```
6. Optional later: compact **normalized** months on USB after GDrive verify (keep derived + datasets local).

| After step | Local footprint |
|------------|-----------------|
| B — drop processed only | **~250 GB** (norm + derived + asia legacy) |
| B + norm on GDrive only, hydrate on demand | **~2–10 GB** local derived + datasets |

### Scenario C — **Derived + datasets only** (minimal local)

- GDrive holds normalized canonical; local keeps `derived/` + `data/datasets/*`.
- **~2 GB** local for GDELT “products”.
- Rebuild overlays by hydrating specific months from GDrive when needed.

---

## What to **always keep**

| Asset | Why |
|-------|-----|
| `derived/gdelt_crypto_overlay` | Stablecoin / crypto news factors |
| `derived/gdelt_entity_ticker_overlay` | Entity↔ticker joins |
| `data/datasets/stablecoin_trust_engagement/` | Published research dataset |
| `derived/gdelt_expanded_queue_state/` | Manifest / provenance |
| GDrive canonical copy | Source of truth per [`STORAGE_ARCHITECTURE.md`](STORAGE_ARCHITECTURE.md) |

## What is **safe to drop** (after verify + overlay rebuild)

| Asset | Condition |
|-------|-----------|
| `processed/expanded_gkg_window_*` | Overlays rebuilt; normalized still on disk or GDrive |
| `normalized/.../month` per-month | GDrive `rclone check` OK **and** overlays rebuilt |
| `/tmp` / `SR_GDELT_TMP` staging | Always ephemeral |

## What **not** to drop yet

- Normalized expanded bulk **before** crypto/entity overlay full rebuild on 102 months.
- Anything not verified on GDrive.

---

## Checklist (run once at 102/102)

- [ ] `bash scripts/run_news_shock_gkg_expanded_fleet.sh status` → 102/102
- [ ] Full `gdelt_crypto_overlay` rebuild
- [ ] `stablecoin_trust_engagement` full publish
- [ ] GDrive sync + verify expanded months
- [ ] `python3 scripts/ops/gdelt_retention_status.py` — confirm numbers
- [ ] `DRY_RUN=1 bash scripts/ops/gdelt_compact_expanded_processed.sh` then apply
- [ ] Register/update registry panels if needed

---

## LSEG comparison (same vault philosophy)

Refinitiv harvest targets **~150–250 GB** of **curated parquet** (prices, fundamentals, master) — no duplicate processed layer. GDELT is bigger because text bulk is inherently larger; **compaction target is ~2 GB products + optional ~240 GB canonical normalized on cold storage**, not 500 GB scored duplicates.
