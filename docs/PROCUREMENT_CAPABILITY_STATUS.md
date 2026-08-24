# Procurement capability status

Release gate for Kong FinTech pilot + known gaps.

## Proven (stack-native)

| Capability | Proof |
|------------|--------|
| **Faculty desk chat** | Cursor Composer 2.5 + procurement MCP (`desk_brain.py`, `POST /library/chat`) |
| Session warm / vault brief | `POST /library/desk/warm`, `desk_vault_brief.py` |
| Composer search (operator) | `research_discover_search` |
| Registry / vault hits | GDELT, OpenSea, Skynet, TWSE OpenAPI, prior scrapes |
| BigQuery USDT | `ethereum_usdt_transfers` dry-run |
| Hard miss procurement | web → probe → yzu_submit_job |
| Single-page scrape | `generic_url_scrape` mode=page |
| **Catalog crawl** | mode=catalog — listing pagination + per-token metadata |
| Probe → catalog | `pagination.detected` + `html_catalog` (no URL regex) |
| Collect path | Composer → `yzu_submit_job` |
| HTTP desk mirror | `POST /library/chat` (Cursor Composer + MCP) |
| Multi-source honesty | `join_hint` when 2+ registry rows match taxonomy ask |
| Desk chat smoke | `scripts/ops/desk_chat_smoke_loop.py` (warm + 3-turn quality gate) |

**Desk chat smoke (latest):** `docs/status/generated/desk_chat_smoke_loop.json` — warm session + 3/3 turns pass (inventory, plain prose, sample rows).

## Explicit catalog plan (no inference)

Below is an example of an explicit scraper run plan layout. The LLM constructs this plan directly and submits it to `yzu_submit_job`:

```json
{
  "job_type": "scraper_run",
  "script_key": "generic_url_scrape",
  "url": "https://etherscan.io/tokens?l=Stablecoin",
  "scrape_mode": "catalog",
  "catalog_max_pages": 64,
  "catalog_max_tokens": 3500,
  "catalog_pause_ms": 400,
  "agent_initiated": true,
  "launchable": true
}
```

**Note:** Restart the research library API after code updates so `/health` includes `desk.gdrive` (running process may be stale).

## Next: procurement miss → GDrive → partition (automated)

Closed loop when `index_miss` / `relevance_miss`:

```text
Composer miss → web_discover → probe → yzu_submit_job (+ partition_id)
  → submit (auto_acquire_on_miss) → worker → registry promote
  → archive_upload → collection/{partition}/{dataset_id} on GDrive
  → partition.registry_dataset_ids + collection_dictionary rebuild
```

| Piece | Module / config |
|-------|-----------------|
| Partition inference | `partition_wiring.infer_partition_id` (keyword tokens) |
| Plan stamp | LLM structures plan with `partition_id` directly |
| Auto submit on miss | `procurement_magic.json` → `research.auto_acquire_on_miss: true` |
| GDrive path | `archive_after_job` + `partition_wiring.archive_remote_suffix` |
| Vault wiring | `bootstrap._on_job_completed` → `wire_promoted_to_partition` |
| MOPS landing zone | `official.mops-disclosures` in `collection_partitions.json` |

**Still manual / product gaps:** structured MOPS API collector (today lands web PDFs into `official.mops-disclosures`); rclone must be configured on the worker for actual GDrive bytes.

## Still open (product coverage — not desk spine gaps)

| Gap | Notes |
|-----|--------|
| Full Etherscan sweep | Queue task `etherscan_stablecoin_catalog_sweep` wired; run `submit_etherscan_catalog_sweep.py` on worker (hours) |
| MOPS refresh | Structured panel collected; optional periodic re-fetch via `fetch_taiwan_mops_governance_panel.py` |
| GDrive on live `/health` | Probe code shipped — restart API to surface `desk.gdrive` |
| All CM faculty deep profiles | 62 faculty in registry + `@yzu.edu.tw` fallback for unknown emails |

## Tiers

See `docs/PROFESSOR_PROFILING.md` and `pipeline_difficulty.py`.

- **T5** = job completes → registry promotion → optional `gdrive_archives` on job result
