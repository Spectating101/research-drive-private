# Research Data Procurement Pipeline

> **Scope:** [`DESK_STATUS.md`](DESK_STATUS.md) — two professor promises + flywheel.  
> **This file:** technical detail for developers (modules, routes, flows).

Audit/duel/benchmark scripts were removed; do not re-add without an explicit product decision.

| Doc | Use for |
|-----|---------|
| [`DESK_STATUS.md`](DESK_STATUS.md) | **Product scope** — promises, flywheel, what to run |
| **This file** | End-to-end pipeline, indexes, jobs |
| [`research_data_mcp.md`](research_data_mcp.md) | MCP tools, start commands |
| [`research_library_backend.md`](research_library_backend.md) | HTTP `/library/*` routes |
| [`research_query_engine.md`](research_query_engine.md) | Query engine CLI, dataset backends |
| [`yzu_cluster.md`](yzu_cluster.md) | Cluster workers and job types |

**Not the live stack:** `research_data_library.html` + `research_data_library_server.py`.

---

## What this is

A **registry-driven research data desk** (separate from alpha in `scripts/alpha_*.py`).

```text
What exists?   → Search lane  (registry + partitions + indexes)
Can we get it? → Procurement lane (chat + jobs + GDrive)
```

**Why not plain chat-only tools?** The lab keeps a **dictionary** and **vault**. The model resolves against memory first; only misses trigger collect; successes are written back (flywheel). See [`DESK_STATUS.md`](DESK_STATUS.md).

---

## One stack, many surfaces

Everything wires through `scripts/research_data_mcp/bootstrap.py` → `create_stack()`:

```text
create_stack()
  ├── ResearchQueryEngine     config/research_query_registry.json
  ├── YzuOrchestrator         data_lake/yzu_cluster/jobs/jobs.sqlite3
  ├── JobService              submit / approve / tick
  ├── ResearchDataGateway     unified API (use in code: stack.gateway)
  ├── ProcurementMemory       advisor / discovery cache
  ├── CampaignStore           multi-step acquire campaigns
  └── ResearchToolHandlers    MCP + HTTP extensions
```

| Surface | Entry | Port |
|---------|-------|------|
| **Research Drive UI** | `src/main.jsx` (Vite) | proxies to `:8765` |
| **HTTP API** | `python -m scripts.research_query_engine.server` | `8765` |
| **MCP** | `scripts/run_research_data_mcp.sh` | stdio or `:8770` |
| **Chat procurement** | `POST /library/chat` | primary human UX |
| **CLI** | `library_cli.py`, `procure_download.py`, `research_query_engine_cli.py` | ops |
| **Worker** | `python -m scripts.yzu_cluster.worker` | executes queued jobs |

**Rule:** UI, MCP, and HTTP are thin clients. Business logic lives in `scripts/research_data_mcp/`, not in `server.py`.

---

## Pipeline diagram

```text
USER (chat / MCP / CLI / Composer)
                           │
                           ▼
┌───────────────────────────────────────────────────────────┐
│  LLM Orchestrator (Composer 2.5 / Gemini)                 │
│  - Decides workflows, queries registries, plans collection│
└───────────────────────────┬───────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
  search_datasets       web_search       yzu_submit_job
  (Local search)      (Tavily/DDG)       (Custom plans)
         │                  │                  │
         ▼                  ▼                  ▼
    smart_search     discover_sources     YzuOrchestrator
         │                  │                  │
         └──────────────────┼──────────────────┘
                            ▼
                        JobService → YzuExecutor
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
     collection_queue   http_manifest   scraper_run
     (queue JSON)       direct fetch    Playwright (SpectatorEngine)
              │             │             │
              └─────────────┴─────────────┘
                            ▼
              data_lake/ → archive_upload → GDrive (canonical)
                            ▼
              RegistryPromoter → research_query_registry.json
                            ▼
              CollectionFlywheel → curated index (optional)
                            ▼
              research_query_dataset() / Lab Drive UI
```

---

## Index layers (discovery)

All of these are used. They are **not** interchangeable — each answers a different question.

| Layer | Location | Local / external | Role |
|-------|----------|------------------|------|
| **Dataset registry** | `config/research_query_registry.json` | Local | What is **queryable now** (`instant` vs `metadata`) |
| **Collection queue** | `config/data_collection_queue.json` | Local | **Runnable ETL scripts** (TWSE, SEC, yfinance, …) |
| **Procurement catalog** | `CatalogService.procurement_catalog()` | Local merge | Registry + queue + pipelines + connectors for browse/advisor |
| **Curated external catalog** | `data_lake/dataset_catalog/` JSONL | Local seed | `search_catalog` metadata index |
| **DataCite live API** | `datacite_client.search` / `get_doi` | External | Global DOI dataset discovery + resolve |
| **DataCite harvest shards** | `data_lake/dataset_catalog/index_v3/{shard}/` | Local mirror | Bulk metadata harvest (`harvest_shard` jobs) |
| **Hugging Face** | `hf_catalog` | External | Dataset discovery supplement |
| **Web discovery** | Tavily + DuckDuckGo (`web_search.py`) | External | Open-web hits on index miss / acquire |
| **Semantic index** | `semantic_index.py` | Local cache | Token match over registry + queue text |
| **Domain packs** | `config/procurement_domain_packs/` | Local | Extra discovery queries / trusted portals |

