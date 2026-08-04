# Reviewed coverage-label migration

## Purpose

Discover's held-evidence assessment deliberately returns `insufficient_metadata`
when registry rows do not explicitly declare coverage for the requested unit,
geography or universe, time range, frequency, fields, or event type.

Reviewed labels must therefore enter the registry through a bounded migration,
not a bulk manual edit. The migration must preserve registry authority, report
orphaned historical labels as expected drift, reject contradictions, and create a
reversible candidate before any live write.

## Security and repository boundary

This repository contains the migration tool and tests only. Do **not** commit:

- faculty-private registry snapshots;
- raw reviewed label packages;
- worker outputs containing research context;
- principal tokens or token files;
- systemd drop-ins or environment files containing secrets.

Keep the reviewed evidence package in durable private storage and pass its path
to the tool locally.

## Tool

```bash
PYTHONPATH=drive:kernel python \
  drive/scripts/research_data_mcp/coverage_label_migration.py \
  --registry /private/path/current_registry.json \
  --labels /private/path/final_approved.json \
  --report /private/path/migration_report.json \
  --candidate /private/path/candidate_registry.json \
  --forward-patch /private/path/forward_patch.json \
  --rollback-patch /private/path/rollback_patch.json \
  --max-changes 10
```

The input registry is never edited in place. All output paths must be distinct
from both inputs and from one another.

## Accepted label shapes

The tool accepts:

- an array of dataset label objects;
- an object containing `datasets`, `labels`, `records`, or `items`;
- an object keyed by dataset id;
- dimension values under `coverage_metadata`, `evidence_coverage`, `coverage`,
  or `dimensions`;
- direct dimension fields;
- a `claims` array containing `dimension` and `value`;
- claim-per-record rows containing `dataset_id`, `dimension`, and `value`.

Repeated records are aggregated by dataset id before the change bound is applied.
Duplicate declarations for the same dataset and dimension must agree exactly;
disagreements are rejected rather than resolved by ordering.

Supported dimensions are:

```text
unit
universe/geography  (aliases: geography, universe)
time_range
frequency
fields
event_type
```

## Authority and conflict contract

The migration checks the same explicit coverage surfaces used by Discover:

- `coverage_metadata`;
- `evidence_coverage`;
- `coverage`;
- `dimensions`;
- direct row-level coverage dimensions.

Existing cross-surface contradictions block migration for that dataset. Incoming
claims never overwrite a contradictory explicit declaration.

Every normalized dataset label is classified as one of:

- `changed` — safely applied to the candidate;
- `already_present` — the same explicit coverage already exists;
- `orphaned` — no current registry target exists;
- `alias_match` — reported through `match_type` when one unique legacy id maps;
- `conflict` — an alias is ambiguous, the registry is already contradictory, or
  incoming coverage contradicts existing explicit coverage;
- `change_deferred` — a dataset-level bound such as `--max-changes` was reached;
- `not_selected` — excluded by repeated `--dataset-id` filters;
- `rejected_invalid` — missing identity, unsupported dimensions, malformed
  claims, or duplicate records that disagree.

Orphaned labels are evidence of registry drift, not an automatic migration
failure. They stay in the report and are never attached to a guessed target.

## Drift evidence

Every report records:

- the raw label-file SHA-256;
- a deterministic input-registry SHA-256;
- a deterministic candidate-registry SHA-256;
- whether the candidate differs from the reviewed input;
- input claim-record count;
- normalized dataset-label count;
- changed dataset ids and reversible patches.

The input-registry fingerprint must still match immediately before promotion.

## Review sequence

1. Preserve and checksum the complete label package and provenance chain.
2. Snapshot and checksum the current authoritative registry.
3. Run a full dry-run report without a candidate.
4. Review all aliases, conflicts, orphaned labels, and visible unlabeled rows.
5. Create a candidate limited to five to ten reviewed datasets.
6. Compare assessment outputs before and after using a fixed research-question
   matrix.
7. Inspect the fingerprints and forward and rollback patches.
8. Run registry, Discover-assessment, and release-contract tests.
9. Confirm the authoritative registry fingerprint has not drifted.
10. Promote only through the registry's transactional authority path.
11. Preserve the report, hashes, candidate, patches, test output, and decision.

## Non-negotiable rules

- Never overwrite the live registry with the CLI output.
- Never resolve an orphan by title similarity alone.
- Never overwrite contradictory explicit coverage automatically.
- Never infer coverage from `query_ready`, `analysis_readiness`, descriptions, or
  broad `field_coverage` labels.
- Never treat successful migration as proof that a research need is covered.
- `completed != archived != registered != query_ready` remains unchanged.
