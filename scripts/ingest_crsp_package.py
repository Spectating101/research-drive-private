#!/usr/bin/env python3
"""Extract CRSP MOVEit zip downloads and emit processed ingest manifests."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "kernel") not in sys.path:
    sys.path.insert(0, str(REPO / "kernel"))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
RAW_ROOT = ROOT / "data_lake/crsp/raw"
EXTRACT_ROOT = ROOT / "data_lake/crsp/extracted"
PROCESSED_ROOT = ROOT / "data_lake/crsp/processed"
CATALOG = ROOT / "config/crsp_moveit_catalog.json"

PRODUCT_OUTPUT = {
    "stock_25i_si_ascii_annual": "us_stock_daily_ciz.parquet",
    "stock_index_1925_annsub": "us_index_history.parquet",
    "index_history_qtrrel": "us_index_quarterly.parquet",
}


def _extract_zip(zip_path: Path, dest: Path) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = dest / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.is_file():
                # Stream rather than read(): these packages carry members up to
                # 9.6 GiB (sfz_dp_dly.dat). Reading a member whole put this
                # process at a ~21 GB peak on a 31 GB box and took the desktop
                # down with the OOM killer.
                with zf.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)
            names.append(info.filename)
    return names


def _try_build_index_parquet(extract_dir: Path, out_path: Path) -> dict:
    """Best-effort: if readable delimited index files exist, materialize a skinny parquet."""
    import pandas as pd

    candidates = sorted(extract_dir.rglob("*.txt")) + sorted(extract_dir.rglob("*.csv"))
    if not candidates:
        return {"status": "pending_parse", "reason": "no_text_files_in_zip", "parser": "crsp_cadb"}

    # Heuristic: pick largest text file with a date-like first column
    best = None
    best_rows = 0
    for path in candidates[:20]:
        try:
            sample = path.read_text(encoding="utf-8", errors="replace")[:4000]
            if not any(ch.isdigit() for ch in sample[:200]):
                continue
            df = pd.read_csv(path, nrows=5000, low_memory=False)
            if len(df) < best_rows:
                continue
            best, best_rows = path, len(df)
        except Exception:
            continue

    if best is None:
        return {"status": "pending_parse", "reason": "no_parseable_text", "files_seen": len(candidates)}

    df = pd.read_csv(best, low_memory=False)
    df.columns = [str(c).strip().lower() for c in df.columns]
    date_col = next((c for c in df.columns if c in {"date", "caldt", "mcaldt"}), df.columns[0])
    df[date_col] = pd.to_datetime(df[date_col].astype(str).str.replace(r"\.0$", "", regex=True), errors="coerce")
    df = df.dropna(subset=[date_col])
    if df.empty:
        return {"status": "pending_parse", "reason": "empty_after_date_parse", "source_file": str(best.name)}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return {
        "status": "partial",
        "source_file": str(best.relative_to(extract_dir)),
        "rows": len(df),
        "columns": list(df.columns)[:30],
        "note": "Heuristic text ingest — verify against CRSP CADB/ASCII spec",
    }


def ingest_product(product_id: str) -> dict:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    prod = next((p for p in catalog.get("priority_products") or [] if p["id"] == product_id), None)
    raw_dir = RAW_ROOT / product_id
    zips = sorted(raw_dir.glob("*.zip")) if raw_dir.is_dir() else []
    if not zips:
        return {"product_id": product_id, "status": "missing_raw", "raw_dir": str(raw_dir.relative_to(ROOT))}

    zip_path = zips[-1]
    extract_dir = EXTRACT_ROOT / product_id / zip_path.stem
    members = _extract_zip(zip_path, extract_dir)

    out_name = PRODUCT_OUTPUT.get(product_id)
    parse_info: dict = {"status": "extracted_only"}
    if out_name:
        out_path = PROCESSED_ROOT / out_name
        parse_info = _try_build_index_parquet(extract_dir, out_path)

    return {
        "product_id": product_id,
        "moveit_label": prod.get("moveit_label") if prod else None,
        "registry_dataset_id": (prod or {}).get("registry_dataset_id"),
        "zip": str(zip_path.relative_to(ROOT)),
        "extracted_to": str(extract_dir.relative_to(ROOT)),
        "member_count": len(members),
        "members_sample": members[:15],
        "parse": parse_info,
        "processed_file": str((PROCESSED_ROOT / out_name).relative_to(ROOT)) if out_name else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--product", action="append", dest="products", help="Catalog product id")
    ap.add_argument("--all-downloaded", action="store_true", help="Ingest every product dir under raw/")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.all_downloaded:
        product_ids = [p.name for p in RAW_ROOT.iterdir() if p.is_dir() and p.name != "_smoke"]
    elif args.products:
        product_ids = args.products
    else:
        product_ids = ["stock_index_1925_annsub"]

    results = [ingest_product(pid) for pid in product_ids]
    out = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "results": results,
    }
    manifest = PROCESSED_ROOT / "ingest_latest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    try:
        from scripts.sync_crsp_ingest_registry import sync_from_ingest

        sync_from_ingest()
    except Exception:
        pass
    print(json.dumps(out, indent=2) if args.json else json.dumps({"manifest": str(manifest.relative_to(ROOT)), "products": len(results)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
