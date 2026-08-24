# Research Data MCP Gateway

MCP tools for **developer** use (Composer/Cursor). Professor-facing UX is the **Research Drive website** — see [`DESK_STATUS.md`](DESK_STATUS.md).

**Naming:** **MCP** = the full data procurement toolbox. This file documents the **protocol adapter** only. Canonical stack map: [`MCP_PROCUREMENT_STACK.md`](MCP_PROCUREMENT_STACK.md).

**Scope:** [`DESK_STATUS.md`](DESK_STATUS.md)  
**Architecture:** [`PROCUREMENT_PIPELINE.md`](PROCUREMENT_PIPELINE.md)  
**HTTP routes:** [`research_library_backend.md`](research_library_backend.md)

## Start

```bash
# stdio (Cursor / Claude Desktop)
scripts/run_research_data_mcp.sh

# streamable HTTP on :8770
RESEARCH_MCP_TRANSPORT=streamable-http scripts/run_research_data_mcp.sh
```

Client config: `config/research_data_mcp.example.json`

## Conversational procurement

The Model operates directly with the following flat MCP tools to discover, query, and collect datasets.

Flow: search local catalog -> preview/query -> if miss, discover web -> probe target -> submit collect job -> monitor progress.

State: `data_lake/procurement_memory/chat_sessions.sqlite3`

## Agent workflow (MCP / ops)

```text
1. research_library_overview          → what is instant vs metadata vs remote
2. research_discover_search(q=...)    → ranked candidates from local registry
3. research_query_dataset(...)        → fetch rows from ready local/remote datasets
4. research_search_catalog            → external metadata discovery
5. research_web_discover              → open web discovery (Tavily/DDG)
6. procurement_probe_public_source    → probe target URL to check layout & robots.txt
7. yzu_submit_job                     → submit collection job (HTML scrape, http_manifest, BQ, etc.)
8. yzu_get_job                        → monitor ops status
```

## Search tools

| Tool | Purpose |
|---|---|
| `research_library_overview` | Bucket datasets by readiness; shows recommended flow |
| `research_list_datasets` | List/search registry (`q`, `readiness`, `access_shape`) |
| `research_describe_dataset` | One dataset: grain, join keys, backend, limitations |
| `research_query_dataset` | Query any registered dataset (`params_json` object) |
| `research_discover_search` | Search registry/catalog index for matches |
| `research_search_catalog` | Curated external metadata index search |
| `research_ops_status` | Collection queue + DataCite harvest combined |
| `collection_queue_status` | Local `data_collection_queue` snapshot |
| `datacite_local_harvest_status` | DataCite harvest lane checkpoints under `index_v3/` |

### Instant panel query example

```text
research_query_dataset("cross_asset_fused_primary_panel", "{\"country\":\"TWN\",\"limit\":10}")
```

## Procurement tools

| Tool | Purpose |
|---|---|
| `procurement_probe_public_source` | Bounded HTTP sample + connector candidate |
| `procurement_list_connectors` | Saved candidates / approved connectors |
| `procurement_approve_connector` | Human gate — does not collect |
| `procurement_prepare_collection` | Plan only (no job created) |
| `procurement_submit_collection_job` | Create `pending_approval` job from approved connector |
| `procurement_list_jobs` | Job history |
| `procurement_get_job` | Job detail + event log |
| `procurement_approve_job` | Launch approved collection |
| `procurement_cancel_job` | Cancel pending/queued job |

State: `data_lake/agent_jobs/procurement_connectors.sqlite3`, `agent_jobs.sqlite3`

## DataCite (live metadata API)

| Tool | Purpose |
|---|---|
| `datacite_search` | Cursor-paginated DOI metadata search |
| `datacite_get` | One DOI record |
| `datacite_scope` | Count records for year scope |
| `datacite_backfill_spec` | Plan checkpointed harvest (does not execute) |

## BigQuery (guarded)

Requires `gcloud auth application-default login` and `GOOGLE_CLOUD_PROJECT`.

| Tool | Purpose |
|---|---|
| `bigquery_status` | ADC + project readiness |
| `bigquery_list_datasets` / `bigquery_list_tables` / `bigquery_table_schema` | Discovery |
| `bigquery_dry_run` | Byte estimate |
| `bigquery_read_query` | Execute after dry-run with `confirm=EXECUTE_READ_ONLY` |

## YZU cluster tools (library + MCP)

Unified with `YzuOrchestrator` — same job store as HTTP `:8765` and UI.

| Tool | Purpose |
|---|---|
| `research_procurement_catalog` | Browse registry + queue tasks + pipelines + connectors |
| `research_advise_datasets` | Librarian: wrong dataset? what to use instead |
| `yzu_cluster_status` | Disk, harvest progress, job stats |
| `yzu_list_acquisitions` | Live acquisition tiles |
| `yzu_cluster_components` | Pools, pipelines, allowed job types |
| `yzu_list_queue_tasks` | Runnable collection queue tasks |
| `yzu_submit_job` | Submit job from `plan_json` |
| `yzu_approve_job` / `yzu_cancel_job` | Job gates |
| `yzu_get_job` / `yzu_list_jobs` | Monitor execution |
| `yzu_archive_to_gdrive` | `rclone copy` + verify to cold archive |

## Design rules

- **Instant** (`analysis_readiness: instant`) — query directly, no download.
- **Metadata** — search only; probe or register before analysis.
- **Procurement** — probe → submit job → approve/execute job.
- MCP never bypasses approval gates, robots checks, private-IP blocks, or BigQuery bytes limits.
