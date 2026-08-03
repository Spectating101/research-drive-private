#!/usr/bin/env python3
"""Backtest selective fry best-picks over full history."""

from __future__ import annotations

import json
import sys

from idn_fry_best_pick_backtest_lib import build_best_pick_backtest


def main() -> int:
    top_k = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    report = build_best_pick_backtest(top_k=top_k)
    headline = {
        "meta": report["meta"],
        "reliability": report["reliability"],
        "strategies": {k: v for k, v in report["strategies"].items() if k.startswith("pick_") or k.startswith("bench_")},
    }
    print(json.dumps(headline, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
