#!/usr/bin/env python3
"""US + global entity master build, then GDELT bridge expansion."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable


def main() -> int:
    steps = [
        [PY, str(REPO / "scripts/build_us_entity_mapping_layer.py")],
        [PY, str(REPO / "scripts/build_global_entity_master.py")],
        [PY, str(REPO / "scripts/build_gdelt_entity_bridge_expansion.py")],
    ]
    for cmd in steps:
        subprocess.run(cmd, cwd=REPO, check=True)
    print(json.dumps({"ok": True, "steps": len(steps)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
