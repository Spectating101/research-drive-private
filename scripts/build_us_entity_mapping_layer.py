#!/usr/bin/env python3
"""Build US entity→instrument mapping (SP500 + mega-cap) for GDELT bridge joins."""

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
DEFAULT_OUT = ROOT / "data_lake/entity_mapping/us"
SP500 = ROOT / "config/tickers_sp500.txt"
UNIVERSES = ROOT / "config/refinitiv_universes.json"


def _load_tickers() -> list[str]:
    syms: list[str] = []
    if SP500.is_file():
        for line in SP500.read_text(encoding="utf-8").splitlines():
            s = line.split("#", 1)[0].strip().upper()
            if s and not s.startswith("^"):
                syms.append(s)
    if UNIVERSES.is_file():
        doc = json.loads(UNIVERSES.read_text(encoding="utf-8"))
        mega = ((doc.get("universes") or {}).get("us_mega_cap_ric") or {}).get("rics") or []
        for ric in mega:
            r = str(ric).strip()
            if r.endswith(".O") or r.endswith(".N"):
                syms.append(r[:-2].replace("_b", ".B"))
    return list(dict.fromkeys(syms))


def build_us_master(*, run_id: str | None = None) -> dict:
    run = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = DEFAULT_OUT / run
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for sym in _load_tickers():
        rows.append(
            {
                "entity_id": f"US_OR_GLOBAL:{sym}",
                "market_country": "USA",
                "exchange": "US_OR_GLOBAL",
                "local_code": sym,
                "yahoo_symbol": sym,
                "name": "",
                "instrument_type": "equity_or_fund",
                "source_tags": "us_sp500_registry|synthetic_gdelt_bridge",
                "confidence": "medium",
            }
        )
    path = out_dir / "us_entity_master.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["entity_id"])
        w.writeheader()
        w.writerows(rows)
    summary = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "run_id": run,
        "us_symbols": len(rows),
        "output": str(path.relative_to(ROOT)),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    latest = DEFAULT_OUT / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(out_dir.name)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = build_us_master(run_id=args.run_id or None)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
