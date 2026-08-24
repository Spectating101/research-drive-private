# Storage architecture

See also: [`COLLECTION_ARCHITECTURE.md`](COLLECTION_ARCHITECTURE.md) (partition map, DataCite scale, target GDrive tree).

Three tiers keep GDrive canonical, USB for local analysis, and NVMe for the desk.

## Tiers

| Tier | Location | Role |
|------|----------|------|
| **Canonical** | `gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data` | Source of truth. Pipeline job is **done** only after `rclone copy` + `rclone check`. |
| **Cache** | Transcend USB (`RESEARCH_BULK_ROOT`, symlinked `data_lake/*`) | Local bulk for analysis when plugged in. Lazy-hydrated from canonical. Staging gz may be compacted after verify. |
| **Hot** | NVMe `data_lake/` (non-symlinked paths) | Alpha panel, SQLite, procured files, active `research_panels/`, SEC caches. |

Config: `config/storage_tiers.json`

## Data flow (drive-first)

```text
Collect / scrape / procure
    → ephemeral local staging (data_lake/procured, spectator_engine/scrapes)
    → rclone copy + verify → collection/{partition}/ on GDrive
    → compact local staging (optional)
    → job marked complete only after Drive verify

Analyze (Lab Drive, query engine, trials)
    → hydrate from GDrive partition when bytes needed on desk
    → collection_hydrate job or read via canonical_remote in registry
```

## What avoids redundancy

- **Not redundant:** GDrive + USB both holding the same month — canonical + local cache.
- **Redundant (avoid):** Same bulk on NVMe and USB — bulk_subdirs live on USB only.
- **Redundant (avoid):** Keeping huge staging gz on USB forever when GDrive verified and no analysis planned — run compact.

## Operator commands

```bash
# Full tier status (API uses same payload)
.venv/bin/python scripts/ops/storage_status.py --pretty

# One-time USB setup (symlinks + .env.local)
bash scripts/ops/setup_bulk_storage.sh

# Compact verified staging on cache only (GDrive must match)
DRY_RUN=1 bash scripts/ops/storage_compact_verified_cache.sh
bash scripts/ops/storage_compact_verified_cache.sh

# Hydrate cache from canonical for entity / overlay work
.venv/bin/python scripts/news_shock_taxonomy/expand_gdelt_entity_article_coverage.py
```

## Code map

| Module | Purpose |
|--------|---------|
| `scripts/research_data_mcp/storage_tiers.py` | Tier rules, path resolution, health payload |
| `scripts/research_data_mcp/data_paths.py` | Bulk root detection, delegates resolve |
| `scripts/research_data_mcp/storage_policy.py` | Agent/procurement policy wrapper |
| `GET /health` → `desk.storage_tiers` | Research Drive desk health |

## Pipeline defaults

- `LOCAL_RETENTION=compact` after GDrive verify when `retention_after_canonical_verify` is `compact_staging_only` (default).
- Use `LOCAL_RETENTION=keep` on cache when running entity overlays or multi-pass analysis on the same month.
- Disk guard (`guard_gdelt_disk_headroom.sh`) targets **NVMe only** when cache is mounted (lower threshold).
