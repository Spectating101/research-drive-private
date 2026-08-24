# README — ChatGPT Full Stablecoin Research Audit Pack

**Zip name pattern:** `chatgpt_full_stablecoin_research_audit_20260713.zip`  
**Purpose:** Give ChatGPT the entire research substrate to redesign reconstruction of Professor Kong’s *original* longitudinal variables — **without** defending or patching the current `attention_proxy_index`.

## Start here

1. Read `docs/FULL_STABLECOIN_DATA_HANDOFF.md` (factual handoff).
2. Skim `audit_summaries/audit_summary.json` + `unexploited_or_partial_assets.csv`.
3. Open `audit_summaries/variable_lineage.csv` and `temporal_grain_audit.csv`.
4. Inspect extracted Skynet assets: `skynet_milestones_extracted.csv`, `skynet_audits_extracted.csv`, `skynet_scores_snapshot.csv`.
5. Read early framing: `docs_context/community_PROFESSOR_HANDOFF.md` and `community_METHODOLOGY.md`.
6. Use `source/` for complete builders/collectors; `config/` for maps/events; `package_20260707/` for published panels; `raw/` for harvest + community panels.

## Do / Don’t

**Do**

- Inventory what can support event-based security state vs historical scores.
- Inventory what can support community *growth* vs attention vs adoption.
- Flag temporal leakage and ambiguous zeros.

**Don’t**

- Defend `attention_proxy_index`.
- Auto-replace the research question.
- Rebuild or delete datasets in this pass.

## Original ask (reminder)

Longitudinal:

1. security / audit history  
2. community growth (esp. Twitter followers)

Both are sparse or missing as clean public panels; many proxies and event streams exist instead.

## Pack layout

```
README_CHATGPT_AUDIT.md          ← this file
docs/FULL_STABLECOIN_DATA_HANDOFF.md
docs/…                           ← other stablecoin docs
audit_summaries/                 ← CSV/JSON audits
source/                          ← Python builders & collectors
config/                          ← stablecoin_*.json
package_20260707/                ← frozen published package
raw/community/                   ← community attention substrate
raw/skynet_harvest_…/            ← canonical Skynet JSON harvest
raw/NOTES_EXCLUDED_LARGE_CACHES.md
```

## Large caches excluded from zip

`stablecoin_skynet/data/derived/defillama/` (~211MB) is inventoried but not fully copied. Rolled adoption/peg factors are inside `package_20260707/factors/`. GDELT overlay under `data_lake/` may be only partially present depending on host disk; lineage paths are recorded.
