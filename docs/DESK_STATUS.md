# Research Desk — scope (read this first)

**Audience:** Professor-facing lab library + your dev work on the same spine.  
**Not in scope here:** Alpha trading (`scripts/alpha_*`), Indonesia sleeve, platform timers — see root `CLAUDE.md`.

---

## Two promises

| # | Promise | What she sees |
|---|---------|----------------|
| **1** | **Organized lab data on Google Drive** | Clear partitions, titles, descriptions — not scattered mystery folders |
| **2** | **Assistant that can procure hard data** | Chat: search → query what we have → collect if missing → it lands in the vault |

**Canonical vault:** `gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data`  
**Professor link:** `collection/` only — see [`docs/VAULT_LAYOUT.md`](VAULT_LAYOUT.md) (`datacite_catalog/` is backend sibling, not in share)  
**Open Drive and you’re lost?** → [`docs/GDRIVE_WHERE_TO_LOOK.md`](GDRIVE_WHERE_TO_LOOK.md)  
**Queryable catalog:** `config/research_query_registry.json`  
**Website:** Research Drive UI — `bash scripts/run_yzu_cluster.sh` → API `:8765` + Vite `:5178` (or `npm run build` + `--serve-ui`)

Legacy Drive names (`news_shock_taxonomy`, `dataset_catalog`, …) still exist on disk. The **partition map** is the clean view; physical rename is optional later.

---

## The flywheel (not a third product)

ChatGPT repeats search + download every session. This desk **remembers**:

```text
Ask → search dictionary (registry + partitions + curated / DataCite index)
  → HIT:  query / preview from lab (no re-procure)
  → MISS: collect once → GDrive → describe → register
  → NEXT: HIT
```

**Dictionary** = partitions + registry + curated index.  
**Hands** = procurement MCP (62 atomic tools) + job queue + worker + scripts.  
**Brain** = **Cursor Composer** in the faculty UI (`config/procurement_magic.json` → `chat.brain: cursor_composer`). Cloud agent + MCP by default; see [`docs/DATASET_SYNTHESIS.md`](DATASET_SYNTHESIS.md).

**Dataset synthesis** = multi-source join capability (showcase: `stablecoin_trust_engagement`). MCP + HTTP integrated; faculty UI tab not yet.

This is the **production lab stack** (not a throwaway demo): same API, vault, and chat path you operate on daily. Individual datasets may still be pilot-scale until archived under `collection/`.

On chat open the UI calls `POST /library/desk/warm` — vault brief + Composer session primed in the background so turn 1 is conversational, not an inventory dump.

After every successful collect: `RegistryPromoter` + `archive_after_job` (GDrive) + optional curated index update.

---

## Three layers (all code paths)

```text
1. Catalog   — registry, collection_partitions, data_collection_queue.json, local_search()
2. Execute   — YzuOrchestrator → YzuExecutor (queue / http / pipeline / scrape / archive)
3. Converse  — desk_brain (Composer + MCP) for UI; no Python planner on the hot path
```

Wiring: `scripts/research_data_mcp/bootstrap.py` → `create_stack()`.

```text
Composer = brain
Procurement MCP = hands
Repo = equipment + filing cabinet
```

Do **not** add a fourth “magic” Python brain (`magic_procure` is deprecated).

---

## What to run

| Role | Command |
|------|---------|
| **Professor / lab UI** | `bash scripts/run_yzu_cluster.sh` |
| **Worker** (must be up for collects) | started by `run_yzu_cluster.sh`, or `python -m scripts.yzu_cluster.worker --poll 2` |
| **API only** | `bash scripts/run_research_query_engine.sh` (loads `.env.local` via `bootstrap`) |
| **Dev / Composer MCP** | `scripts/run_research_data_mcp.sh` |
| **MCP toolbox audit** | `.venv/bin/python scripts/research_data_mcp/mcp_stack_audit.py` |
| **Library smoke** | `.venv/bin/python scripts/research_data_mcp/library_smoke.py` |
| **Desk chat smoke** | `.venv/bin/python scripts/ops/desk_chat_smoke_loop.py` |

### Secrets

Set `CURSOR_API_KEY` in `Sharpe-Renaissance/.env.local` (loaded by `bootstrap.create_stack()` and `scripts/lib/platform_env.sh`).  
Legacy external-LLM settings may remain in old scripts, but they are not a desk option. Professor-facing chat is Composer + MCP only.

### Faculty chat HTTP

