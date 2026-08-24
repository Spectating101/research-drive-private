# Professor profiling (v2 intel)

How we turn a YZU CM faculty row into **Discover**, **chat**, **DataCite**, and **BigQuery** routing.

## Two lanes (do not merge)

| Lane | What | Profile fields |
|------|------|----------------|
| **A — Vault** | Bytes already in `collection/` | `lab_fintech_stack`, `registry_dataset_ids` |
| **B — Procure** | Search, extend, collect when missing | `recommended_datasets`, `datacite_scopes`, `bigquery_interests` |

Vault inventory is **not** copied into `recommended_datasets` prompts. The lab stack is declared once in `lab_fintech_stack`.

## Intel sources (enrich beyond CM journal scrape)

1. **YZU CM page** — specialties, journal list, grants (if listed)
2. **Google Scholar / SSRN** — working papers, citation weight, FinTech/NFT keywords
3. **Grants** — active direction (e.g. token taxonomy on/off-chain)
4. **Lab commission** — pipelines built for the professor (OpenSea, CoinGecko, Skynet, BigQuery USDT)
5. **Live probes** — short DataCite seeds + `require_any` / `demote_any` filters (no bulk harvest)

Pilot example: `drkong` in `config/yzu_cm_faculty_registry.json`.

## Registry schema (`profile_schema: v2_intel`)

```json
{
  "external_profiles": { "google_scholar": "...", "ssrn": "..." },
  "research_tracks": [{ "id", "phase", "title", "weight", "routes" }],
  "research_grants": [{ "title", "phase", "primary_direction" }],
  "ssrn_papers": [{ "title", "ssrn_id", "keywords", "citation_weight" }],
  "working_papers": [{ "title", "keywords" }],
  "lab_fintech_stack": [{ "id", "label", "partition_id", "registry_dataset_ids", "route", "priority", "prompt" }],
  "datacite_scopes": [{ "id", "seed_queries", "require_any", "demote_any", "max_results" }],
  "bigquery_interests": [{ "registry_id", "trigger_keywords", "label", "note" }],
  "registry_dataset_ids": [],
  "recommended_datasets": [],
  "domain_tags": [],
  "research_keywords": []
}
```

## Runtime (`scripts/research_data_mcp/faculty_profile.py`)

| Function | Use |
|----------|-----|
| `lab_fintech_stack_recommendations` | Discover chips — vault/BQ routes first |
| `datacite_scope_queries` | Short live DataCite API seeds |
| `expand_datacite_queries` | Scopes + profile phrases (not long prompts) |
| `datacite_scope_score_adjustment` | Boost/demote DataCite hits per scope |
| `bigquery_route_hints` | `bigquery_interests` → registry dry-run targets |
| `profile_summary` | UI + `/library/discover?email=` |

## Pipeline difficulty tiers (`pipeline_difficulty.py`)

Maps professor asks to **how deep** the desk must go — use for benchmarks and Composer expectations.

| Tier | Professor analogy | Stack |
|------|-------------------|--------|
| **T1_instant** | GDELT / CoinGecko snapshot | `research_query_dataset(limit=N)` |
| **T2_vault** | OpenSea graph, Skynet harvest | describe + vault partition |
| **T3_guarded_remote** | USDT on-chain history | BigQuery dry_run → guarded run |
| **T4_procure_miss** | Obscure paper / niche panel | web_discover → probe → plan_collect |
| **T5_job_acquire** | Long scrape / backfill | yzu_submit_job → GDrive archive |

**Benchmark:** `PYTHONPATH=. .venv/bin/python scripts/research_data_mcp/professor_pipeline_benchmark.py`  
**Kong pilot matrix:** four cases (T1–T4) in `KONG_PILOT_MATRIX`.

## DataCite vs BigQuery vs vault

| Need | Route |
|------|--------|
| NFT / OpenSea / CoinGecko / Skynet | **vault** (`lab_fintech_stack`) |
| USDT / ERC-20 history | **bigquery** (`ethereum_usdt_transfers`) |
| Taiwan equity / governance | **twse_openapi** + MOPS procure |
| Comparable academic DOIs | **datacite** — scoped seeds only |

## Adding a new professor

1. Scrape CM row (specialties, journals, grants).
2. Browse Scholar / SSRN / personal site — add `ssrn_papers`, `working_papers`.
3. List **active grant** → `research_tracks` + `primary_direction`.
4. Map lab holdings → `lab_fintech_stack` + `registry_dataset_ids`.
5. Define 1–3 `datacite_scopes` with **short** `seed_queries` and filters.
6. Define `bigquery_interests` only when registry has a BQ-backed dataset.
7. Set `starter_prompts` to procure/extend intents, not “open file on Drive”.

## API

- `GET /library/faculty/profile?email=` — `profile_summary` (includes stacks, scopes)
- `GET /library/discover?email=&q=` — ranked search with profile expansion
