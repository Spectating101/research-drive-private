# Composer + Procurement MCP

**Orchestrator:** The LLM Model (Cursor Composer 2.5 / Gemini) via raw protocol tools. The Python backend is strictly passive and does not orchestrate or auto-submit jobs.

---

## Workflow Playbook

Instead of relying on heuristic Python planners, the Model uses its own reasoning loop to execute the acquisition ladder:

```text
1. collection_status        --> Check what is already present in the vault
2. research_discover_search --> Search local registry & metadata catalog
3. research_web_discover    --> If local miss, search Tavily/DDG for sources
4. procurement_probe_public_source --> Probe target URL to extract data layout & robots.txt
5. yzu_submit_job           --> Submit a custom collection job plan directly
6. yzu_get_job              --> Monitor execution status until completion
```

---

## Flat Atomic Tools

Use these atomic tools to query, inspect, and collect datasets:

| Tool | Purpose |
|------|---------|
| `collection_status` | Returns the vault status (GDrive & local partitions) |
| `research_discover_search` | Searches local catalog registry |
| `research_web_discover` | Runs an external web search (Tavily/DDG) |
| `research_describe_dataset` | Shows grain, schema details, and access tier of a dataset |
| `research_query_dataset` | Direct SQL-like querying for instant local datasets |
| `procurement_probe_public_source` | Probes URL headers and structure to help formulate a plan |
| `yzu_submit_job` | Submits a raw collection job (HTML scraping, HTTP manifest, BigQuery, etc.) |
| `yzu_get_job` | Refreshes and monitors job progress |

---

## Decommissioned Heuristics

The following composite/planning tools have been decommissioned:
* `research_composer_workflow`
* `research_composer_session`
* `research_plan_collect`
* `research_collect_fast`
* `research_submit_collect_plan`
* `research_job_outcome`

The Model must formulate collection plans directly and submit them as JSON payloads to `yzu_submit_job`.
