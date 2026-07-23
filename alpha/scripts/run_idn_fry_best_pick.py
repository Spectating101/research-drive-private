#!/usr/bin/env python3
"""Emit gated fry best-pick shortlist."""

from __future__ import annotations

import json
import sys

from idn_fry_best_pick_lib import build_and_save_best_picks


def main() -> int:
    top_k = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    report = build_and_save_best_picks(top_k=top_k)
    print(json.dumps({"as_of": report["as_of"], "top_picks": report["top_picks"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
