"""Whether a choice changes the finding, measured instead of judged.

The desk resolves routine choices itself and stops for consequential ones. Which
is which was the agent's opinion, and an opinion is not auditable: a researcher
who asks "why didn't you ask me about that?" deserves a number, not a category.

A bounded preview costs about two seconds, so both branches can simply be run and
compared. Excluding a forward-return column leaves the output identical and needs
no one's attention. Treating a percentage as a fraction moves the median by two
orders of magnitude and needs the researcher. The same rule decides both, and the
threshold that separates them is stated once here rather than re-judged per
decision.

This does not apply to choices with no cheap second run — a different collection,
a different source. Those stay judgements, and should say so.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

MATERIAL_ROW_SHIFT = 0.01
MATERIAL_VALUE_SHIFT = 0.01
NEGLIGIBLE = 1e-12


def _summarise(frame) -> dict[str, Any]:
    import pandas as pd

    out: dict[str, Any] = {"rows": int(len(frame)), "metrics": {}}
    for name in frame.columns:
        column = frame[name]
        if not pd.api.types.is_numeric_dtype(column):
            continue
        out["metrics"][str(name)] = {
            "median": _finite_float(column.median()),
            "mean": _finite_float(column.mean()),
        }
    return out


def _finite_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _relative_shift(before: float | None, after: float | None) -> float | None:
    if before is None or after is None:
        return None
    scale = max(abs(before), abs(after))
    if scale < NEGLIGIBLE:
        return 0.0
    return abs(after - before) / scale


def compare(baseline_frame, variant_frame,
            row_threshold: float = MATERIAL_ROW_SHIFT,
            value_threshold: float = MATERIAL_VALUE_SHIFT) -> dict[str, Any]:
    """What moved, by how much, and whether that is worth the researcher's attention."""
    before, after = _summarise(baseline_frame), _summarise(variant_frame)
    row_shift = _relative_shift(float(before["rows"]), float(after["rows"])) or 0.0
    moved: list[dict[str, Any]] = []
    for name, stats in before["metrics"].items():
        other = after["metrics"].get(name)
        if not other:
            moved.append({"metric": name, "shift": None, "note": "absent from the variant"})
            continue
        # A median alone misses a rescale on a column whose median is zero:
        # supply_growth_wow_pct has median 0.0, so dividing it by 100 moves
        # nothing a median can see while the mean goes 311,165 -> 3,111. Take
        # whichever summary moved most.
        candidates = [
            ("median", stats["median"], other["median"]),
            ("mean", stats["mean"], other["mean"]),
        ]
        scored = [(name_, before_, after_, _relative_shift(before_, after_))
                  for name_, before_, after_ in candidates]
        scored = [row for row in scored if row[3] is not None]
        if not scored:
            continue
        summary, before_value, after_value, shift = max(scored, key=lambda row: row[3])
        moved.append({
            "metric": name,
            "summary": summary,
            "before": before_value,
            "after": after_value,
            "shift": shift,
        })
    material = [m for m in moved if m.get("shift") is not None and m["shift"] > value_threshold]
    absent = [m for m in moved if m.get("shift") is None]
    verdict = "material" if (row_shift > row_threshold or material or absent) else "no material change"
    return {
        "verdict": verdict,
        "absent": absent,
        "rows_before": before["rows"],
        "rows_after": after["rows"],
        "row_shift": row_shift,
        "moved": sorted(moved, key=lambda m: -(m.get("shift") or 0)),
        "material": material,
        "row_threshold": row_threshold,
        "value_threshold": value_threshold,
    }


def explain(delta: dict[str, Any]) -> str:
    """One line a researcher can be shown, or asked to argue with."""
    if delta.get("verdict") != "material":
        return "the output is unchanged, so this was resolved without asking you"
    reasons = []
    if (delta.get("row_shift") or 0) > delta.get("row_threshold", MATERIAL_ROW_SHIFT):
        reasons.append(
            f"{delta['rows_before']:,} rows become {delta['rows_after']:,}")
    for item in delta.get("absent", [])[:2]:
        reasons.append(f"{item['metric']} is absent from the variant")
    for item in delta.get("material", [])[:2]:
        if item.get("shift") is not None:
            reasons.append(
                f"{item['metric']} {item.get('summary', 'median')} moves from "
                f"{item['before']:.6g} to {item['after']:.6g}")
    return " · ".join(reasons) or "the output changes"


def compare_specs(repo_root: Path | str, baseline: dict[str, Any], variant: dict[str, Any],
                  thread_id: str = "delta", **thresholds) -> dict[str, Any]:
    """Run both specs through the engine and compare what came out."""
    import pandas as pd

    from scripts.research_data_mcp.synthesis_executor import execute

    repo_root = Path(repo_root)
    frames = []
    for index, spec in enumerate((baseline, variant)):
        execute(repo_root, f"delta_{index}", {"execution_spec": spec, "thread_id": thread_id})
        frames.append(pd.read_parquet(
            repo_root / "data_lake/synthesis/thread_outputs" / thread_id / f"delta_{index}" / "output.parquet"))
    return compare(frames[0], frames[1], **thresholds)
