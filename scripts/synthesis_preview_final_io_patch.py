#!/usr/bin/env python3
"""Apply final freeze-grade Synthesis Preview I/O/authority edits atomically.

The target executor is large, so this patcher edits only uniquely asserted source
regions. It aborts on drift or ambiguity rather than replacing the whole file.
Delete this staging script after the product commit is green.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, value: str) -> None:
    (ROOT / path).write_text(value, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> bool:
    value = text(path)
    if new in value:
        return False
    count = value.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one guarded fragment, found {count}")
    write(path, value.replace(old, new, 1))
    return True


def replace_region(path: str, start: str, end: str, replacement: str) -> bool:
    value = text(path)
    if replacement in value:
        return False
    if value.count(start) != 1 or value.count(end) != 1:
        raise SystemExit(
            f"{path}: region markers drifted: start={value.count(start)} end={value.count(end)}"
        )
    left = value.index(start)
    right = value.index(end, left)
    write(path, value[:left] + replacement + value[right:])
    return True


def main() -> None:
    changed: list[str] = []

    executor = "drive/scripts/research_data_mcp/synthesis_executor.py"
    if replace_region(
        executor,
        "def _non_finite_report(path: Path, columns: list[str]) -> dict[str, int]:",
        "\ndef preflight_execution_spec(",
        '''def _non_finite_report(
    path: Path,
    columns: list[str],
    *,
    row_cap: int | None = None,
) -> dict[str, int]:
    """Count inf/-inf per aggregate column.

    ``row_cap`` makes the diagnostic physically bounded for Preview. Silence
    still means unreadable/absent columns, never that the entire source is clean.
    """
    if not columns:
        return {}
    try:
        import numpy as np

        if row_cap:
            from scripts.research_data_mcp.synthesis.bounded_read import read_bounded_frame

            frame = read_bounded_frame(path, int(row_cap))[0].head(int(row_cap))
        else:
            import pandas as pd

            frame = pd.read_parquet(path) if str(path).endswith(".parquet") else pd.read_csv(path, low_memory=False)
    except Exception:
        return {}
    found: dict[str, int] = {}
    for column in columns:
        if column not in frame.columns:
            continue
        import pandas as pd

        series = pd.to_numeric(frame[column], errors="coerce")
        count = int(np.isinf(series).sum())
        if count:
            found[column] = count
    return found

''',
    ):
        changed.append(executor)

    if replace_once(
        executor,
        '''def preflight_execution_spec(
    repo_root: Path,
    spec: dict[str, Any],
    *,
    retention_floor_pct: float = DEFAULT_JOIN_RETENTION_FLOOR_PCT,
) -> dict[str, Any]:''',
        '''def preflight_execution_spec(
    repo_root: Path,
    spec: dict[str, Any],
    *,
    retention_floor_pct: float = DEFAULT_JOIN_RETENTION_FLOOR_PCT,
    row_cap: int | None = None,
) -> dict[str, Any]:''',
    ):
        changed.append(executor)

    if replace_once(
        executor,
        '''        try:
            frame = _read_frame(path)
        except Exception as exc:  # noqa: BLE001
            issues.append({"code": "unreadable_input", "dataset_id": dataset_id, "detail": str(exc)[:400]})
            return None
        numeric_by_dataset[dataset_id] = {
            str(c) for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])
        }''',
        '''        try:
            if row_cap:
                from scripts.research_data_mcp.synthesis.bounded_read import read_bounded_frame

                frame = read_bounded_frame(path, int(row_cap))[0].head(int(row_cap))
            else:
                frame = _read_frame(path)
        except Exception as exc:  # noqa: BLE001
            issues.append({"code": "unreadable_input", "dataset_id": dataset_id, "detail": str(exc)[:400]})
            return None
        numeric_by_dataset[dataset_id] = {
            str(c) for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])
        }''',
    ):
        changed.append(executor)

    if replace_once(
        executor,
        '''        report = _non_finite_report(input_path, agg_cols)
        for column, count in report.items():
            warnings.append(
                f"{normalized['input_dataset_id']}.{column}: {count} non-finite value(s) (inf/-inf) "
                "in the source; aggregates over this column inherit them"
            )''',
        '''        report = _non_finite_report(input_path, agg_cols, row_cap=row_cap)
        for column, count in report.items():
            scope = (
                f"within the bounded preflight window (first {int(row_cap)} rows)"
                if row_cap
                else "in the source"
            )
            warnings.append(
                f"{normalized['input_dataset_id']}.{column}: {count} non-finite value(s) (inf/-inf) "
                f"{scope}; aggregates over observed non-finite values inherit them"
            )''',
    ):
        changed.append(executor)

    if replace_once(
        executor,
        '''        "note": (
            "Preflight only — does not execute or materialise. "
            + ("Fix issues before proposing." if not ok else "Spec is structurally runnable when local inputs are present.")
        ),''',
        '''        "bounded_row_cap": int(row_cap) if row_cap else None,
        "note": (
            "Bounded preflight only — schema/dtype diagnostics use a capped row window; no output is materialised. "
            if row_cap
            else "Preflight only — does not execute or materialise. "
        ) + ("Fix issues before proposing." if not ok else "Spec is structurally runnable when local inputs are present."),''',
    ):
        changed.append(executor)

    preview = "drive/scripts/research_data_mcp/synthesis_preview.py"
    if replace_region(
        preview,
        "def _bounded_primary_frame(path: Path, limit: int):",
        "\ndef _aggregate_preview(",
        '''def _bounded_primary_frame(path: Path, limit: int):
    from scripts.research_data_mcp.synthesis.bounded_read import read_bounded_frame

    return read_bounded_frame(path, limit)

''',
    ):
        changed.append(preview)

    if replace_once(
        preview,
        "MAX_OUTPUT_ROW_LIMIT = 100\n# Non-streamable/unknown primary formats may still be previewed when genuinely\n# small, but never by reading an arbitrarily large file merely to take head().\nMAX_FALLBACK_PRIMARY_BYTES = 16 * 1024 * 1024",
        "MAX_OUTPUT_ROW_LIMIT = 100\n# Right-hand join inputs are intentionally read with production join semantics.\n# Keep that full-side read finite and substantially below the 512 MiB Build cap.\nMAX_PREVIEW_JOIN_INPUT_BYTES = 64 * 1024 * 1024",
    ):
        changed.append(preview)

    if replace_once(
        preview,
        "    preflight = preflight_execution_spec(root, dict(execution_spec or {}))",
        "    preflight = preflight_execution_spec(root, dict(execution_spec or {}), row_cap=in_limit)",
    ):
        changed.append(preview)

    if replace_once(
        preview,
        '''    input_revisions = input_revision_snapshot(root, spec)
    authority_hash = preview_authority_hash(spec_hash, input_revisions)

    registry = _load_registry(root)''',
        '''    input_revisions = input_revision_snapshot(root, spec)
    authority_hash = preview_authority_hash(spec_hash, input_revisions)
    oversized_join_inputs = [
        row for row in input_revisions
        if row.get("dataset_id") != spec["input_dataset_id"]
        and int(row.get("size_bytes") or 0) > MAX_PREVIEW_JOIN_INPUT_BYTES
    ]
    if oversized_join_inputs:
        names = ", ".join(str(row.get("dataset_id") or "unknown") for row in oversized_join_inputs)
        raise ValueError(
            f"bounded Preview refuses full right-hand join input(s) above "
            f"{MAX_PREVIEW_JOIN_INPUT_BYTES} bytes: {names}"
        )

    registry = _load_registry(root)''',
    ):
        changed.append(preview)

    if replace_once(
        preview,
        '''        "preflight": {
            "warnings": list(preflight.get("warnings") or []),
            "join_probes": list(preflight.get("join_probes") or []),
        },''',
        '''        "preflight": {
            "warnings": list(preflight.get("warnings") or []),
            "join_probes": list(preflight.get("join_probes") or []),
            "bounded_row_cap": preflight.get("bounded_row_cap"),
            "right_input_full_read_cap_bytes": MAX_PREVIEW_JOIN_INPUT_BYTES,
        },''',
    ):
        changed.append(preview)

    gateway = "drive/scripts/research_data_mcp/gateway.py"
    if replace_once(
        gateway,
        '    def _synthesis_thread_submit_approval(self, thread_id: str) -> dict:',
        '    def _synthesis_thread_submit_approval(\n        self, thread_id: str, *, expected_authority_hash: str = ""\n    ) -> dict:',
    ):
        changed.append(gateway)

    if replace_once(
        gateway,
        '''        accepted_hash = str(state.get("accepted_spec_hash") or "")
        if not accepted_hash:
            raise ValueError("execution spec has not been accepted as a reviewed revision")
        execution = state.get("execution") or {}''',
        '''        accepted_hash = str(state.get("accepted_spec_hash") or "")
        if not accepted_hash:
            raise ValueError("execution spec has not been accepted as a reviewed revision")
        if expected_authority_hash:
            preview = state.get("preview") if isinstance(state.get("preview"), dict) else {}
            if (
                preview.get("status") != "succeeded"
                or preview.get("spec_hash") != accepted_hash
                or preview.get("authority_hash") != expected_authority_hash
            ):
                raise ValueError(
                    "execution approval refused: Preview authority changed before job creation; rerun Preview"
                )
        execution = state.get("execution") or {}''',
    ):
        changed.append(gateway)

    authority = "drive/scripts/research_data_mcp/synthesis_execution_authority.py"
    if replace_once(
        authority,
        "    submitted = gateway._synthesis_thread_submit_approval(thread_id)",
        '''    submitted = gateway._synthesis_thread_submit_approval(
        thread_id,
        expected_authority_hash=str(fresh_authority.get("authority_hash") or ""),
    )''',
    ):
        changed.append(authority)

    print("patched:", ", ".join(dict.fromkeys(changed)) if changed else "already applied")


if __name__ == "__main__":
    main()
