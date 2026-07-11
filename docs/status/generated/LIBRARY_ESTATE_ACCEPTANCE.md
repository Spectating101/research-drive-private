# Library Data Estate — acceptance

Accepted product composition for the Library surface.

## Main canvas

Library is the lab's owned data estate and research memory.

- Root collections are ordered by estate role, not research priority: **Research panels → Acquired data → Reference data → Connected sources → Data pipelines → Research campaigns → Other assets**.
- Physical IDs and vault paths are unchanged; only user-facing collection language is normalized.
- The permanent lane-chip wall, registry-first path banner, duplicate Upload action, and hard-coded Refinitiv-first lane priority are removed from the primary canvas.
- Collection cards expose purpose plus honest dataset/query-ready counts.
- Asset rows scan as title/readiness → purpose → known coverage/grain/source → asset type.
- Missing metadata is omitted from row chrome rather than filled with synthetic copy.
- Filter and Sort are subordinate counted disclosures.

## Readiness authority

Unknown or unrecognized readiness never defaults to Query ready.

- `instant` / `instant_or_minutes` → Query ready
- `connected` / `dry_run_before_execution` / BigQuery backend → Connected
- `metadata_search` / `metadata_only` → Metadata only
- `procurement_planning` → Queued
- `sample_now_full_later` → Review
- `failed` → Failed
- all unknown/unrecognized states → Readiness unknown

This contract is covered by `datasetMeta.test.js` and included in the standard unit-test command.

## Library inspector

Library keeps a right inspector because retaining the estate browser helps bounded asset inspection.

Dataset hierarchy:

1. human identity, asset type, readiness;
2. **Can I use this?**;
3. **Useful for**;
4. coverage and grain;
5. join keys;
6. provenance;
7. deterministic **Still unknown** gaps;
8. collapsed Technical details.

Raw `dataset_id`, registry readiness, backend, vault path, and query path live under Technical details rather than leading the header.

Only Query ready assets expose **Preview rows** as the primary action. Connected, Metadata only, and Readiness unknown assets use **Ask about access** and do not pretend an instant query path exists.

Collection hierarchy:

- collection/library identity;
- counts by usable state;
- one Add data section: Upload file, Add URL / DOI, Find missing data;
- destination and item counts under Technical details;
- one contextual Ask footer.

The old four-row STATUS / USE NOW / RISK / NEXT matrix and duplicate Branch actions + Upload footer are not used for Library.

## Rendered review

Reviewed at 1440×900 and 390×1200 across:

1. Library root;
2. Research panels collection;
3. selected Query ready derived panel;
4. selected Metadata only acquired asset;
5. selected Connected BigQuery asset;
6. selected Readiness unknown registry asset;
7. mobile root;
8. mobile selected Query ready asset.

The estate browser and inspector are visually approved. Global mobile navigation and lower-sheet polish remain part of the later cross-surface responsive pass.
