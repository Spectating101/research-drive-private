#!/usr/bin/env python3
"""Reverse-engineer IDX price-movement detectors via agent + historical panel.

Modes:
  scan     — fast deterministic full scan (no LLM)
  agent    — LLM calls discovery tools to hypothesize and test signals

Outputs:
  backtests/outputs/platform/idn_signal_discovery/latest.json
  backtests/outputs/platform/idn_signal_discovery/latest.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from idn_signal_discovery_agent import run_discovery_agent  # noqa: E402
from idn_signal_discovery_tools import DiscoveryContext, deterministic_discovery_scan  # noqa: E402
from run_idn_invest_trial import load_liquid_universe  # noqa: E402

OUT = REPO / "backtests/outputs/platform/idn_signal_discovery"


def write_md(result: dict[str, Any]) -> str:
    rep = result.get("discovery_report") or {}
    lines = [
        "# IDX signal discovery (reverse engineering)",
        f"- built: {result.get('built_at_utc')}",
        f"- mode: {result.get('mode')}",
        f"- tool_calls: {result.get('tool_calls', 'n/a')}",
        "",
        "## Summary",
        rep.get("summary", "n/a"),
        "",
        "## Best signals (detection rules)",
    ]
    for s in rep.get("best_signals", []):
        lines.append(
            f"- **{s.get('signal')}** ({s.get('direction')}) → {s.get('target')}: "
            f"{s.get('detection_rule')} | verdict={s.get('verdict')}"
        )
        lines.append(f"  - evidence: {s.get('evidence')}")
    lines.extend(["", "## Recommended detector stack"])
    for x in rep.get("recommended_detector_stack", []):
        lines.append(f"- {x}")
    lines.extend(["", "## Retail rules validated"])
    for r in rep.get("retail_rules_validated", []):
        lines.append(f"- {r.get('strategy_id')}: {r.get('verdict')}")
    lines.extend(["", "## Failed / rejected"])
    for f in rep.get("failed_signals", []):
        lines.append(f"- {f.get('signal')}: {f.get('why')}")
    lines.extend(["", "## Next experiments"])
    for n in rep.get("next_experiments", []):
        lines.append(f"- {n}")
    if result.get("deterministic_scan"):
        lines.extend(["", "## Deterministic scan (raw)"])
        best = (result["deterministic_scan"].get("best_candidates") or {})
        for c in best.get("oos_top", [])[:5]:
            lines.append(f"- OOS: {c}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["scan", "agent"], default="scan")
    ap.add_argument("--llm", default="auto", help="LLM backend for agent mode")
    ap.add_argument("--llm-model", default="")
    ap.add_argument("--include-retail", action="store_true", help="Run slow retail event studies in scan mode.")
    args = ap.parse_args()

    liquid = load_liquid_universe()
    ctx = DiscoveryContext(liquid=liquid)

    if args.mode == "scan":
        det = deterministic_discovery_scan(ctx, include_retail=bool(args.include_retail))
        result: dict[str, Any] = {
            "mode": "deterministic_scan",
            "built_at_utc": datetime.now(UTC).isoformat(),
            "deterministic_scan": det,
            "discovery_report": {
                "mission": "reverse_engineer_price_movement",
                "best_signals": [
                    {
                        "signal": c.get("signal"),
                        "direction": c.get("direction"),
                        "target": "fwd_return_1w",
                        "evidence": f"spread_t={c.get('spread_t')} era=oos_holdout",
                        "verdict": c.get("verdict"),
                        "detection_rule": f"{c.get('direction')} on {c.get('signal')}",
                    }
                    for c in (det.get("best_candidates") or {}).get("oos_top", [])[:5]
                ],
                "retail_rules_validated": [
                    {"strategy_id": s, "verdict": "reliable"}
                    for s in (det.get("best_candidates") or {}).get("retail_reliable", [])
                ],
                "recommended_detector_stack": (det.get("best_candidates") or {}).get("retail_reliable", [])
                + (det.get("best_candidates") or {}).get("oos_stable_signals", []),
                "failed_signals": [],
                "falsifiers": ["entity coverage 2024+ thin"],
                "next_experiments": ["run --mode agent for LLM synthesis", "composite signal backtest"],
                "summary": "Deterministic panel scan — ranked OOS candidates and retail event studies.",
            },
        }
    else:
        agent = run_discovery_agent(
            liquid=liquid,
            backend=args.llm,
            model=args.llm_model,
            max_turns=args.max_turns,
        )
        result = {
            "built_at_utc": datetime.now(UTC).isoformat(),
            **agent,
        }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    (OUT / "latest.md").write_text(write_md(result), encoding="utf-8")
    if result.get("trace"):
        (OUT / "discovery_trace.json").write_text(
            json.dumps(result["trace"], indent=2, default=str) + "\n", encoding="utf-8"
        )
    print(write_md(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
