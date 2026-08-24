#!/usr/bin/env python3
"""List CRSP MOVEit Product_Downloads and write manifest_latest.json."""

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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="Write manifest to data_lake/crsp/")
    args = ap.parse_args()

    from scripts.crsp_moveit_lib import crsp_credentials, list_moveit_folders, load_env_local, moveit_login_session

    env = load_env_local(ROOT)
    user, password = crsp_credentials(env)
    sess = moveit_login_session(user, password)
    r = sess.get("https://crsp.moveitcloud.com/", timeout=60)
    folders = list_moveit_folders(r.text)

    catalog_path = ROOT / "config/crsp_moveit_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.is_file() else {}
    priorities = {p["moveit_label"]: p for p in catalog.get("priority_products") or []}

    matched = []
    for row in folders:
        label = row["label"]
        base = label.split("/")[-1].strip()
        if base in priorities:
            row["priority"] = priorities[base]
            matched.append(base)

    out = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "portal": "https://crsp.moveitcloud.com",
        "authenticated": True,
        "folder_count": len(folders),
        "priority_matched": matched,
        "folders": folders,
        "catalog": str(catalog_path.relative_to(ROOT)),
    }

    if args.json:
        out_dir = ROOT / "data_lake/crsp"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "manifest_latest.json"
        path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {path}")
    else:
        print(json.dumps({"folder_count": len(folders), "priority_matched": matched}, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
