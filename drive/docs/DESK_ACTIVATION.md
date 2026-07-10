# Desk activation backlog (operational — not inventory)

**This is not `DATABANK_STATE.md`.**  
Read [`DATABANK_STATE.md`](DATABANK_STATE.md) for neutral truth: what exists, where it lives, coverage axes.

This file lists **activation work** — making the databank live, queryable, and visible.  
**Priorities should be ranked per researcher** via `research_faculty_profile` (email/slug), not globally.

```text
Neutral truth     → DATABANK_STATE.md + platform_progress.json
Profiled advice   → Composer + research_faculty_profile + chat context
Operational queue → this file (default ordering when no profile is bound)
```

Machine-readable snapshot: `drive/docs/status/generated/platform_progress.json`  
Regenerate: `python3 drive/scripts/sync_drive_platform_state.py`

---

## Default activation queue (unprofiled desk)

Use only when no faculty profile is bound. Re-order after `research_faculty_profile`.

| Priority | Task | Why |
|---------:|------|-----|
| 1 | Keep `:8765` API + worker up | Query and collect depend on it |
| 2 | Query-path smoke for all instant cards | `platform_progress.json` → `instant_path_miss` |
| 3 | Fix stale `default_run_id` / USB symlink paths | ticker_week panels, GDELT CSV on bulk root |
| 4 | Map unmapped registry IDs → partitions | ~93 cards; improves Drive semantics |
| 5 | Expand event↔instrument bridge | spine GDELT↔RIC match rate (~11%) |
| 6 | Materialize high-value metadata → instant | pick per faculty domain, not bulk |
| 7 | Research Drive UI shows full catalog | 150 cards / 22 partitions / live connectors |

---

## Incomplete / partial items (2026-07-06)

See `platform_progress.json` for the live list. Typical categories:

| Kind | Meaning |
|------|---------|
| `instant_path` | Registry says instant but parquet/CSV path does not resolve |
| `partition_map` | Card exists but no `collection_partitions` entry |
| `materialization` | `metadata_search` only — discoverable, not query-ready |

**Known instant path misses (fix `default_run_id` or promote latest run):**

- `ticker_week_country_broadcast_panel`
- `ticker_week_entity_residual_panel`

**Not broken — by design:**

- 104 `metadata_search` cards (procurement catalog)
- Live connectors (BigQuery, DataCite, HF) until a job materializes rows

---

## Synthesis panels (built)

| dataset_id | Build script |
|------------|--------------|
| `pit_index_revision_momentum` | `drive/scripts/build_pit_revision_momentum_panel.py` |
| `jkse_pit_idn_microstructure_revisions` | `drive/scripts/build_jkse_pit_idn_microstructure_revisions.py` |

Additional recipes: `drive/config/synthesis_profiles.json` — run via `research_synthesis_run`.

**Profile note:** A Taiwan-focused professor should not be steered to JKSE×IDN first; a crypto professor should see stablecoin synthesis. Bind profile before recommending.

---

## Commands

```bash
# Sync docs + audits + platform_progress.json into drive/
python3 drive/scripts/sync_drive_platform_state.py

# Coverage only
python3 drive/scripts/databank_coverage_report.py
python3 drive/scripts/databank_research_coverage.py

# API health + platform snapshot
curl -s http://127.0.0.1:8765/health | jq .
curl -s http://127.0.0.1:8765/library/platform/state | jq .
```

---

## Faculty-profiled recommendation flow

```text
1. POST /library/desk/warm  (or chat open)
2. research_faculty_profile(email=…)
3. research_discover_search(query aligned to profile domains)
4. Suggest next collect OR query from instant catalog
5. Log procurement outcome → registry promote
```

The desk should say **what you have** neutrally; **what you should do next** comes from the profiled research question.
