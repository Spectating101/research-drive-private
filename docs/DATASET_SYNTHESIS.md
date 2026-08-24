# Dataset synthesis (desk capability)

Multi-source **entity-level join + gap analysis + panel artifacts** — supersedes metadata-only Cluster Venn overlap. The flagship showcase is **`stablecoin_trust_engagement`** (community growth, code security, GDELT, DeFiLlama, Skynet/Etherscan, Wikipedia, GitHub, incidents → entity×week panels).

---

## Is it integrated?

**Yes — backend/desk layer.** Not a throwaway script; wired into MCP, HTTP, and Composer chat.

| Surface | Status |
|---------|--------|
| Engine | `drive/scripts/research_data_mcp/synthesis/` |
| Profiles | `config/synthesis_profiles.json` |
| MCP tools (core) | `research_synthesis_list_profiles`, `research_synthesis_run`, `research_synthesis_pair` |
| HTTP | `GET /library/synthesis/profiles`, `GET /library/synthesis/{id}`, `POST /library/synthesis/run`, `POST /library/synthesis/pair` |
| Gateway | `gateway.synthesis_run()`, `synthesis_pair()` |
| Desk chat | `desk_brain.py` → **Cursor cloud agent** + stdio MCP (`CURSOR_API_KEY`, `RESEARCH_MCP_DESK=1`) |
| CLI | `scripts/run_synthesis.py` |
| Faculty UI tab | **Not yet** — API + chat + MCP only |

**Showcase dataset (v3):** `data/datasets/stablecoin_trust_engagement/latest/` — built 2026-06-26; ~20,980 weekly panel rows, 71 entities.

---

## Script path vs Composer path (do not confuse)

| Path | Entry | Proves |
|------|-------|--------|
| **Equipment / CI** | `synthesis_harness.py`, `synthesis_trust_engagement_harness.py`, `run_synthesis.py`, `pytest tests/test_synthesis.py` | MCP tools + engine work |
| **Product** | `POST /library/chat` → `desk_brain.run_cursor_composer_turn()` → Cursor → MCP | Professor-facing Composer synthesis |

Harnesses call `stack.tools.research_synthesis_run()` **directly** — they do **not** prove Composer chose the tool.

**Composer chat smoke:** `scripts/ops/desk_synthesis_chat_smoke.py` (needs API `:8765` + `CURSOR_API_KEY` in `.env.local`).

**Composer runtime (headless cluster):** cloud agents by default (`CloudAgentOptions`). Local agents (`DESK_COMPOSER_LOCAL=1`) need Cursor IDE bridge on the same host. MCP child `PYTHONPATH` = `repo:kernel:drive:alpha`.

**Model:** `DESK_COMPOSER_MODEL` defaults to `default` (reliable with MCP); fallback `composer-2.5` via `DESK_COMPOSER_MODEL_FALLBACK`.

---

## Profiles

### `stablecoin_trust_engagement` (full cluster)

- **Type:** `trust_engagement`
- **Sources:** Skynet, Etherscan scrapes, community proxies, DeFiLlama peg/supply, GDELT overlay, Wikipedia, GitHub, incidents
- **Output panel:** `panels/research_panel_weekly.csv` (`community_growth_index`, `code_security_score`, `gdelt_*`, peg/supply, etc.)
- **Default mode:** `validate_existing: true` — reads v3 package on disk (~40ms); does **not** rebuild every call
- **Full rebuild:** set `validate_existing: false` in profile → calls `publish_research_dataset()` (same as `build_stablecoin_research_dataset.py`). GDELT overlay scan is slow; wait for expanded fleet / Jul 7 handoff before forcing full refresh.

### `skynet_etherscan_stablecoin`

- Address-level join: Skynet leaderboard ↔ Etherscan token scrapes; gaps + entity panel.

---

## Procurement playbook (Composer)

1. `research_synthesis_list_profiles`
2. `research_synthesis_run(profile_id="stablecoin_trust_engagement")` for trust↔engagement cluster
3. `research_synthesis_pair(left_dataset_id, right_dataset_id)` for registry metadata join viability only

See also `.agents/AGENTS.md` and desk MCP instructions (`RESEARCH_MCP_DESK=1`).

---

## Not done yet

- `stablecoin_unified_panel` in `research_query_registry.json` (synthesis tools work; `research_query_dataset` does not)
- Synthesis gaps → auto `yzu_submit_job` scrape plans
- Dedicated React synthesis surface (Codex frontend)
- Rigorous `/library/chat` tool-call attribution in smoke (answers verified; tool names not always in HTTP artifacts)

---

## Related

- Stablecoin dataset build: `docs/STABLECOIN_RESEARCH_DATASET.md`, `scripts/build_stablecoin_research_dataset.py`
- GDELT expanded fleet (cluster downloads): `docs/GDELT_EXPANDED_FLEET.md`
- Desk scope: `docs/DESK_STATUS.md`
