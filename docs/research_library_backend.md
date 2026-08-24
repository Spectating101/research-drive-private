# Research Library — Backend API

HTTP routes and Python module map. UI and MCP are thin clients over the same stack.

**Architecture (read first):** [`PROCUREMENT_PIPELINE.md`](PROCUREMENT_PIPELINE.md)

## Honest assessment (what is / is not clean)

### Solid
- **One job store** — `JobService` → `YzuOrchestrator` → SQLite; HTTP `/library/jobs` is canonical (POST `/yzu/jobs` remains for cluster submit scripts).
- **One registry engine** — `create_stack()` passes a single `ResearchQueryEngine` into both orchestrator and `ResearchDataGateway`.
- **Router is table-driven** — `http_router.py` maps paths → handlers; no business logic in `server.py`.
- **MCP-first** — `ResearchToolHandlers` is the equipment surface; HTTP `/library/*` and `/library/extensions/*` delegate to the same gateway/tools.

### Still rough (known debt)
| Issue | Status |
|-------|--------|
| **`ResearchDataGateway` size** | Facade delegates to search, catalog, jobs; further split optional. |
| **Search trio** | `/library/discover` (local), `/library/search` (unified), `/library/discover/web` (Tavily) — intentional; see table below. |
| **`/yzu/*` cluster ops** | Status, workers, queue, POST submit — legacy prefix with `_deprecated` hint; prefer `/library/jobs` for list/get/approve. |
| **Registry promotion** | `RegistryPromoter` runs on job completion; reloads registry via gateway `SearchService`. |

Removed HTTP routes (404): entire `/agent/*` namespace, `GET /yzu/jobs` duplicates.  
Removed gateway stubs: `assist()`, `magic_procure()` (use MCP `yzu_submit_job` / `POST /library/chat`).

### Search endpoints (when to call which)

| Route | Use |
|-------|-----|
| `GET /library/discover` | Local vault index only — fast Browse step 1 |
| `GET /library/search` | Unified layers (registry + DataCite + HF + scrape); pass `skip_discover=1` after discover |
| `GET /library/discover/web` | External Tavily discovery only |

MCP equivalents: `research_discover_search`, `research_unified_search`, `research_web_discover`.

### Recommended client surface
Use **`/library/*`** for faculty UI and new integrations. Use **`/yzu/*`** only for cluster status/workers/queue. Use **MCP tools** for Composer agents.

Full pipeline, index layers, and flows: [`PROCUREMENT_PIPELINE.md`](PROCUREMENT_PIPELINE.md).

### Module map (summary)

```text
bootstrap.py          → create_stack() + registry promotion hook
jobs.py               → JobService (submit, approve, list, archive_plan)
gateway.py            → ResearchDataGateway (thin facade + PassivePlanner shim)
desk_brain.py         → Composer + MCP (faculty chat brain)
search.py             → SearchService (datasets, query, overview, ops)
catalog.py            → CatalogService (procurement_catalog)
registry_promotion.py → RegistryPromoter (queue task → registry)
tool_handlers.py      → ResearchToolHandlers (MCP + HTTP extensions)
datacite_client.py    → DataCite REST
bigquery_client.py    → guarded BigQuery reads
mcp_register.py       → MCP tool registration from handlers
advisor.py            → DatasetAdvisor (deterministic catalog ranking)
http_router.py        → path → handler table (+ legacy _deprecated)
server.py             → thin MCP transport (registers shared handlers)
```


```text
create_stack(repo_root)
  ├── ResearchQueryEngine      config/research_query_registry.json
  ├── YzuOrchestrator          data_lake/yzu_cluster/jobs/jobs.sqlite3
  ├── ResearchDataGateway      unified library API (use this in code)
  └── YzuClusterAPI            live cluster status / acquisitions
```

**Entry point for Python:**

```python
from scripts.research_data_mcp import create_stack, ResearchDataGateway

stack = create_stack()          # or create_stack("/path/to/repo")
gw = stack.gateway              # preferred handle

catalog = gw.procurement_catalog(q="sec")
advice = gw.advise_datasets("SEC filings", current_dataset_id="gdelt_asia_daily_country_panel")
job = gw.submit_yzu_job({"job_type": "collection_queue_task", "task_id": "sec_company_tickers", "launchable": True})
```

## HTTP server

```bash
# Same process as YZU cluster launcher
scripts/run_yzu_cluster.sh

# Or query engine only
python -m scripts.research_query_engine.server --port 8765
```

Routing is implemented in `scripts/research_data_mcp/http_router.py` — no business logic in the HTTP handler.

### `/library/*` — preferred API namespace

| Method | Path | Gateway method |
|--------|------|----------------|
| GET | `/library/catalog?q=` | `procurement_catalog` |
| GET | `/library/overview` | `library_overview` |
| GET | `/library/ops` | `ops_status` |
| POST | `/library/advise` | `advise_datasets` |
| POST | `/library/chat` | `procurement_chat` (Composer + MCP) |
| POST | `/library/chat/stream` | streaming chat (Vite UI) |
| GET | `/library/jobs` | `list_yzu_jobs` |
| GET | `/library/jobs/{id}` | `get_yzu_job` |
| POST | `/library/jobs` | `submit_yzu_job` |
| POST | `/library/jobs/{id}/approve` | `approve_yzu_job` |
| POST | `/library/jobs/{id}/cancel` | `cancel_yzu_job` |
| POST | `/library/archive` | `archive_to_gdrive` |
| GET | `/library/extensions/tools` | MCP tool catalog |
| GET | `/library/extensions/datacite/search` | `datacite_search` |
| GET | `/library/extensions/bigquery/status` | `bigquery_status` |
| POST | `/library/extensions/bigquery/dry-run` | `bigquery_dry_run` |

### Legacy cluster routes (not job list duplicates)

| Path | Notes |
|------|-------|
| `POST /yzu/jobs` | Cluster script submit alias → same store as `POST /library/jobs` |
| `GET /yzu/status`, `/yzu/workers`, … | Cluster ops only |
| `/datasets`, `/query/{id}` | Registry query — all via `gateway.list_datasets` / `query_dataset` |

## MCP

```bash
scripts/run_research_data_mcp.sh
```

MCP tools call the same `ResearchDataGateway` instance created via `create_stack()`.

## CLI & smoke

```bash
# Gateway smoke (browse → advise → job → optional gdrive)
python scripts/research_data_mcp/library_smoke.py

# API smoke (needs :8765)
python scripts/procurement_ops_smoke.py

# YZU cluster integration (workers, pools)
python scripts/yzu_cluster/integration_audit.py
```

## Tests

```bash
.venv/bin/pytest tests/test_research_library_backend.py tests/test_research_data_gateway.py tests/test_yzu_orchestrator.py tests/test_research_tool_handlers.py -q
```

## Job lifecycle (library)

```text
submit_yzu_job(plan) → pending_approval | queued
approve_yzu_job(id)  → queued → running (worker process)
get_yzu_job(id)      → completed | failed (+ registry_promotion in result when mapped)
archive_to_gdrive()  → archive_upload job → rclone → GDrive
```

On completion, `RegistryPromoter` checks `config/procurement_registry_map.json` for the queue task id(s), upserts into `research_query_registry.json` if the artifact exists, and reloads the in-memory engine.

Worker: `python -m scripts.yzu_cluster.worker` (started by `run_yzu_cluster.sh`).
