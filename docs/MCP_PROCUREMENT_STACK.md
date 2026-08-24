# Procurement MCP — the full toolbox

**MCP** = the **data procurement platform** (dictionary, engines, cluster, vault, orchestration).

The Cursor **protocol server** (`scripts/run_research_data_mcp.sh`) is the plug for **Composer**.

| Audience | Doc |
|----------|-----|
| **Composer / operator** | [`COMPOSER_PROCUREMENT.md`](COMPOSER_PROCUREMENT.md) |
| **Research Drive UI** | [`DESK_STATUS.md`](DESK_STATUS.md) |

---

## Orchestrator

**Cursor Composer is the only hot-path brain.** It uses MCP tools directly:

```text
Composer -> research_discover_search / collection_status
         -> research_describe_dataset / research_query_dataset
         -> research_web_discover
         -> procurement_probe_public_source
         -> yzu_submit_job / yzu_get_job
```

`research_procure_chat` is only the MCP/HTTP mirror for the desk chat route. It is not a second planner, and legacy LLM helpers are not desk brains.

---

## Acquisition ladder

```text
vault_dictionary → registry_catalog → datacite_local_prefetch
  → discover_search → web_discover → probe_url
  → shell_direct_http | spectator_playwright → cluster_jobs → vault
```

Composer native Playwright / webfetch / web search = same rungs as shell/Spectator for **probe**, not default **acquire**.

---

## Engines

| Engine | Role |
|--------|------|
| **Collection dictionary** | Vault map — check first |
| **Registry** | Query + describe (`access_tier` on describe) |
| **DataCite harvest** | Your academic index |
| **web_search.py** | Tavily, DuckDuckGo, Zenodo, OpenAlex on index_miss |
| **Spectator** | Playwright extract + flywheel |
| **Cluster** | Queue, harvest, BQ, archive |
| **BigQuery** | Guarded on-chain (`ethereum_usdt_transfers`) |

---

## Protocol tools

```bash
.venv/bin/python scripts/research_data_mcp/mcp_stack_audit.py
```

MCP: `research_mcp_stack_status` · HTTP: `GET /library/extensions/tools`

| **core** | 13 | Composer daily — start with `research_discover_search` |
| **acquire** | 11 | DOI, jobs, BQ read, campaigns |
| **ops** | 38 | Admin, chat mirror, raw DataCite |

---

## Honest bounds

| Claim | Reality |
|-------|---------|
| Registry count | Only `analysis_readiness: instant` rows are directly queryable; the rest are catalog/metadata/procurement records |
| Search = acquire | yzu_submit_job(plan) |
| All registry datasets queryable | **No** — check `access_tier` on describe |

---

## Tests

```bash
.venv/bin/pytest tests/test_mcp_stack_consolidation.py \
  tests/test_procurement_search.py tests/test_faculty_profile_recommendations.py -q
```
