"""Build an auditable candidate registry from reviewed coverage labels.

The input registry is never edited in place. Labels are classified as exact,
alias, orphaned, conflicting, already present, invalid, or changed. Optional
candidate and patch files make a small reviewed migration reversible.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

DIMENSIONS = (
    "unit",
    "universe/geography",
    "time_range",
    "frequency",
    "fields",
    "event_type",
)
DIMENSION_ALIASES = {
    "geography": "universe/geography",
    "universe": "universe/geography",
    "universe/geography": "universe/geography",
}
CONTAINER_KEYS = ("coverage_metadata", "evidence_coverage", "coverage", "dimensions")
ID_KEYS = ("dataset_id", "registry_id", "id")
ALIAS_KEYS = ("aliases", "legacy_ids", "alternate_ids")
LIST_KEYS = ("datasets", "labels", "records", "items")


class MigrationError(ValueError):
    """Unsafe or malformed migration input."""


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        return [item for item in (_clean(item) for item in value) if item is not None]
    if isinstance(value, dict):
        cleaned = {str(key): _clean(item) for key, item in value.items()}
        return {key: item for key, item in cleaned.items() if item is not None}
    return value


def _canonical(value: Any) -> str:
    return json.dumps(_clean(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dataset_id(record: Mapping[str, Any]) -> str | None:
    for key in ID_KEYS:
        value = _clean(record.get(key))
        if isinstance(value, str):
            return value
    return None


def _dimension(value: Any) -> str | None:
    key = str(value or "").strip()
    normalized = DIMENSION_ALIASES.get(key, key)
    return normalized if normalized in DIMENSIONS else None


def _aliases(record: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ALIAS_KEYS:
        value = record.get(key)
        if isinstance(value, str):
            values.append(value.strip())
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            values.extend(str(item).strip() for item in value if str(item).strip())
    return tuple(dict.fromkeys(item for item in values if item))


def _iter_records(payload: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(payload, list):
        yield from (item for item in payload if isinstance(item, Mapping))
        return
    if not isinstance(payload, Mapping):
        raise MigrationError("labels must be a JSON object or array")
    for key in LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            yield from (item for item in value if isinstance(item, Mapping))
            return
    if _dataset_id(payload):
        yield payload
        return
    for key, value in payload.items():
        if isinstance(value, Mapping):
            row = dict(value)
            row.setdefault("dataset_id", str(key))
            yield row


def _coverage(record: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    coverage: dict[str, Any] = {}
    errors: list[str] = []
    for container_key in CONTAINER_KEYS:
        container = record.get(container_key)
        if isinstance(container, Mapping):
            for key, value in container.items():
                dimension = _dimension(key)
                cleaned = _clean(value)
                if dimension and cleaned is not None:
                    coverage[dimension] = cleaned
    for key, value in record.items():
        dimension = _dimension(key)
        cleaned = _clean(value)
        if dimension and cleaned is not None:
            coverage[dimension] = cleaned
    claims = record.get("claims")
    if isinstance(claims, list):
        for index, claim in enumerate(claims):
            if not isinstance(claim, Mapping):
                errors.append(f"claims[{index}] is not an object")
                continue
            dimension = _dimension(claim.get("dimension") or claim.get("key") or claim.get("name"))
            value = _clean(claim.get("value"))
            if not dimension:
                errors.append(f"claims[{index}] has an unsupported dimension")
            elif value is None:
                errors.append(f"claims[{index}] has no value")
            elif dimension in coverage and _canonical(coverage[dimension]) != _canonical(value):
                errors.append(f"claims[{index}] conflicts with {dimension}")
            else:
                coverage[dimension] = value
    if not coverage:
        errors.append("no supported coverage dimensions")
    return coverage, errors


def normalize_labels(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labels: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, record in enumerate(_iter_records(payload)):
        source_id = _dataset_id(record)
        coverage, errors = _coverage(record)
        if not source_id:
            errors.append("missing dataset_id")
        if errors:
            rejected.append({"index": index, "dataset_id": source_id, "reasons": errors})
            continue
        provenance: dict[str, Any] = {}
        for key in ("provenance", "label_provenance", "review", "evidence"):
            value = record.get(key)
            if isinstance(value, Mapping):
                provenance.update(_clean(dict(value)))
        labels.append(
            {
                "source_id": source_id,
                "coverage": coverage,
                "provenance": provenance,
                "aliases": list(_aliases(record)),
            }
        )
    return labels, rejected


def _registry_rows(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = document.get("datasets")
    if not isinstance(rows, list):
        raise MigrationError("registry must contain a datasets array")
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise MigrationError(f"datasets[{index}] is not an object")
        dataset_id = _dataset_id(row)
        if not dataset_id:
            raise MigrationError(f"datasets[{index}] has no dataset_id")
        if dataset_id in seen:
            raise MigrationError(f"duplicate registry dataset_id: {dataset_id}")
        seen.add(dataset_id)
    return rows


def _existing(row: Mapping[str, Any]) -> dict[str, Any]:
    container = row.get("coverage_metadata")
    if not isinstance(container, Mapping):
        return {}
    return {
        dimension: _clean(container[dimension])
        for dimension in DIMENSIONS
        if dimension in container and _clean(container[dimension]) is not None
    }


def migrate(
    registry: Mapping[str, Any],
    label_payload: Any,
    *,
    source_sha256: str | None = None,
    selected_ids: set[str] | None = None,
    max_changes: int | None = None,
) -> dict[str, Any]:
    candidate = copy.deepcopy(dict(registry))
    rows = _registry_rows(candidate)
    by_id = {_dataset_id(row): row for row in rows}
    alias_index: dict[str, set[str]] = {}
    for row in rows:
        target = _dataset_id(row)
        for alias in _aliases(row):
            alias_index.setdefault(alias, set()).add(target)

    labels, rejected = normalize_labels(label_payload)
    details: list[dict[str, Any]] = []
    forward: list[dict[str, Any]] = []
    rollback: list[dict[str, Any]] = []
    changed = 0

    for label in labels:
        source_id = label["source_id"]
        if selected_ids and source_id not in selected_ids:
            details.append({"source_dataset_id": source_id, "classification": "not_selected"})
            continue
        target: str | None = source_id if source_id in by_id else None
        match_type = "exact_match" if target else None
        if not target:
            candidates = set(alias_index.get(source_id, set()))
            for alias in label["aliases"]:
                candidates.update(alias_index.get(alias, set()))
                if alias in by_id:
                    candidates.add(alias)
            if len(candidates) == 1:
                target = next(iter(candidates))
                match_type = "alias_match"
            elif len(candidates) > 1:
                details.append(
                    {
                        "source_dataset_id": source_id,
                        "classification": "conflict",
                        "reason": "alias maps to multiple targets",
                        "targets": sorted(candidates),
                    }
                )
                continue
        if not target:
            details.append(
                {
                    "source_dataset_id": source_id,
                    "classification": "orphaned",
                    "coverage_dimensions": sorted(label["coverage"]),
                }
            )
            continue

        row = by_id[target]
        existing = _existing(row)
        conflicts = {
            dimension: {"existing": existing[dimension], "incoming": incoming}
            for dimension, incoming in label["coverage"].items()
            if dimension in existing and _canonical(existing[dimension]) != _canonical(incoming)
        }
        if conflicts:
            details.append(
                {
                    "source_dataset_id": source_id,
                    "target_dataset_id": target,
                    "match_type": match_type,
                    "classification": "conflict",
                    "reason": "incoming coverage contradicts existing explicit coverage",
                    "conflicts": conflicts,
                }
            )
            continue
        if all(
            dimension in existing and _canonical(existing[dimension]) == _canonical(incoming)
            for dimension, incoming in label["coverage"].items()
        ):
            details.append(
                {
                    "source_dataset_id": source_id,
                    "target_dataset_id": target,
                    "match_type": match_type,
                    "classification": "already_present",
                }
            )
            continue
        if max_changes is not None and changed >= max_changes:
            details.append(
                {
                    "source_dataset_id": source_id,
                    "target_dataset_id": target,
                    "match_type": match_type,
                    "classification": "change_deferred",
                    "reason": f"max_changes={max_changes} reached",
                }
            )
            continue

        before = copy.deepcopy(row.get("coverage_metadata"))
        after = copy.deepcopy(before) if isinstance(before, Mapping) else {}
        after.update(copy.deepcopy(label["coverage"]))
        provenance = copy.deepcopy(after.get("provenance")) if isinstance(after.get("provenance"), Mapping) else {}
        provenance.update(copy.deepcopy(label["provenance"]))
        provenance.setdefault("method", "reviewed_label_migration")
        provenance.setdefault("source_dataset_id", source_id)
        if source_sha256:
            provenance.setdefault("source_label_sha256", source_sha256)
        after["provenance"] = provenance
        row["coverage_metadata"] = after
        changed += 1
        details.append(
            {
                "source_dataset_id": source_id,
                "target_dataset_id": target,
                "match_type": match_type,
                "classification": "changed",
                "coverage_dimensions": sorted(label["coverage"]),
            }
        )
        forward.append({"dataset_id": target, "field": "coverage_metadata", "before": before, "after": after})
        rollback.append({"dataset_id": target, "field": "coverage_metadata", "before": after, "after": before})

    counts: dict[str, int] = {}
    for item in details:
        key = item["classification"]
        counts[key] = counts.get(key, 0) + 1
    counts["rejected_invalid"] = len(rejected)
    return {
        "candidate_registry": candidate,
        "report": {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "registry_dataset_count": len(rows),
            "normalized_label_count": len(labels),
            "source_label_sha256": source_sha256,
            "counts": counts,
            "details": details,
            "rejected": rejected,
            "changed_dataset_ids": [item["dataset_id"] for item in forward],
        },
        "forward_patch": forward,
        "rollback_patch": rollback,
    }


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MigrationError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MigrationError(f"invalid JSON in {path}: {exc}") from exc


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe(inputs: Iterable[Path], output: Path | None) -> None:
    if output and any(output.resolve() == item.resolve() for item in inputs):
        raise MigrationError(f"refusing to overwrite input file: {output}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--registry", type=Path, required=True)
    result.add_argument("--labels", type=Path, required=True)
    result.add_argument("--report", type=Path, required=True)
    result.add_argument("--candidate", type=Path)
    result.add_argument("--forward-patch", type=Path)
    result.add_argument("--rollback-patch", type=Path)
    result.add_argument("--dataset-id", action="append", dest="dataset_ids")
    result.add_argument("--max-changes", type=int)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.max_changes is not None and args.max_changes < 0:
        raise MigrationError("--max-changes must be non-negative")
    inputs = (args.registry, args.labels)
    for output in (args.report, args.candidate, args.forward_patch, args.rollback_patch):
        _safe(inputs, output)
    result = migrate(
        _load(args.registry),
        _load(args.labels),
        source_sha256=_hash(args.labels),
        selected_ids=set(args.dataset_ids or ()) or None,
        max_changes=args.max_changes,
    )
    _write(args.report, result["report"])
    if args.candidate:
        _write(args.candidate, result["candidate_registry"])
    if args.forward_patch:
        _write(args.forward_patch, result["forward_patch"])
    if args.rollback_patch:
        _write(args.rollback_patch, result["rollback_patch"])
    print(json.dumps(result["report"]["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
