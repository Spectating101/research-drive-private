# YZU Cluster — Ideal Design, References & Examples

This document is the **design north star**. Implementation status lives in [`yzu_cluster.md`](yzu_cluster.md). Code map: `config/yzu_cluster.json`, `scripts/yzu_cluster/`, `scripts/research_query_engine/`.

Current production rule: **Cursor Composer + MCP is the only desk brain**. Older references to agent-side planning are retained here only as historical design context.

---

## 1. What we are building (one sentence)

**YZU Cluster** is a **data procurement control plane**: a single place to discover sources, approve collection plans, dispatch work to existing cluster engines, stage results locally, archive to cold storage, and register datasets for query — **not** a Google Drive clone and **not** the alpha-trading pipeline.

---

## 2. What we are *not* building

| Anti-pattern | Why we reject it |
|--------------|------------------|
| Full GDrive/Dropbox UI | Cold archive works via `rclone copy`; discovery belongs in **registry + metadata**, not folder browsing on 5TB |
| New scraper framework | **Spectator** (Molina) + `remote_collect.py` already exist; YZU only **dispatches** them |
| Another long-running script per pipeline | DataCite, GDELT, collection queue each had their own watchdog; YZU **unifies the job model** |
| Autonomous “download everything” agent | Every procure path needs **explicit approval** (or pre-approved schedule); probes first for unknown URLs |
| IHSG / live alpha | Out of scope unless it shares infra (prices, news panels) as **registered datasets** |

---

## 3. Reference models (what we’re stealing from)

These are the **mental references** — not dependencies to install.

### A. Research library (catalog + query)

**Reference:** `research_query_registry.json` + `ResearchQueryEngine` (`:8765`)

- Separates *“what exists?”* from *“can I analyze it now?”*
- Each dataset has `backend`, `access_shape`, `analysis_readiness`, `limitations`
- **YZU role:** after procurement completes, **promote** a new entry here (or update `local_root` / `local_path`)

**Example in repo:** `gdelt_asia_daily_country_panel` — local derived tables, instant readiness, join keys documented.

### B. Procurement workbench (probe → approve → collect)

**Reference:** `scripts/research_query_engine/procurement.py` + `agent.py`

- `source_probe`: bounded HTTP fetch, robots-aware, connector store
- `http_manifest`: known direct file URLs → Windows workers
- Composer or the UI submits explicit JSON **plans**, never shell
- **YZU role:** Composer is the planner; orchestrator is the executor

**Example flow:** User pastes a CSV URL → probe → if direct file → `http_manifest` with 2–4 shards on windows_lab.

### C. Cluster render-farm (Tailscale workers)

**Reference:** Windows inventory CSV + `cluster_agent/remote_collect.py`

- 4× ASUS nodes on Tailscale; SSH as `user@<ip>`
- Work is **sharded** (manifest JSON per shard, zip artifact back)
- **YZU role:** pool `windows_lab` for HTTP harvest + remote DataCite shard **control** (restart/status)

**Example in repo:** DataCite y2025 shards on `100.102.0.84`, `100.83.34.59`; local q3 on optiplex (`datacite_y2025_parallel_shards.list`).

### D. Batch ops queue (conservative unattended tasks)

**Reference:** `config/data_collection_queue.json` + `run_data_collection_queue.py`

- Only `enabled=true` and `credential_required=false`
- SEC tickers, yfinance panels, macro baseline — land under `data_lake/`
- **YZU role:** expose as `collection_queue_task` / `collection_queue_batch` jobs (same commands, unified queue)

**Example tasks:** `sec_company_tickers`, `yfinance_global_drilldown_10y`, `public_macro_market_baseline`.

### E. Cold archive tier (GDrive as tape, not UI)

**Reference:** `rclone copy` / `rclone check` across pipelines (GDELT upload queue, DataCite shard upload, reclaim scripts)

- **Never** `rclone sync` (local missing must not delete Drive)
- Upload → verify → delete local blob (`reclaim_gdelt_gkg_local_after_drive_ok.sh` pattern)
- Root: `gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data`
- **YZU role:** `archive_upload` job type; dashboard shows disk + upload backlog, not Drive file tree

### F. Spectator scrape host (Puppeteer sidecar)

