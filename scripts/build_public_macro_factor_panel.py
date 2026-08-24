#!/usr/bin/env python3
"""Build instant Ken French FF3 daily factor parquet from public macro baseline."""

from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "kernel") not in sys.path:
    sys.path.insert(0, str(REPO / "kernel"))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
MACRO_ROOT = ROOT / "data_lake/public_macro_market_baseline"
OUT_DIR = ROOT / "data_lake/research_panels/public_macro"
OUT_PANEL = OUT_DIR / "ff_factors_daily.parquet"
ZIP_NAME = "raw/kenneth_french/F-F_Research_Data_Factors_daily_CSV.zip"


def _latest_run_dir() -> Path | None:
    if not MACRO_ROOT.is_dir():
        return None
    runs = sorted([p for p in MACRO_ROOT.iterdir() if p.is_dir()], reverse=True)
    return runs[0] if runs else None


def _parse_ff3_csv(text: str):
    import pandas as pd
    from io import StringIO

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    header_idx = next(
        (i for i, ln in enumerate(lines) if "mkt-rf" in ln.lower() or ln.lower().startswith("date")),
        None,
    )
    if header_idx is not None:
        body = "\n".join(lines[header_idx:])
        df = pd.read_csv(StringIO(body))
    else:
        data_start = next(i for i, ln in enumerate(lines) if len(ln) >= 8 and ln[:8].isdigit())
        body = "\n".join(lines[data_start:])
        df = pd.read_csv(StringIO(body), header=None, names=["date", "mkt_rf", "smb", "hml", "rf"])

    df.columns = [c.strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]
    date_col = "date" if "date" in df.columns else df.columns[0]
    df = df.rename(columns={date_col: "date"})
    df["date"] = pd.to_datetime(df["date"].astype(str).str.replace(r"\.0$", "", regex=True), format="%Y%m%d", errors="coerce")
    for col in df.columns:
        if col == "date":
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["date"])
    return df


def main() -> int:
    run_dir = _latest_run_dir()
    if not run_dir:
        print("No public_macro_market_baseline run — run scripts/download_public_macro_market_baseline.py first", file=sys.stderr)
        return 1
    zip_path = run_dir / ZIP_NAME
    if not zip_path.is_file():
        print(f"Missing {zip_path}", file=sys.stderr)
        return 1

    with zipfile.ZipFile(zip_path) as zf:
        csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv") or n.lower().endswith(".txt"))
        raw = zf.read(csv_name).decode("utf-8", errors="replace")
    df = _parse_ff3_csv(raw)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PANEL, index=False)

    manifest = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_run": str(run_dir.relative_to(ROOT)),
        "source_zip": ZIP_NAME,
        "panel": str(OUT_PANEL.relative_to(ROOT)),
        "rows": len(df),
        "date_min": str(df["date"].min().date()) if len(df) else None,
        "date_max": str(df["date"].max().date()) if len(df) else None,
        "columns": list(df.columns),
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