**DataCite is an index** (published research datasets). **Queue is an execution registry** (your scripts). **Web browse exists** (Tavily/DDG + Playwright). Procurement uses **catalog-first**, then supplements with external indexes — not one or the other.

---

## Legacy helpers (not on the desk hot path)

The professor-facing desk is Composer + MCP. Legacy helper modules may still exist for campaign resume, bounded analysis, or older ops flows, but they do not own orchestration and should not be extended as alternate brains.

| Component | File | When | Context injected |
|-----------|------|------|------------------|
| **Desk chat** | `desk_brain.py` | Faculty UI turns | **Cursor Composer + MCP** (default) |
| **Dataset advisor** | `advisor.py` | `POST /library/advise` | Deterministic catalog ranking; Composer judges fit |
| **Research planner** | `research_planner.py` | Legacy campaign resume via `magic_procure` only | Discovery hits, probe URLs |
| **Probe analyst** | `probe_analyst.py` | Legacy probe narrative only | HTTP sample -> scrape vs collect |

Advisors are constrained: **never invent dataset ids** — only ids from provided catalog context.

Composer calls atomic MCP tools (`research_discover_search`, `yzu_submit_job`, …) — not a fixed Python tool list.

---

## Sourcing capabilities (web + collect)

| Stage | Mechanism | Job type |
|-------|-----------|----------|
| **Web search** | Tavily (`Molina-Optiplex` `TavilyBalancer`), DuckDuckGo HTML/instant | — (feeds discovery) |
| **Dataset API search** | DataCite, HF, unified search | — |
| **URL probe** | Bounded HTTP sample | `source_probe` |
| **Direct download** | `classify_url` → direct HTTP | `http_manifest` |
| **DOI collect** | resolve → repository adapters (Zenodo, OSF, …) | `http_manifest` |
| **Browser scrape** | Playwright on spectator pools | `scraper_run` (`generic_url_scrape`) |
| **Wired ETL** | Queue task command | `collection_queue_task` |
| **Bulk DataCite** | Shard harvest | `harvest_shard` |
| **Shell pipelines** | `yzu_cluster.json` pipelines | `registered_pipeline` |

`discover_with_catalog()` merges: curated catalog + `plan_sources` + `discover_sources` (Tavily, DataCite, DDG). Cached 72h (`procurement_cache`). Budget limits in `governance.py`.

---

## Execution & routing

**Job store:** `data_lake/yzu_cluster/jobs/jobs.sqlite3`

**Allowed job types** (`YzuExecutor`): `source_probe`, `http_manifest`, `registered_pipeline`, `collection_queue_task`, `collection_queue_batch`, `harvest_shard`, `archive_upload`, `scraper_run`, `bigquery_query`

**Lifecycle:**

```text
submit(plan) → pending_approval | queued
approve(id)  → queued → running (worker tick)
completed    → RegistryPromoter (if mapped) + optional GDrive archive
```

**Routing** (`config/yzu_cluster.json` `operations`): local optiplex vs `windows_lab` SSH; `prefer_local_queue`, `cluster_only`, `procurement_routes_via_cluster`.

**Sync vs async** (`procurement_fast.should_sync_wait`, `config/procurement_magic.json` `execute.sync_wait_max_minutes`):

- **Sync wait:** `http_manifest`, `source_probe`, short queue tasks (≤2 min default)
- **Async:** long ETL (e.g. TWSE ~6–8 min) — submit, return `job_id`, user checks **status**

---

## End-to-end flows

### A. Topic search — “Taiwan equity daily”

1. `POST /library/chat` → `ProcurementAgent` → tool `search_datasets`
2. `smart_search` → `catalog_search` matches queue task `twse_openapi_taiwan_market_layer`
3. User: “download #1” → `collect_dataset` → `_action_launch_job`
4. Plan: `{ job_type: "collection_queue_task", task_id: "twse_openapi_taiwan_market_layer" }`
5. Worker runs `scripts/fetch_twse_openapi_taiwan_market_layer.py`
6. Output: `data_lake/official_disclosures/taiwan_twse/`
7. On completion: may promote into registry via `procurement_registry_map.json`

### B. Topic miss — “baby growth diaper brands”

