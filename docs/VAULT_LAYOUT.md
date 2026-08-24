# GDrive vault layout — professor vs backend

**Vault:** `gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data`

## Two trees (do not mix)

```text
Sharpe-Renaissance-data/
├── collection/              ← SHARE WITH PROFESSOR (Promise 1)
│   ├── markets/             # equities, crypto, USDT professor package, …
│   ├── news/
│   ├── official/
│   ├── reference/
│   ├── social/
│   ├── acquired/
│   ├── derived/
│   └── catalog/curated/     # human-readable dataset lists only
│
└── datacite_catalog/        ← BACKEND ONLY (operator / procurement)
    └── harvest/index_v3/    # datacite_*.jsonl.gz shards — not professor-facing
```

| Tree | Audience | Examples |
|------|----------|----------|
| `collection/` | Professor + lab | TWSE, USDT daily CSV, procured DOIs, panels |
| `datacite_catalog/` | Operator desk | Bulk DataCite metadata harvest for search/procure |

**Professor link:** share `collection/` only — never `datacite_catalog/`.

Config: `config/collection_partitions.json` (`professor_visible: false` on backend partitions).

Relocate DataCite out of `collection/` (one-time, triggers Drive re-scan):

```bash
python3 scripts/ops/relocate_datacite_to_sibling.py --dry-run
python3 scripts/ops/relocate_datacite_to_sibling.py --apply
```
