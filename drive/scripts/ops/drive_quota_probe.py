#!/usr/bin/env python3
"""Run one bounded Drive copy/check probe after a quota cooldown.

This is intentionally a one-shot health probe, not a synchronizer.  It writes
one tiny marker below the verification area so that Drive readiness is tested
through the same archive path used by collection jobs.
"""

from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from scripts.research_data_mcp.drive_first import archive_local_to_remote


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    marker_name = f"drive-health-{stamp}-{uuid.uuid4().hex[:8]}.txt"
    remote_suffix = (
        "collection/_verification/research-drive-control-plane/"
        f"quota-probe/{marker_name}"
    )
    local_rel = f"data_lake/.drive-health/{marker_name}"
    local_path = repo_root / local_rel
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text("research-drive quota probe\n", encoding="utf-8")
    try:
        result = archive_local_to_remote(
            repo_root,
            local_rel,
            remote_suffix,
            verify=True,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("ok") and result.get("verified") else 2
    finally:
        local_path.unlink(missing_ok=True)
        try:
            local_path.parent.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
