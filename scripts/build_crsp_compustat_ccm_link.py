#!/usr/bin/env python3
"""Build CRSP/Compustat CCM link parquet when link source files exist on disk."""

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
CRSP_ROOT = ROOT / "data_lake/crsp"
OUT = CRSP_ROOT / "processed/ccm_link.parquet"

LINK_NAME_HINTS = ("ccm", "link", "crspcomp", "ccmxpf")
LINK_COL_SETS = [
    {"gvkey", "lpermno", "linkdt"},
    {"gvkey", "permno", "linkdt"},
    {"gvkey", "lpermno", "linkenddt"},
]


def _read_table(path: Path):
    import pandas as pd

    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path, low_memory=False)


def _find_link_file() -> Path | None:
    search_roots = [CRSP_ROOT / "raw", CRSP_ROOT / "extracted", ROOT / "data_lake/compustat/raw"]
    for root in search_roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            name = path.name.lower()
            if path.suffix.lower() not in {".csv", ".txt", ".parquet", ".xlsx", ".xls"}:
                continue
            if any(h in name for h in LINK_NAME_HINTS):
                return path
    return None


def _normalize_link(df):
    import pandas as pd

    cols = {str(c).strip().lower(): c for c in df.columns}
    mapping = {}
    for want in ("gvkey", "permno", "lpermno", "linkdt", "linkenddt", "linktype", "linkprim"):
        for alias in (want, want.upper()):
            if alias.lower() in cols:
                mapping[want] = cols[alias.lower()]
                break
    if "gvkey" not in mapping or ("permno" not in mapping and "lpermno" not in mapping):
        return None
    slim = pd.DataFrame({k: df[v] for k, v in mapping.items()})
    if "permno" not in slim.columns and "lpermno" in slim.columns:
        slim["permno"] = slim["lpermno"]
    for col in ("linkdt", "linkenddt"):
        if col in slim.columns:
            slim[col] = pd.to_datetime(slim[col], errors="coerce")
    return slim.dropna(subset=["gvkey", "permno"], how="any")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    link_path = _find_link_file()
    if not link_path:
        out = {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "status": "blocked",
            "reason": "No CCM/link file under data_lake/crsp or compustat/raw",
            "hint": "CRSP CCM often ships as separate MOVEit product or WRDS table; place *ccm*link*.csv in data_lake/crsp/raw/",
        }
        manifest = CRSP_ROOT / "processed/ccm_link_status.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(out, indent=2) if args.json else out["reason"])
        return 1

    df = _read_table(link_path)
    link = _normalize_link(df)
    if link is None or link.empty:
        out = {"status": "blocked", "reason": "link_file_missing_columns", "source": str(link_path.relative_to(ROOT))}
        print(json.dumps(out, indent=2))
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    link.to_parquet(OUT, index=False)
    out = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "ok",
        "rows": len(link),
        "source": str(link_path.relative_to(ROOT)),
        "output": str(OUT.relative_to(ROOT)),
    }
    (CRSP_ROOT / "processed/ccm_link_status.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2) if args.json else json.dumps({"rows": len(link), "output": str(OUT.relative_to(ROOT))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
