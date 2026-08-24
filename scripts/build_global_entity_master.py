#!/usr/bin/env python3
"""Merge Asia + US entity masters into a single global mapping for spine / GDELT bridge."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "kernel") not in sys.path:
    sys.path.insert(0, str(REPO / "kernel"))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
ASIA_ROOT = ROOT / "data_lake/entity_mapping/asia"
US_ROOT = ROOT / "data_lake/entity_mapping/us"
OUT_ROOT = ROOT / "data_lake/entity_mapping/global"


def _latest_csv(root: Path, name: str) -> Path | None:
    if (root / "latest").is_symlink():
        p = root / "latest" / name
        if p.is_file():
            return p
    runs = sorted([d for d in root.iterdir() if d.is_dir() and d.name != "latest"], reverse=True)
    for run in runs:
        p = run / name
        if p.is_file():
            return p
    return None


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def build_global(*, run_id: str | None = None) -> dict:
    run = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = OUT_ROOT / run
    out_dir.mkdir(parents=True, exist_ok=True)

    asia_path = _latest_csv(ASIA_ROOT, "asia_entity_master.csv")
    us_path = _latest_csv(US_ROOT, "us_entity_master.csv")
    merged: dict[str, dict[str, str]] = {}
    for row in _read_csv(asia_path) if asia_path else []:
        sym = str(row.get("yahoo_symbol") or "").strip()
        if sym:
            merged[sym] = row
    for row in _read_csv(us_path) if us_path else []:
        sym = str(row.get("yahoo_symbol") or "").strip()
        if sym and sym not in merged:
            merged[sym] = row

    rows = list(merged.values())
    out_path = out_dir / "entity_master.csv"
    if rows:
        with out_path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    summary = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "run_id": run,
        "asia_source": str(asia_path.relative_to(ROOT)) if asia_path else None,
        "us_source": str(us_path.relative_to(ROOT)) if us_path else None,
        "total_symbols": len(rows),
        "output": str(out_path.relative_to(ROOT)) if out_path.is_file() else None,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    latest = OUT_ROOT / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(out_dir.name)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = build_global(run_id=args.run_id or None)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