**Reference:** Molina-Optiplex `scripts/spectator_*.mjs`, `config/spectator_remote_paths.json`

- Remote Linux host `spectator` / `100.96.62.97`; True-Oracle SQLite DBs
- Used when HTTP/API is insufficient (JS boards, CDP)
- **YZU role:** `scraper_run` with **allowlisted** scripts in `yzu_cluster.json` → `spectator_scripts`

**Example scripts:** `spectator_scrape_cake.mjs`, `spectator_scrape_yourator.mjs`.

### G. Guarded remote query (BigQuery pilot)

**Reference:** `ethereum_usdt_transfers` in registry + `scripts/usdt_catalogue/`

- `access_shape`: `remote_bigquery_with_local_rpc_preview`
- Dry-run byte budget before execute; local RPC for no-GCP proof
- **YZU role (target):** job type `bigquery_template_run` (not wired in executor yet); status tile in UI; MCP already has `bigquery_dry_run`

### H. Agent MCP surface (Cursor / Claude)

**Reference:** `scripts/research_data_mcp/` — same gateway as HTTP API

- Search → plan → query → procure
- **YZU role:** one backend (`:8765`); MCP tools call same orchestrator as UI

---

## 4. Ideal architecture (layers)

```text
┌─────────────────────────────────────────────────────────────────┐
│  Experience layer                                                │
│  • Vite UI (:5178) — dashboard, library, discover, jobs          │
│  • Composer desk chat — plan + approve                           │
│  • MCP / CLI — automation                                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  Control plane (optiplex)                                        │
│  • YzuOrchestrator — SQLite job queue, validation, schedules     │
│  • YzuClusterAPI — live acquisitions (DataCite, GDELT, queue)    │
│  • ResearchQueryEngine — registry query + research_source_plan   │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ windows_lab   │   │ optiplex      │   │ spectator     │
│ SSH + PS      │   │ systemd, local│   │ SSH + node    │
│ HTTP collect  │   │ shards, queue │   │ Puppeteer     │
│ DataCite shard│   │ GDELT fleet   │   │ SQLite scrape │
└───────┬───────┘   └───────┬───────┘   └───────┬───────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
                 ┌─────────────────────┐
                 │  Staging             │
                 │  data_lake/          │
                 │  (disk guards)       │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │  Cold archive        │
                 │  gdrive:Machine_...  │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │  Registry            │
                 │  research_query_     │
                 │  registry.json       │
                 └─────────────────────┘
```

### Design principles

1. **One job model** — every procure action is `{ job_type, plan, status, events, result }` in SQLite.
2. **Honest UI** — dashboard rows come from probes (DataCite shards, GDELT ok-months, queue lock), not hardcoded demos.
3. **Fast status, slow probes** — shard SSH cached ~90s; live probe on demand (Workers tab).
4. **Approval by default** — agent creates `pending_approval`; schedules may `auto_approve` for known-safe batch jobs.
5. **Register last** — procurement success should eventually **write registry metadata** (today: manual / partial).

---

## 5. The six-step researcher loop (ideal)

| Step | User action | System | Example in this repo |
|------|-------------|--------|----------------------|
| **1. Discover** | Search library / ask agent | `research_source_plan`, registry, DataCite catalogue | “asia equity news shock dataset” → 25 routes |
| **2. Plan** | Composer or UI builds plan | MCP JSON plan or quick-launch chip | `collection_queue_task` for `sec_company_tickers` |
| **3. Approve** | Click Launch / CLI approve | `pending_approval` → `queued` | Job `76a5f23a25cf` probe example.com |
| **4. Procure** | Worker executes | Executor picks pool | Windows shard download zip; local DataCite restart |
| **5. Stage + archive** | Automatic or follow-up job | `data_lake/` then `archive_upload` | GDELT month → GDrive → local reclaim |
| **6. Register** | Promote dataset | Update `research_query_registry.json` | Add row when `yfinance_global_drilldown_10y.csv` ready |

Steps 1–4 are **implemented**. Steps 5–6 are **partial** (pipelines archive ad hoc; registry updates manual).

---

## 6. Worker pools (ideal responsibilities)

