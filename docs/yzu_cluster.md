# YZU Cluster — Data Sourcing & Procurement Network

**Design spec (ideal architecture, references, examples):** [`yzu_cluster_design.md`](yzu_cluster_design.md)  
**This file:** implementation status and file pointers.

## Launch (production desk)

Faculty-facing **Research Desk** — one URL, chat procurement, cluster-backed collection.

```bash
# Development (Vite HMR + API proxy)
scripts/run_yzu_cluster.sh

# Production (built UI served by API on one port)
scripts/run_yzu_cluster_prod.sh
# → http://127.0.0.1:8765/

# Persistent (systemd user units — builds dist/ with --prod)
bash scripts/install_yzu_cluster_systemd_user.sh --prod
```

| Requirement | Command / check |
|-------------|-----------------|
| API + UI | `curl -s http://127.0.0.1:8765/health` |
| Worker | `systemctl --user status yzu-cluster-worker` |
| Smoke | `.venv/bin/python scripts/research_data_mcp/library_smoke.py` (MCP, no API) |
| API smoke | `.venv/bin/python scripts/procurement_ops_smoke.py` (needs `:8765` up) |
| LLM | `CURSOR_API_KEY` in `.env.local` for Composer desk chat |

**Remote access:** put Caddy/nginx in front of `:8765` with TLS. API serves `dist/` when started with `--serve-ui`.

**Faculty login:** `@saturn.yzu.edu.tw` or `@yzu.edu.tw` email (registry personalization). Ops views require the same login.

**Job backlog:** safe types (DataCite collect, source_probe, short queue tasks) auto-approve from desk chat. Clear historical `pending_approval` backlog:

```bash
.venv/bin/python scripts/yzu_cluster/triage_pending_jobs.py --approve-safe --dry-run
.venv/bin/python scripts/yzu_cluster/triage_pending_jobs.py --approve-safe
```

**Codex / IDE path:** `research-data` MCP (`scripts/run_research_data_mcp.sh`) — same backend as the desk; use for power users, not inside the web UI.

## Problem (why the current stack feels bad)

Today we have **four half-products** that do not share one job model:

| Layer | What exists | Why it fails researchers |
|-------|-------------|---------------------------|
| **Research Drive UI** (`src/main.jsx`) | Pretty acquisitions/library views | **Hardcoded rows** — not wired to live cluster state |
| **Query engine** (`:8765`) | Registry + query + source planner | Good for *querying what we have*, weak for *getting new data* |
| **MCP agent** (`research_data_mcp`) | Chat → plan → approve → execute | Only 3 job types; no scraper dispatch; threads not durable |
| **Collection queue** (`run_data_collection_queue.py`) | Unattended local shell tasks | Parallel universe — no agent UI, skips credentialed tasks |
| **Cluster workers** | DataCite / GDELT / `remote_collect.py` | Each pipeline has its own watchdog; no unified registry |
| **Spectator** (Molina-Optiplex) | Puppeteer scrapers on remote `spectator` host | **Not in Sharpe repo**; Drive dump is archive-not-control-plane |
| **Molina `research-drive/`** | FastAPI `:8000` metadata browser | **Not integrated** with Sharpe query engine or agent |

Google Drive was used as a poor man's catalog. It works for cold archive (`rclone copy`, never `sync`) but is **not** a procurement control plane.

## Vision

**YZU Cluster** = one orchestration layer for any researcher (or chatbot agent) to:

1. **Discover** — what datasets exist (registry + DataCite + source planner)
2. **Plan** — probe URL, estimate size/access mode, pick worker pool
3. **Procure** — dispatch jobs to Linux/Windows/Spectator workers
4. **Stage** — local `data_lake/` with disk guards
5. **Archive** — verified upload to GDrive tier
6. **Register** — promote into `research_query_registry.json`

```text
Researcher / Agent chat
        │
        ▼
┌───────────────────┐
│  YZU control plane │  optiplex — job queue, worker registry, status API
└─────────┬─────────┘
          │
    ┌─────┴─────┬─────────────┬──────────────┐
    ▼           ▼             ▼              ▼
 Windows     Linux local   Spectator      Public HTTP
 (SSH)       (systemd)     (scrape fork)  (remote_collect)
    │           │             │              │
    └───────────┴─────────────┴──────────────┘
                        │
                        ▼
              data_lake/ (staging)
                        │
                        ▼
              gdrive:Machine_Archive/... (cold)
                        │
                        ▼
         research_query_registry.json
```

## Worker pools

