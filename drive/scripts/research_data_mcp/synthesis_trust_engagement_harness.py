#!/usr/bin/env python3
"""Full trust↔engagement synthesis test — community, security, GDELT cluster."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
for _p in (_REPO, _REPO / "kernel", _REPO / "drive"):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

from scripts.research_data_mcp.bootstrap import create_stack

PROFESSOR_PROMPTS = [
    "How many stablecoin entities have community growth + security + adoption data clustered?",
    "Which coins have 5 or more source layers for panel research?",
    "Show an example week with peg stress and GDELT security news together.",
    "What is the weekly panel size and date range for trust vs engagement work?",
]


def answer_trust_engagement(run: dict) -> list[dict]:
    s = run.get("summary") or {}
    cluster = run.get("cluster") or {}
    samples = run.get("panel_samples") or []
    src = cluster.get("source_coverage") or {}

    out = [
        {
            "prompt": PROFESSOR_PROMPTS[0],
            "answer": (
                f"{s.get('leaderboard_entities')} leaderboard entities; "
                f"code security on {s.get('with_code_security_score')}, "
                f"GDELT hits on {s.get('entities_with_gdelt_hits')} entities, "
                f"DeFiLlama mapped {s.get('defillama_mapped_entities')}, "
                f"community engagement weekly rows {s.get('engagement_weekly_rows')}."
            ),
            "actionable": bool(s.get("leaderboard_entities")),
        },
        {
            "prompt": PROFESSOR_PROMPTS[1],
            "answer": (
                f"{cluster.get('entities_with_5plus_sources', 0)} entities with ≥5 sources. "
                f"Examples: "
                + ", ".join(
                    (r.get("entity_id") or "") for r in (cluster.get("top_multi_source") or [])[:5]
                )
            ),
            "actionable": (cluster.get("entities_with_5plus_sources") or 0) > 0,
        },
        {
            "prompt": PROFESSOR_PROMPTS[2],
            "answer": json.dumps(samples[0], default=str) if samples else "No sample row with stress+GDELT in preview",
            "actionable": bool(samples),
        },
        {
            "prompt": PROFESSOR_PROMPTS[3],
            "answer": (
                f"{s.get('research_weekly_rows')} entity-week rows, range {s.get('week_range')}. "
                f"Primary table: panels/research_panel_weekly.csv"
            ),
            "actionable": bool(s.get("research_weekly_rows")),
        },
    ]
    return out


def main() -> int:
    stack = create_stack(_REPO)
    report: dict = {"checks": [], "professor_qa": []}

    t0 = time.perf_counter()
    run = stack.tools.research_synthesis_run(
        "stablecoin_trust_engagement",
        preview_limit=10,
        gap_limit=10,
    )
    ms = int((time.perf_counter() - t0) * 1000)
    s = run.get("summary") or {}

    report["checks"] = [
        {"name": "trust_engagement_run", "ok": run.get("type") == "trust_engagement", "ms": ms},
        {
            "name": "weekly_panel_rows",
            "ok": (s.get("research_weekly_rows") or 0) > 10_000,
            "rows": s.get("research_weekly_rows"),
        },
        {
            "name": "security_coverage",
            "ok": (s.get("with_code_security_score") or 0) >= 60,
            "n": s.get("with_code_security_score"),
        },
        {
            "name": "community_engagement",
            "ok": (s.get("engagement_weekly_rows") or 0) > 10_000,
            "n": s.get("engagement_weekly_rows"),
        },
        {
            "name": "gdelt_entity_layer",
            "ok": (s.get("entities_with_gdelt_hits") or 0) >= 40,
            "n": s.get("entities_with_gdelt_hits"),
        },
        {
            "name": "multi_source_cluster",
            "ok": (s.get("entities_with_5plus_sources") or 0) >= 30,
            "n": s.get("entities_with_5plus_sources"),
        },
        {
            "name": "panel_artifact",
            "ok": (_REPO / str(run.get("artifacts", {}).get("panel_weekly", ""))).is_file(),
        },
    ]

    report["summary"] = s
    report["source_coverage"] = (run.get("cluster") or {}).get("source_coverage")
    report["professor_qa"] = answer_trust_engagement(run)
    report["qa_actionable"] = sum(1 for q in report["professor_qa"] if q.get("actionable")) / max(
        len(report["professor_qa"]), 1
    )
    report["pass"] = all(c["ok"] for c in report["checks"]) and report["qa_actionable"] >= 0.75

    print(json.dumps(report, indent=2, default=str))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
