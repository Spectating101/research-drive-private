#!/usr/bin/env python3
"""Normalize Capital IQ / Compustat CSV exports into na_fundamentals_annual.parquet."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "kernel") not in sys.path:
    sys.path.insert(0, str(REPO / "kernel"))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
SCHEMA = ROOT / "config/compustat_export_schema.json"


def _resolve_columns(df, aliases: dict[str, list[str]]) -> dict[str, str]:
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    resolved: dict[str, str] = {}
    for canonical, names in aliases.items():
        for name in names:
            key = name.strip().lower()
            if key in lower_map:
                resolved[canonical] = lower_map[key]
                break
    return resolved


def _read_table(path: Path):
    import pandas as pd

    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if path.suffix.lower() == ".zip":
        import zipfile
        from io import BytesIO

        with zipfile.ZipFile(path) as zf:
            inner = next(n for n in zf.namelist() if n.lower().endswith((".csv", ".txt")))
            return pd.read_csv(BytesIO(zf.read(inner)), low_memory=False)
    return pd.read_csv(path, low_memory=False)


def ingest_exports(raw_root: Path, schema: dict) -> dict:
    import pandas as pd

    aliases = schema.get("column_aliases") or {}
    required_any = schema.get("required_columns_any") or ["gvkey"]
    files = sorted(
        [p for p in raw_root.rglob("*") if p.is_file() and p.suffix.lower() in {".csv", ".txt", ".xlsx", ".xls", ".zip"}],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return {"status": "missing_raw", "raw_root": str(raw_root.relative_to(ROOT))}

    frames = []
    used_files = []
    for path in files:
        try:
            df = _read_table(path)
        except Exception as exc:
            continue
        mapping = _resolve_columns(df, aliases)
        if not any(req.lower() in mapping for req in required_any):
            continue
        slim = pd.DataFrame({k: df[v] for k, v in mapping.items()})
        if "datadate" in slim.columns:
            slim["datadate"] = pd.to_datetime(slim["datadate"], errors="coerce")
        frames.append(slim)
        used_files.append(str(path.relative_to(ROOT)))

    if not frames:
        return {"status": "no_matching_exports", "files_seen": len(files)}

    out = pd.concat(frames, ignore_index=True).drop_duplicates()
    out_path = ROOT / schema["processed_output"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    return {
        "status": "ok",
        "rows": len(out),
        "columns": list(out.columns),
        "source_files": used_files,
        "output": str(out_path.relative_to(ROOT)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    raw_root = ROOT / schema["export_root"]
    raw_root.mkdir(parents=True, exist_ok=True)

    result = ingest_exports(raw_root, schema)
    out = {"generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), **result}
    manifest = raw_root / "ingest_latest.json"
    manifest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2) if args.json else json.dumps({"status": result.get("status"), "manifest": str(manifest.relative_to(ROOT))}, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
