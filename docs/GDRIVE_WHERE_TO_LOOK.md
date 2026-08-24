# Google Drive — where to look

**Promise 1:** Give the professor **one folder link** — everything lives under `collection/`.

---

## The one link to share

When migration is complete, share **only this folder**:

```
My Drive → Machine_Archive → molina_workbench → Sharpe-Renaissance-data → collection
```

In Google Drive: right-click **`collection`** → **Share** → copy link.  
That single link covers markets, news, official data, catalog, procured downloads, etc.

**Do not** share legacy root folders (`news_shock_taxonomy`, `market_data`, …) — they are removed as migration finishes.

**Check if ready:**

```bash
python3 scripts/ops/verify_gdrive_vault.py
```

Exit `0` = no legacy folders at vault root; safe to share `collection/`.

**Finish migration (if verify fails):**

```bash
python3 scripts/ops/migrate_gdrive_collection_layout.py --all
# runs in background; log:
tail -f data_lake/collection/_index/migration/nohup_migrate.log
```

---

## 1. Open this path in the browser

```
My Drive
 └── Machine_Archive
      └── molina_workbench
           └── Sharpe-Renaissance-data    ← you are here
```

**First file to open:** `START_HERE.md` (at that folder root).  
If it’s missing, publish it:

```bash
python scripts/ops/publish_gdrive_partition_nav.py --upload
```

---

## 2. What you see now (after migration)

Open **`collection/`** — everything lives under one tree:

```
Sharpe-Renaissance-data/
├── START_HERE.md          ← open this first
├── PARTITION_MAP.json
└── collection/
    ├── markets/
    ├── news/
    ├── official/
    ├── reference/
    ├── social/
    ├── catalog/
    ├── acquired/
    ├── derived/
    └── ops/
```

Legacy flat folders (`news_shock_taxonomy`, `market_data`, …) are **removed after migrate** completes.

**Migrate / refresh:**

```bash
python3 scripts/ops/migrate_gdrive_collection_layout.py --all
python3 scripts/ops/publish_gdrive_partition_nav.py --upload
```

---

## 3. What each top-level folder is (cheat sheet)

| Folder you see on Drive | What it is | Future clean path |
|-------------------------|------------|-------------------|
| `news_shock_taxonomy` | GDELT Asia news (GKG) — **largest** (~156 GiB) | `collection/news/gdelt-asia` |
| `dataset_catalog` | Curated lists + `datacite/index_v3` harvest shards (~32 GiB in index_v3) | `collection/catalog/…` |
| `market_data` | Asia equity universes / yfinance panels | `collection/markets/equities-asia` |
| `crypto_landscape` | Crypto landscape snapshots | `collection/markets/crypto-landscape` |
| `official_disclosures` | TWSE and exchange disclosures | `collection/official/exchange-disclosures` |
| `official_macro_asia` | Public macro baseline packs | `collection/official/macro-asia` |
| `entity_mapping` | Asia entity / ticker mapping | `collection/reference/entity-mapping-asia` |
| `sec` | SEC EDGAR reference (e.g. company tickers) | `collection/reference/sec-edgar` |
| `social_reddit` | Reddit ingest archive | `collection/social/reddit` |
| `research_panels` | Derived analysis panels | `collection/derived/research-panels` |
| `research_models` | Saved model trial artifacts | `collection/derived/research-models` |
| `procured` | One-off DOI / chat downloads | `collection/acquired/procured` |
| `manifests` | Pipeline / queue operator JSON | `collection/ops/pipeline-manifests` |
| `collection_queue` | New per-task job archives (e.g. SEC tickers) | ops (migration TBD) |

---

## 4. Three places the “partition” exists

```text
┌─────────────────────────────────────────────────────────────┐
│  A. Google Drive (browser) — LEGACY folder names at root    │
│     gdrive:Machine_Archive/.../Sharpe-Renaissance-data      │
└───────────────────────────────┬─────────────────────────────┘
                                │ same bytes, different labels
┌───────────────────────────────▼─────────────────────────────┐
│  B. Repo config — semantics (titles, descriptions, map)    │
│     config/collection_partitions.json                       │
└───────────────────────────────┬─────────────────────────────┘
                                │ scaffold + symlinks
┌───────────────────────────────▼─────────────────────────────┐
│  C. Local navigation tree — CLEAN names (no extra copy)     │
│     data_lake/collection/{domain}/{partition}/meta.json     │
└─────────────────────────────────────────────────────────────┘
```

- **Professor browsing Drive** → table in §3 or `START_HERE.md` on Drive.
- **Lab UI / registry** → reads `collection_partitions.json` + registry.
- **Operator on optiplex** → `data_lake/collection/` with `STORAGE` symlinks to USB cache.

---

## 5. How to build / refresh the partition map (operator)

**Regenerate local navigation tree** (meta.json per partition, INDEX.json):

```bash
python scripts/data_catalog/build_collection_directory.py --link-storage
```

**Inventory Drive vs local** (sizes, manifest):

```bash
python scripts/data_catalog/inventory_canonical_collection.py --quick --pretty
```

**Publish human map to Drive root**:

```bash
python scripts/ops/publish_gdrive_partition_nav.py --upload
```

**Physical migration** (when ready — copies bytes, long-running):

```bash
# Example for one partition; verify with rclone check before deleting legacy
rclone copy \
  "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/sec" \
  "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/reference/sec-edgar" \
  --checksum
```

Full target layout: `docs/COLLECTION_ARCHITECTURE.md` §2.

---

## 6. Quick commands

```bash
# List vault root on Drive
rclone lsd "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data"

# Local partition tree
ls data_lake/collection/

# Storage tier status
python scripts/ops/storage_status.py --pretty
```