| Pool | Hosts | Ideal workloads | Do **not** use for |
|------|-------|-----------------|-------------------|
| `optiplex` | Controller | Queue runner, local DataCite q3, GDELT score/fleet, agent API | Heavy browser scrape |
| `windows_lab` | 4× Tailscale | `http_manifest`, DataCite shard harvest (long-running), GDELT fetch shards | Interactive UI |
| `spectator` | `100.96.62.97` | `scraper_run` allowlisted `.mjs` / board refresh | Bulk DOI metadata |
| `public_http` | (logical) | Any joined node via `remote_collect.py` | Authenticated APIs without connector |

---

## 7. Job types (ideal contract)

Each plan is JSON stored in `jobs.sqlite3`. Executor routes by `job_type`.

| `job_type` | Purpose | Example plan |
|------------|---------|--------------|
| `source_probe` | Unknown URL triage | `{"job_type":"source_probe","url":"https://…","launchable":true}` |
| `http_manifest` | Direct file URLs | `{"job_type":"http_manifest","items":[{"url":"https://…/file.csv"}],"shards":2}` |
| `registered_pipeline` | Long-running fleet | `{"job_type":"registered_pipeline","pipeline_id":"gdelt_fleet"}` |
| `collection_queue_task` | One public queue task | `{"job_type":"collection_queue_task","task_id":"sec_company_tickers"}` |
| `collection_queue_batch` | Full enabled queue | `{"job_type":"collection_queue_batch","timeout_seconds":14400}` |
| `harvest_shard` | DataCite **control** (not full harvest in UI thread) | `{"job_type":"harvest_shard","shard":"y2025_q2","action":"restart"}` |
| `archive_upload` | Staging → GDrive | `{"job_type":"archive_upload","local_path":"data_lake/…","verify":true}` |
| `scraper_run` | Spectator allowlist | `{"job_type":"scraper_run","script_key":"cake_board"}` |
| `bigquery_template_run` | **Target** — USDT pilot | `{"job_type":"bigquery_template_run","template":"daily_recent","dry_run":true}` |

Actions for `harvest_shard`: `restart` | `status` | `pull_meta` (remote heartbeat); local also `systemctl --user restart datacite-local-{shard}`.

---

## 8. Concrete end-to-end examples

### Example A — Professor asks: “Get SEC tickers and latest submissions”

```text
Discover  → research_source_plan / library shows sec_* datasets
Plan      → collection_queue_task sec_company_tickers then sec_sp500_submissions
Approve   → Jobs tab → Approve (or auto_approve schedule)
Procure   → optiplex runs .venv python scripts/sec_fetch_*.py
Stage     → data_lake/sec/company_tickers.json, submissions/
Register  → (manual today) ensure registry paths match
```

### Example B — DataCite y2025 q2 stuck

```text
Dashboard → DataCite row shows q2 @ 100.83.34.59 at 93%
Inspector → Restart y2025_q2
Job       → harvest_shard restart → SSH powershell restart_datacite_shard_clean.ps1
Archive   → ongoing via shard harvest scripts + rclone (not one UI job)
```

### Example C — New external CSV URL

```text
Agent chat → “collect https://example.org/data/prices.csv”
Probe      → source_probe → connector candidate
Plan       → http_manifest if probe shows direct file
Procure    → 2 Windows workers → artifacts in data_lake/agent_jobs/{id}/
Archive    → archive_upload job (follow-up)
Register   → new registry row or update procurement_source_registry
```

### Example D — USDT on-chain flows (BigQuery)

```text
Discover  → dataset_id ethereum_usdt_transfers (dry_run_before_execution)
Plan      → bigquery_dry_run via MCP (byte estimate)
Procure   → (target) bigquery_template_run with billing guard
Stage     → data/usdt_catalogue/pilot/
Query     → research_query_engine on registered backend
```

### Example E — Taiwan job boards (Spectator)

```text
Plan      → scraper_run script_key cake_board
Procure   → SSH spectator → node scripts/spectator_scrape_cake.mjs
Pull      → optional pull_paths to data_lake/yzu_cluster/scrapes/
Register  → link to tw_jobs / external catalogue (future)
```

---

## 9. UI ideal (Drive-*like* comfort, honest data)