| Pool | Hosts | Engine | Use for |
|------|-------|--------|---------|
| `windows_lab` | 4× Tailscale ASUS nodes | PowerShell tasks, Python workers | HTTP harvest, DataCite shards, GDELT fetch |
| `optiplex` | This machine | systemd user services | Controller, local shards, queue runner |
| `spectator` | `spectator` / `100.96.62.97` | Molina `spectator_*.mjs` (Puppeteer) | JS-heavy sites, CDP, SQLite scrapes |
| `public_http` | Any joined node | `cluster_agent/remote_collect.py` | Direct file URLs |

Spectator is **forkable**: copy Molina `scripts/spectator_*.mjs` + deps to cluster nodes; wrap with `scripts/yzu_cluster/workers/scraper_dispatch.sh`.

## Unified job types (target)

| `job_type` | Today | YZU target |
|------------|-------|------------|
| `source_probe` | `procurement.probe()` | keep |
| `http_manifest` | `remote_collect.py` on Windows | keep + retry queue |
| `registered_pipeline` | allowlisted shell only | expand registry |
| `scraper_run` | **missing** | dispatch Spectator/Crawlee worker |
| `harvest_shard` | ad-hoc DataCite/GDELT scripts | generic shard runner |
| `archive_upload` | per-pipeline rclone | shared post-verify uploader |

## Phased revamp

### Phase 1 — Control plane (done)
- `config/yzu_cluster.json` — worker pools, pipelines, schedules, spectator scripts
- `scripts/yzu_cluster/orchestrator.py` — unified SQLite job queue
- `scripts/yzu_cluster/executor.py` — cross-pool execution
- `scripts/yzu_cluster/worker.py` — durable worker + scheduler tick
- `scripts/yzu_cluster/cli.py` — CLI (`components`, `jobs`, `submit`, `approve`, `queue`)
- API on `:8765` — `/yzu/*` + `/agent/*` share one queue
- UI on `:5178` — dashboard, library, jobs quick-launch

Launch: `scripts/run_yzu_cluster.sh` (API + worker + Vite UI)

### Phase 2 — Job queue (done)
- SQLite at `data_lake/yzu_cluster/jobs/jobs.sqlite3`
- Job types: `source_probe`, `http_manifest`, `registered_pipeline`, `collection_queue_task`, `collection_queue_batch`, `harvest_shard`, `archive_upload`, `scraper_run`
- Agent approves → worker executes (no daemon threads)

### Phase 3 — Spectator on cluster (partial)
- `scraper_run` dispatches allowlisted Molina scripts on `spectator` via SSH
- Configure scripts in `config/yzu_cluster.json` → `spectator_scripts`

### Phase 4 — UI revamp (done)
- Live acquisitions from `/yzu/status` (cached shard probes)
- Jobs page wired to `/yzu/jobs` with quick-launch + schedules

## Storage rules (unchanged, enforced centrally)

- Local = staging + hot query panels only
- GDrive = cold archive after `rclone check`
- Delete local blobs after verify (`compact` / reclaim scripts)
- Never `rclone sync` (missing local must not delete Drive)

## Component coherence (integration audit)

Run without any live LLM — verifies config cross-refs, API wiring, and safe job paths:

```bash
.venv/bin/python scripts/yzu_cluster/integration_audit.py
# API-only (no job execution): --no-execute
```

**Single control plane:** `YzuOrchestrator` + SQLite job store is shared by `/yzu/*`, `/agent/*`, background worker, CLI, and UI.

| Component | Entry | Talks to |
|-----------|-------|----------|
| Registry | `/datasets`, `/query/{id}` | `research_query_registry.json` |
| Collection queue | `/yzu/queue/tasks`, job types `collection_queue_*` | `config/data_collection_queue.json` |
| Pipelines | `/yzu/components`, `registered_pipeline` jobs | `config/yzu_cluster.json` pipelines |
| Windows pool | `/yzu/workers`, `http_manifest`, `harvest_shard` | inventory CSV + SSH |
| Spectator | `scraper_run` jobs | allowlisted Molina scripts |
| Procurement | `source_probe` jobs | connector store under jobs root |
| DataCite / GDELT | `/yzu/acquisitions` | local data_lake + fleet scripts |

`/agent/chat` is a deprecated compatibility shell. Composer desk chat uses `/library/chat`, and submit/approve/execute is owned by the shared YZU job store.


- Agent brain: `scripts/research_query_engine/agent.py`
- Procurement: `scripts/research_query_engine/procurement.py`
- Cluster HTTP worker: `scripts/cluster_agent/remote_collect.py`
- Registry: `config/research_query_registry.json`
- Windows inventory: `/home/phyrexian/cluster-lab-logs/windows-cluster-inventory.csv`
- Spectator (Molina): `../scripts/spectator_*.mjs`, `config/spectator_remote_paths.json`
