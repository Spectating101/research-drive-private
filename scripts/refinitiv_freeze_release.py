#!/usr/bin/env python3
"""Freeze canonical Refinitiv run as an immutable release."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANONICAL_RUN = "2026-07-06-complete"
RUN_DIR = REPO / "data_lake/refinitiv_backfill" / CANONICAL_RUN
COMPLETION_SRC = REPO / "docs/status/generated/refinitiv_harvest_completion.json"
RELEASE_MD = REPO / "docs/status/generated/REFINITIV_2026_07_06_COMPLETE_RELEASE.md"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    if not RUN_DIR.exists():
        raise SystemExit(f"Missing run dir: {RUN_DIR}")

    release = {
        "release_id": CANONICAL_RUN,
        "frozen_at": utc_now(),
        "status": "RELEASE_FROZEN",
        "do_not_overwrite": True,
        "canonical": True,
        "platform_readiness": "9.0",
        "bulk_harvest_policy": "STOP — entitlement ceiling reached; targeted probes only",
        "artifacts": {
            "processed": str(RUN_DIR / "processed"),
            "normalized": str(RUN_DIR / "processed/normalized"),
            "qa": str(RUN_DIR / "qa"),
            "validated": str(RUN_DIR / "VALIDATED.json"),
            "manifest": str(RUN_DIR / "manifest.json"),
        },
        "derived_panels": str(REPO / "data_lake/research_panels/refinitiv" / CANONICAL_RUN),
        "notes": [
            "Do not re-run --job complete over this stamp.",
            "US vol/skew history: use rescued_desktop_20251215.",
            "Ownership, supply chain, StarMine: license-blocked on YZU EDP.",
        ],
    }
    (RUN_DIR / "RELEASE.json").write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")

    if COMPLETION_SRC.exists():
        shutil.copy2(COMPLETION_SRC, RUN_DIR / "completion_report.json")

    if not RELEASE_MD.exists():
        raise SystemExit(f"Release note missing: {RELEASE_MD}")

    print(json.dumps({"frozen": True, "release_id": CANONICAL_RUN, "release_md": str(RELEASE_MD)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