| View | Ideal behavior | Data source |
|------|----------------|-------------|
| **Dashboard** | Acquisition cards with real % / disk / fleet | `/yzu/status`, `/yzu/acquisitions` |
| **Discover** | Source planner for new questions | `/query/research_source_plan` |
| **Library** | Registry browse + preview rows | `/datasets`, `/query/{id}` |
| **Jobs** | Unified queue, quick-launch, events | `/yzu/jobs`, `/yzu/queue/tasks` |
| **Workers** | Live SSH probe optional | `/yzu/workers?live=1` |
| **Inspector** | Agent + shard restart for DataCite | `/agent/chat`, `/yzu/jobs` POST |

**Not in v1 ideal:** full GDrive tree browser, inline SQL editor, embedding search (noted in registry limitations).

---

## 10. Storage & ops rules (non-negotiable)

```text
Local (data_lake/)     = hot staging + query panels; disk guard on optiplex
GDrive                 = cold verified archive only
Delete local           = only after rclone check matches (reclaim scripts)
DataCite               = ~129M records target; y2025 = 4 quarterly shards
GDELT Asia GKG         = 2018–2023 monthly windows; fleet + upload queue
Collection queue       = public tasks only unless operator adds credentials elsewhere
```

---

## 11. Current vs ideal (honest gap list)

| Area | Current | Ideal |
|------|---------|-------|
| Job queue | ✅ Unified SQLite + worker | Retry policy, priority lanes |
| Agent | ✅ Plans → same queue | Broader prompt for new job types |
| DataCite / GDELT status | ✅ Live with cache | Fix watchdog list vs real shard hosts |
| Collection queue | ✅ Task + batch jobs | Enable daily schedule when ready |
| Spectator | ⚠️ SSH dispatch stub | Pull paths, health probe, deps on spectator |
| BigQuery USDT | ❌ Not in executor | `bigquery_template_run` + UI status |
| Register step | ❌ Manual | Job completion hook → registry promotion draft |
| GDrive library | ❌ By design | Registry + `local_root` / `drive_root` pointers only |
| MCP parity | ⚠️ Partial | All `/yzu/jobs` ops as MCP tools |

---

## 12. File map (what to read)

| Concern | Path |
|---------|------|
| Cluster config | `config/yzu_cluster.json` |
| Dataset catalogue | `config/research_query_registry.json` |
| Public task list | `config/data_collection_queue.json` |
| DataCite shards | `scripts/data_catalog/datacite_y2025_parallel_shards.list` |
| Orchestrator | `scripts/yzu_cluster/orchestrator.py` |
| Executor | `scripts/yzu_cluster/executor.py` |
| HTTP API | `scripts/research_query_engine/server.py` |
| Agent | `scripts/research_query_engine/agent.py` |
| Procurement probes | `scripts/research_query_engine/procurement.py` |
| Windows collect | `scripts/cluster_agent/remote_collect.py` |
| MCP gateway | `scripts/research_data_mcp/gateway.py` |
| USDT BigQuery | `scripts/usdt_catalogue/`, `sql/bigquery/usdt/` |
| Spectator | `../Molina-Optiplex/scripts/spectator_*.mjs` |
| UI | `src/main.jsx` |
| Launch | `scripts/run_yzu_cluster.sh` |

---

## 13. Success criteria (how we know the design is “done”)

1. Researcher can go **Discover → Jobs → staged files** without touching raw scripts.
2. Dashboard numbers match SSH probes / checkpoint files (no fake rows).
3. Agent, UI, CLI, and MCP create the **same job records**.
4. Long-running harvests stay in **systemd/fleet**; UI only **controls** and **monitors**.
5. New dataset appears in **registry** with correct `local_root` after procure (automated or one-click promote).
6. Disk pressure triggers **archive + reclaim**, visible on dashboard.

---

## 14. Recommended build order (from here)

1. **Ops truth** — sync DataCite watchdog/worker lists with `datacite_y2025_parallel_shards.list`.
2. **Register hook** — on `collection_queue_task` / `http_manifest` complete, emit registry promotion JSON for review.
3. **BigQuery job type** — wire `usdt_catalogue` dry-run + capped execute into orchestrator.
4. **Spectator hardening** — health check, allowlist only, standard pull to `data_lake/yzu_cluster/scrapes/`.
5. **MCP tools** — `yzu_submit_job`, `yzu_list_acquisitions` mirroring HTTP.
6. **Schedule** — enable `public_collection_daily` after one clean batch run.

This order finishes the **procurement network** before any new UI polish.
