#!/usr/bin/env python3
"""Report GDELT news_shock_taxonomy sizes and retention scenarios."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

TAX = REPO / "data_lake" / "news_shock_taxonomy"
MANIFEST = (
    TAX
    / "derived"
    / "gdelt_expanded_queue_state"
    / "queue_manifest.json"
)
OUT = REPO / "docs" / "status" / "generated" / "gdelt_retention_snapshot.json"


def _dir_bytes(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = Path(root) / name
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total


def _gb(n: int) -> float:
    return round(n / 1024**3, 2)


def main() -> int:
    base = TAX
    if not base.is_dir() and Path("/media/phyrexian/Transcend/sharpe-renaissance/data_lake/news_shock_taxonomy").is_dir():
        base = Path("/media/phyrexian/Transcend/sharpe-renaissance/data_lake/news_shock_taxonomy")

    norm_exp = base / "normalized" / "gdelt_gkg_expanded_bulk"
    norm_asia = base / "normalized" / "gdelt_gkg_asia_bulk"
    proc_root = base / "processed"
    derived = base / "derived"
    raw = base / "raw"

    proc_exp_dirs = sorted(proc_root.glob("expanded_gkg_window_*")) if proc_root.is_dir() else []
    proc_exp_bytes = sum(_dir_bytes(d) for d in proc_exp_dirs)

    layers = {
        "normalized_expanded_gb": _gb(_dir_bytes(norm_exp)),
        "normalized_asia_legacy_gb": _gb(_dir_bytes(norm_asia)),
        "processed_expanded_gb": _gb(proc_exp_bytes),
        "derived_gb": _gb(_dir_bytes(derived)),
        "raw_gb": _gb(_dir_bytes(raw)),
    }
    layers["total_taxonomy_gb"] = round(sum(layers.values()), 2)

    sc = REPO / "data" / "datasets" / "stablecoin_trust_engagement"
    layers["stablecoin_dataset_gb"] = _gb(_dir_bytes(sc))

    complete, total_m = 66, 102
    if MANIFEST.is_file():
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        complete = int(m.get("complete_months", complete))
        total_m = int(m.get("total_months", total_m))
    elif (base / "derived" / "gdelt_expanded_queue_state" / "queue_manifest.json").is_file():
        mp = base / "derived" / "gdelt_expanded_queue_state" / "queue_manifest.json"
        m = json.loads(mp.read_text(encoding="utf-8"))
        complete = int(m.get("complete_months", complete))
        total_m = int(m.get("total_months", total_m))

    factor = total_m / max(complete, 1)
    n_exp = layers["normalized_expanded_gb"]
    p_exp = layers["processed_expanded_gb"]
    other = layers["normalized_asia_legacy_gb"] + layers["derived_gb"] + layers["raw_gb"]

    scenarios = {
        "A_full_pipeline_at_102mo_gb": round(n_exp * factor + p_exp * factor + other, 2),
        "B_drop_processed_keep_normalized_gb": round(n_exp * factor + other, 2),
        "C_derived_and_datasets_local_only_gb": round(
            layers["derived_gb"] + layers["stablecoin_dataset_gb"], 2
        ),
    }

    snap = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "queue_complete_months": complete,
        "queue_total_months": total_m,
        "expanded_window_dirs": {
            "normalized": len(list(norm_exp.glob("expanded_gkg_window_*"))) if norm_exp.is_dir() else 0,
            "processed": len(proc_exp_dirs),
        },
        "current_gb": layers,
        "scenarios_at_102_months_gb": scenarios,
        "notes": [
            "343GB is normalized+processed pipeline bulk, not raw GDELT zips.",
            "Target products: derived/ overlays + data/datasets/stablecoin_trust_engagement.",
            "See docs/GDELT_RETENTION_PLAN.md",
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")

    print(f"GDELT retention snapshot  queue={complete}/{total_m}")
    print("CURRENT (GB)")
    for k, v in layers.items():
        print(f"  {k}: {v}")
    print("SCENARIOS at 102 months (GB)")
    for k, v in scenarios.items():
        print(f"  {k}: {v}")
    print(f"written: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
