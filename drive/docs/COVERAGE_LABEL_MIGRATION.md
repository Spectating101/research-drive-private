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

The input registry is never edited in place. The command refuses output paths
that equal either input path.

## Accepted label shapes

The tool accepts:

- an array of dataset label objects;
- an object containing `datasets`, `labels`, `records`, or `items`;
- an object keyed by dataset id;
- dimension values under `coverage_metadata`, `evidence_coverage`, `coverage`,
  or `dimensions`;
- direct dimension fields;
- a `claims` array containing `dimension` and `value`.

Supported dimensions are:

```text
unit
universe/geography  (aliases: geography, universe)
time_range
frequency
fields
event_type
```

## Classification contract

Every normalized label is classified as one of:

- `changed` — safely applied to the candidate;
- `already_present` — the same explicit coverage already exists;
- `orphaned` — no current registry target exists;
- `alias_match` — reported through `match_type` when one unique legacy id maps;
- `conflict` — an alias is ambiguous or incoming coverage contradicts existing
  explicit coverage;
- `change_deferred` — a sample bound such as `--max-changes` was reached;
- `not_selected` — excluded by repeated `--dataset-id` filters;
- `rejected_invalid` — missing identity, unsupported dimensions, or malformed
  claims.

Orphaned labels are evidence of registry drift, not an automatic migration
failure. They stay in the report and are never attached to a guessed target.

## Review sequence

1. Preserve and checksum the complete label package and provenance chain.
2. Snapshot and checksum the current authoritative registry.
3. Run a full dry-run report without a candidate.
4. Review all aliases, conflicts, orphaned labels, and visible unlabeled rows.
5. Create a candidate limited to five to ten reviewed datasets.
6. Compare assessment outputs before and after using a fixed research-question
   matrix.
7. Inspect the forward and rollback patches.
8. Run registry, Discover-assessment, and release-contract tests.
9. Promote only through the registry's transactional authority path.
10. Preserve the report, hashes, candidate, patches, test output, and decision.

## Non-negotiable rules

- Never overwrite the live registry with the CLI output.
- Never resolve an orphan by title similarity alone.
- Never overwrite contradictory explicit coverage automatically.
- Never infer coverage from `query_ready`, `analysis_readiness`, descriptions, or
  broad `field_coverage` labels.
- Never treat successful migration as proof that a research need is covered.
- `completed != archived != registered != query_ready` remains unchanged.
