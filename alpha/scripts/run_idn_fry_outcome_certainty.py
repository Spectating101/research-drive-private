#!/usr/bin/env python3
"""Build fry outcome certainty report — full win/loss path menu."""

from __future__ import annotations

import json
import sys

from idn_fry_outcome_certainty_lib import build_outcome_certainty_report


def main() -> int:
    report = build_outcome_certainty_report()
    summary = {
        "n_episodes": report["meta"]["n_episodes"],
        "verdict": report["certainty_verdict"]["verdict"],
        "plain_english": report["certainty_verdict"]["plain_english"],
        "t1": {
            "pop_any_pct": report["t1_deep_dd_vol"].get("pop_any_rate_pct"),
            "non_pop": report["t1_deep_dd_vol"].get("non_pop_breakdown_pct"),
            "if_hold_30d_median": report["t1_deep_dd_vol"]
            .get("if_hold_from_trigger_close", {})
            .get("median_cum_30d_pct"),
        },
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
