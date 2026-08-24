#!/usr/bin/env python3
"""Summarize Refinitiv harvest completion: entitled vs collected vs blocked."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENTITLEMENT = REPO / "docs/status/generated/refinitiv_value_entitlement_map.json"
BACKFILL = REPO / "data_lake/refinitiv_backfill"
DEFAULT_OUT = REPO / "docs/status/generated/refinitiv_harvest_completion.json"

CANONICAL_RUN = "2026-07-06-complete"

JOB_ARTIFACTS = {
    "job_1": "refinitiv_security_master.parquet",
    "job_2": "index_membership_pit.parquet",
    "job_3": "corporate_actions_snapshot.parquet",
    "job_4": "vol_surface_metrics_daily.parquet",
    "job_5": "estimate_revisions_daily.parquet",
    "job_6": "fundamentals_panel.parquet",
    "job_7": "index_membership_current.parquet",
    "job_8": "analyst_consensus_snapshot.parquet",
    "job_9": "esg_snapshot.parquet",
}

BLOCKED_CATEGORIES = {
    "G1_ownership": "Institutional ownership fields not on YZU EDP",
    "I1_supply_chain": "Supply chain graph fields not on YZU EDP",
    "F1_starmine_probe": "StarMine / SmartEstimate fields not on YZU EDP",
    "A1_A7_prices": "Skipped — yfinance + IDX legacy cover OHLCV",
    "M1_M2_news": "Skipped — GDELT lane is canonical",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    ent = json.loads(ENTITLEMENT.read_text(encoding="utf-8")) if ENTITLEMENT.exists() else {}
    categories = ent.get("categories") or {}

    run_dir = BACKFILL / CANONICAL_RUN / "processed"
    collected: dict[str, Any] = {}
    for job, artifact in JOB_ARTIFACTS.items():
        path = run_dir / artifact
        if path.exists():
            collected[job] = {"artifact": artifact, "bytes": path.stat().st_size, "status": "collected"}
        else:
            collected[job] = {"artifact": artifact, "status": "missing"}

    entitled = []
    partial = []
    blocked = []
    for cat_id, cat in categories.items():
        status = cat.get("status", "fail")
        entry = {"category_id": cat_id, "status": status, "description": cat.get("description")}
        if cat_id in BLOCKED_CATEGORIES:
            entry["reason"] = BLOCKED_CATEGORIES[cat_id]
            blocked.append(entry)
        elif status == "pass":
            entitled.append(entry)
        elif status == "partial":
            partial.append(entry)
        else:
            blocked.append(entry)

    rescued = BACKFILL / "rescued_desktop_20251215/processed/us_risk_vol_skew_daily.parquet"
    desktop_risk = rescued.exists()

    report = {
        "generated_at": utc_now(),
        "canonical_run_id": CANONICAL_RUN,
        "entitlement_summary": ent.get("summary"),
        "entitled_categories": entitled,
        "partial_categories": partial,
        "blocked_categories": blocked,
        "policy_skips": list(BLOCKED_CATEGORIES.values()),
        "jobs": collected,
        "desktop_rescued_us_risk": desktop_risk,
        "completion_score": _score(entitled, partial, blocked, collected, desktop_risk),
        "notes": [
            "YZU EDP vol 30/90 daily history empty; US vol/skew from desktop RESCUED pull.",
            "Fundamentals via fundamental_and_reference FRQ=FY (not get_data snapshot).",
            "Korea PIT uses 0#.KSE not 0#.KS11.",
        ],
    }
    DEFAULT_OUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"completion_score": report["completion_score"], "out": str(DEFAULT_OUT)}, indent=2))
    return 0


def _score(entitled, partial, blocked, collected, desktop_risk) -> dict:
    total_entitled_jobs = len(JOB_ARTIFACTS)
    collected_n = sum(1 for v in collected.values() if v.get("status") == "collected")
    entitled_n = len(entitled)
    return {
        "entitled_categories": entitled_n,
        "partial_categories": len(partial),
        "blocked_categories": len(blocked),
        "jobs_collected": collected_n,
        "jobs_total": total_entitled_jobs,
        "job_coverage_pct": round(100.0 * collected_n / total_entitled_jobs, 1),
        "desktop_risk_rescued": desktop_risk,
        "platform_readiness": "9.0" if collected_n >= 8 and desktop_risk else "8.5",
    }


if __name__ == "__main__":
    raise SystemExit(main())
