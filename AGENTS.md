# Research Data Procurement — agent rules

Canonical copy: see also [`.agents/AGENTS.md`](.agents/AGENTS.md). Faculty/lab context: [`docs/DESK_STATUS.md`](docs/DESK_STATUS.md). Repo layout: [`REPO_LAYOUT.md`](REPO_LAYOUT.md).

This workspace is the **YZU Research Drive / procurement platform** (`drive/`). Python is passive MCP equipment; **Cursor Composer** plans and calls atomic tools. Alpha engine lives in `alpha/`; shared contract in `kernel/`.

Do not re-introduce Python heuristic planners (`planner.py`, `composer_workflow`, composite `research_plan_collect` tools).

## Where to work

| Area | Path |
|------|------|
| Faculty UI, MCP, query engine | `drive/scripts/yzu_cluster/`, `drive/scripts/research_data_mcp/` |
| Registry (producer) | `drive/config/research_query_registry.json` |
| GDELT / collection fleet | `drive/scripts/run_news_shock_*`, `drive/config/gdelt_*` |
| Alpha (do not mix into drive) | `alpha/` |

## Procurement playbook

1. `research_discover_search` or `collection_status` — local index
2. `research_describe_dataset` + `research_query_dataset` — inspect hits
3. `research_web_discover` — on miss
4. `procurement_probe_public_source(url)` — classify source
5. `yzu_submit_job(plan_json)` or `datacite_collect_doi` — acquire
6. `yzu_archive_to_gdrive` — vault
7. `research_open_dataset` — verify

**Dataset synthesis (stablecoin / multi-source cluster):**

8. `research_synthesis_list_profiles` — available merge profiles
9. `research_synthesis_run("stablecoin_trust_engagement")` — community + security + GDELT + adoption panel
10. `research_synthesis_pair(left_id, right_id)` — registry join viability (not entity merge)

Faculty UI: `POST /library/chat` (Composer + MCP). Not `/library/magic`, `/library/assist`, or `/library/workflow` (removed).

Composer uses **cloud agents** by default (`CURSOR_API_KEY` + stdio MCP). Set `DESK_COMPOSER_LOCAL=1` only when the Cursor IDE local bridge runs on the same host.

GDrive vault: `gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data` — professor share is `collection/` only.
