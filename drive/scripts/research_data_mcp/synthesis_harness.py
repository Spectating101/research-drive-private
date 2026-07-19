#!/usr/bin/env python3
"""Composer-equipment test — synthesis tools only, no manual imports."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
for _p in (_REPO, _REPO / "kernel", _REPO / "drive"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from scripts.research_data_mcp.bootstrap import create_stack
from scripts.research_data_mcp.http_router import handle_get, handle_post


PROFESSOR_PROMPTS = [
    "How many CertiK Skynet stablecoins also have Etherscan token data?",
    "Name stablecoins on Skynet that we still don't have Etherscan coverage for.",
    "Give me one example of a fully linked coin with security score and holder count.",
    "Can we join Skynet harvest data with the Asia GDELT daily panel directly?",
]


def answer_from_synthesis_only(tools, run: dict, pair_skynet_gdelt: dict) -> list[dict]:
    s = run.get("summary") or {}
    entities = run.get("entities") or []
    gaps = run.get("gaps") or []
    out: list[dict] = []

    out.append(
        {
            "prompt": PROFESSOR_PROMPTS[0],
            "answer": (
                f"{s.get('both_count')} of {s.get('left_count')} Skynet leaderboard projects "
                f"are linked to Etherscan scrapes ({s.get('overlap_pct')}% overlap)."
            ),
            "source": "research_synthesis_run.summary",
            "actionable": s.get("both_count") is not None,
        }
    )

    gap_names = [g.get("canonical_name") or g.get("skynet_slug") for g in gaps[:10]]
    out.append(
        {
            "prompt": PROFESSOR_PROMPTS[1],
            "answer": (
                f"{s.get('skynet_only_count')} Skynet-only: "
                + (", ".join(gap_names) if gap_names else "(none in preview)")
            ),
            "source": "research_synthesis_run.gaps",
            "actionable": bool(gap_names),
            "next_action": (gaps[0].get("recommended_action") if gaps else None),
        }
    )

    ex = entities[0] if entities else {}
    out.append(
        {
            "prompt": PROFESSOR_PROMPTS[2],
            "answer": (
                f"{ex.get('canonical_name')} ({ex.get('entity_id')}): Skynet score "
                f"{ex.get('skynet_score')}, {ex.get('etherscan_holders'):,} holders, "
                f"on-chain mcap ${ex.get('etherscan_onchain_mcap_usd'):,.0f}."
                if ex
                else "No linked entity in preview — widen preview_limit."
            ),
            "source": "research_synthesis_run.entities[0]",
            "actionable": bool(ex.get("skynet_score")),
        }
    )

    sm = pair_skynet_gdelt.get("summary") or {}
    out.append(
        {
            "prompt": PROFESSOR_PROMPTS[3],
            "answer": (
                f"Not via registry metadata alone (overlap {sm.get('overlap_pct')}%, "
                f"viable={sm.get('synthesis_viable')}). "
                f"Use skynet_etherscan_stablecoin profile or a future skynet_gdelt_entity profile."
            ),
            "source": "research_synthesis_pair",
            "actionable": sm.get("synthesis_viable") is False,
        }
    )
    return out


def main() -> int:
    stack = create_stack(_REPO)
    tools = stack.tools
    report: dict = {"checks": [], "professor_qa": []}

    t0 = time.perf_counter()
    profiles = tools.research_synthesis_list_profiles()
    report["checks"].append(
        {
            "name": "mcp_list_profiles",
            "ok": profiles.get("count", 0) >= 1,
            "ms": int((time.perf_counter() - t0) * 1000),
        }
    )

    t0 = time.perf_counter()
    run = tools.research_synthesis_run("skynet_etherscan_stablecoin", preview_limit=10, gap_limit=20)
    run_ms = int((time.perf_counter() - t0) * 1000)
    s = run.get("summary") or {}
    report["checks"].append(
        {
            "name": "mcp_run_skynet_etherscan",
            "ok": (s.get("both_count") or 0) > 0 and bool(run.get("artifacts", {}).get("panel_csv")),
            "ms": run_ms,
            "both_count": s.get("both_count"),
        }
    )

    t0 = time.perf_counter()
    pair = tools.research_synthesis_pair("skynet_stablecoin_harvest", "gdelt_asia_daily_country_panel")
    report["checks"].append(
        {
            "name": "mcp_pair_skynet_gdelt",
            "ok": pair.get("summary", {}).get("synthesis_viable") is False,
            "ms": int((time.perf_counter() - t0) * 1000),
        }
    )

    t0 = time.perf_counter()
    http_profiles = handle_get("/library/synthesis/profiles", {}, stack)
    http_run = handle_post(
        "/library/synthesis/run",
        {"profile_id": "skynet_etherscan_stablecoin", "preview_limit": 3},
        stack,
    )
    prof_body = http_profiles.get("body") if isinstance(http_profiles, dict) else http_profiles
    run_body = http_run.get("body") if isinstance(http_run, dict) else http_run
    report["checks"].append(
        {
            "name": "http_router_synthesis",
            "ok": http_profiles.get("status") == 200
            and http_run.get("status") == 200
            and prof_body.get("count", 0) >= 1
            and run_body.get("type") == "skynet_etherscan",
            "ms": int((time.perf_counter() - t0) * 1000),
        }
    )

    panel_rel = run.get("artifacts", {}).get("panel_csv", "")
    panel = _REPO / panel_rel if panel_rel else None
    report["checks"].append(
        {
            "name": "panel_csv_readable",
            "ok": panel is not None and panel.is_file() and panel.stat().st_size > 1000,
            "bytes": panel.stat().st_size if panel and panel.is_file() else 0,
        }
    )

    try:
        q = stack.gateway.query_dataset  # noqa: F841 — probe registry
        reg_hit = stack.gateway.describe_dataset("stablecoin_unified_panel")
        registry_ok = bool(reg_hit.get("dataset_id"))
    except Exception:
        registry_ok = False
        reg_hit = {}
    report["checks"].append(
        {
            "name": "registry_queryable_panel",
            "ok": registry_ok,
            "note": "stablecoin_unified_panel not in registry yet" if not registry_ok else "ok",
        }
    )

    report["professor_qa"] = answer_from_synthesis_only(tools, run, pair)
    report["composer_ready_score"] = sum(1 for c in report["checks"] if c.get("ok")) / max(len(report["checks"]), 1)
    report["qa_actionable"] = sum(1 for q in report["professor_qa"] if q.get("actionable")) / max(
        len(report["professor_qa"]), 1
    )

    print(json.dumps(report, indent=2, default=str))
    all_core = all(c.get("ok") for c in report["checks"] if c["name"] != "registry_queryable_panel")
    return 0 if all_core and report["qa_actionable"] >= 0.75 else 1


if __name__ == "__main__":
    raise SystemExit(main())