1. `catalog_search` weak → full `smart_search` (DataCite + HF + registry)
2. Still weak → `discover_with_catalog` (Tavily/DDG)
3. Ranked candidates with `collect_via: datacite` | `huggingface` | `queue` | `http_manifest`
4. User picks → collect via `equipment_bridge`

### C. DOI in message

1. `deterministic_plan` or `collect_doi` tool
2. `plan_datacite_collect` → `resolve_doi` → `build_http_manifest_plan`
3. Download to `data_lake/procured/{repository}/`
4. Pin + registry promotion

### D. Direct URL

1. `plan_immediate_collect` → `scrape_plan.classify_url`
2. `direct_http` → `http_manifest`; else → `generic_url_scrape` (Playwright)

### E. “Source this for me” (inaccessible / unknown)

1. Chat → `smart_search` / advisor
2. Index miss → `discover_with_catalog` + `ResearchPlanner`
3. Auto-probe top URLs → recommendations → `approve_collect`
4. User **approve** → collect jobs → flywheel write-back

---

## Config files

| File | Role |
|------|------|
| `research_query_registry.json` | Queryable datasets |
| `data_collection_queue.json` | Runnable collection tasks |
| `yzu_cluster.json` | Pools, pipelines, spectator scripts, routing |
| `procurement_magic.json` | Auto-approve, sync-wait, discovery on miss, cache TTLs |
| `procurement_registry_map.json` | Job completion → registry upsert rules |
| `procurement_governance.json` | Legacy magic/Tavily budgets per campaign run |
| `procurement_domain_packs/` | Domain discovery hints |

---

## Outputs & delivery

| Artifact | Typical path |
|----------|----------------|
| HTTP / DOI procured | `data_lake/procured/` |
| Queue task output | per-task `output_hint` in queue JSON |
| Scrapes | `data_lake/spectator_engine/scrapes/{job_id}/` |
| Job logs | `data_lake/yzu_cluster/jobs/{job_id}/` |
| Cold archive | GDrive via `archive_upload` when enabled |
| Chat state | `data_lake/procurement_memory/chat_sessions.sqlite3` |
| Pins / reuse | `data_lake/procurement_memory/` (DOI reuse) |

---

## Search lane (query what you have)

Use **before** procuring when data may already be instant:

```text
1. research_library_overview / GET /library/overview
2. research_plan_sources(q=...) or procurement_catalog
3. research_query_dataset(...) on analysis_readiness=instant
4. Only then: chat procure / plan_collect / queue collect
```

See [`research_query_engine.md`](research_query_engine.md) for CLI examples.

---

## Tests & smoke

```bash
.venv/bin/pytest tests/test_procurement_search.py -q
.venv/bin/python scripts/research_data_mcp/library_smoke.py
```

See [`DESK_STATUS.md`](DESK_STATUS.md) for scope — do not re-add audit/benchmark scripts.

---

## Module map (`scripts/research_data_mcp/`)

| Module | Role |
|--------|------|
| `bootstrap.py` | `create_stack()` |
| `gateway.py` | Facade (routing to search, catalog, and jobs) |
| `procurement_chat.py` | Chat orchestration and progress updates |
| `procurement_search.py` | `smart_search` and relevance ranking |
| `procurement_fast.py` | `local_search` and catalog-first matches |
| `magic_procure.py` | Campaign resume/approve only — not HTTP/chat |
| `catalog_index.py` | Token scoring over queue/pipelines/shards |
| `unified_search.py` | Registry + DataCite + HF merge |
| `web_search.py` | Tavily & DDG web discovery |
| `datacite_repository.py` | DOI resolve + manifest plans |
| `scrape_plan.py` | URL classify and scrape layout decisions |
| `jobs.py` | `JobService` wrapper |
| `registry_promotion.py` | Post-job registry promotion |
| `procurement_delivery.py` | Worker ticks & outcome formatting |
| `advisor.py` | Deterministic dataset advisor; Composer judges fit |
| `research_planner.py` | Index-miss research plans (legacy) |
| `http_router.py` | HTTP `/library/*` API routing |

---

## Known debt (honest)

- Three HTTP namespaces (`/library` canonical; `/yzu`, `/agent` legacy)
- DataCite harvest shards: light scan in `local_search`; full FTS index still TODO
- Tavily depends on Molina-Optiplex keys; parallel path falls back to DDG
- Legacy `research_data_library.html` still in repo — do not use for integration

---

## Quick start

```bash
# HTTP + UI
scripts/run_yzu_cluster.sh

# MCP
scripts/run_research_data_mcp.sh

# Python
from scripts.research_data_mcp.bootstrap import create_stack
gw = create_stack().gateway
gw.procurement_chat(session_id, "I need Taiwan equity daily data")
```