| Route | Purpose |
|-------|---------|
| `POST /library/desk/warm` | Pre-prime session + vault brief |
| `GET /library/desk/brief` | Vault brief only |
| `POST /library/chat` | Chat turn |
| `POST /library/chat/stream` | Streaming chat (UI) |
| `GET /health` | `desk.brain`, `desk.composer_configured`, jobs |

### Composer tools (protocol tier **core**)

**Desk UI:** Composer chooses tools freely via stdio MCP (`scripts/research_data_mcp/server.py`).

**Operator / shell:** Expose flat atomic tools. See [`COMPOSER_PROCUREMENT.md`](COMPOSER_PROCUREMENT.md).

1. `research_faculty_profile` (when email known)
2. `research_query_dataset` / `research_describe_dataset` / `research_analyze_dataset`
3. `research_discover_search` / `research_web_discover` → `procurement_probe_public_source`
4. `yzu_submit_job` (LLM submits custom collection plans directly)
5. `research_collection_hydrate` when bytes are on Drive only

`research_procure_chat` MCP tool = HTTP mirror of the UI — not the brain.

---

## Config map (don't confuse these)

| File | Question it answers |
|------|---------------------|
| `collection_partitions.json` | What’s on Drive, human titles/descriptions |
| `research_query_registry.json` | What can we `query_dataset` right now? |
| `data_collection_queue.json` | Which ETL scripts can jobs run? |
| `procurement_registry_map.json` | After job success → registry row |
| `procurement_magic.json` | Auto-collect, chat brain, flywheel |
| `yzu_cluster.json` | Pipelines, GDrive roots, worker routing |
| `storage_tiers.json` | GDrive = canonical, USB = cache, NVMe = hot |

---

## Frozen / deprecated (do not extend)

| Item | Note |
|------|------|
| `procurement_chat.py` | UI session shell — fix bugs only; brain is `desk_brain.py` |
| `magic_procure.py` | Campaign resume/approve only — not HTTP, not chat |
| `POST /library/magic`, `/library/assist`, `/library/workflow` | Removed — use `/library/chat` + MCP |
| `procurement_agent.py`, `planner.py`, `composer_workflow.py` | Deleted |
| `research_data_library.html` | Legacy prototype |
| Audit / duel / benchmark scripts | Removed |
| Windows fleet | Optional; optiplex runs queue until workers provisioned |
| Spectator host | Disabled in `yzu_cluster.json` |

---

## Tests

```bash
.venv/bin/pytest tests/test_desk_brain.py tests/test_desk_vault_brief.py tests/test_desk_reply_sanitize.py -q
.venv/bin/pytest tests/test_procurement_search.py tests/test_procurement_equipment_bridge.py -q
.venv/bin/python scripts/ops/desk_chat_smoke_loop.py   # needs API + CURSOR_API_KEY
```

Rules: `tests/README.md`

---

## Deeper technical docs

| Doc | Use for |
|-----|---------|
| [`DATABANK_STATE.md`](DATABANK_STATE.md) | **Neutral inventory** — what exists, where, coverage axes |
| [`DESK_ACTIVATION.md`](DESK_ACTIVATION.md) | **Activation backlog** — profile-filtered priorities (not global doctrine) |
| [`DATASET_SYNTHESIS.md`](DATASET_SYNTHESIS.md) | Synthesis capability, Composer vs harness, profiles |
| [`GDELT_EXPANDED_FLEET.md`](GDELT_EXPANDED_FLEET.md) | Expanded GDELT downloads on cluster / Transcend |
| [`RESEARCH_DRIVE_UI_CANON.md`](RESEARCH_DRIVE_UI_CANON.md) | **UI composition + workflows** — shell, DetailPanel, handoffs |
| [`RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md) | Right rail as the interface + integration anchor |
| [`design/TOKENS.md`](design/TOKENS.md) | Visual tokens (colors, spacing) |
| [`PROCUREMENT_CAPABILITY_STATUS.md`](PROCUREMENT_CAPABILITY_STATUS.md) | Release gate + benchmark results |
| [`PROCUREMENT_PIPELINE.md`](PROCUREMENT_PIPELINE.md) | Module map, HTTP routes, flow diagrams |
| [`research_data_mcp.md`](research_data_mcp.md) | MCP catalog |
| [`STORAGE_ARCHITECTURE.md`](STORAGE_ARCHITECTURE.md) | GDrive / USB / NVMe tiers |
| [`COLLECTION_ARCHITECTURE.md`](COLLECTION_ARCHITECTURE.md) | Partition migration notes |
