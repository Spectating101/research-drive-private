#!/usr/bin/env python3
"""Probe Refinitiv/LSEG entitlement across harvest-plan priority tiers."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = REPO / "config/refinitiv_harvest_plan.json"
DEFAULT_OUT = REPO / "docs/status/generated/refinitiv_entitlement_probe.json"

sys.path.insert(0, str(REPO / "scripts"))
from refinitiv_lseg_session import load_env, platform_session  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _frame_summary(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None:
        return {"rows": 0, "cols": 0, "columns": []}
    return {
        "rows": int(len(frame)),
        "cols": int(len(frame.columns)),
        "columns": [str(c) for c in frame.columns[:20]],
    }


def probe_get_data(ld: object, rics: list[str], fields: list[str]) -> dict[str, Any]:
    try:
        frame = ld.get_data(universe=rics, fields=fields)  # type: ignore[attr-defined]
        summary = _frame_summary(frame)
        ok = summary["rows"] > 0
        return {
            "ok": ok,
            "method": "get_data",
            "rics": rics,
            "fields": fields,
            "summary": summary,
            "error": None if ok else "empty frame",
        }
    except Exception as exc:
        return {
            "ok": False,
            "method": "get_data",
            "rics": rics,
            "fields": fields,
            "summary": _frame_summary(None),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=3),
        }


def probe_get_history(
    ld: object,
    rics: list[str],
    fields: list[str],
    *,
    start: str,
    interval: str,
) -> dict[str, Any]:
    try:
        frame = ld.get_history(  # type: ignore[attr-defined]
            universe=rics,
            fields=fields,
            start=start,
            interval=interval,
        )
        summary = _frame_summary(frame)
        ok = summary["rows"] > 0
        return {
            "ok": ok,
            "method": "get_history",
            "rics": rics,
            "fields": fields,
            "start": start,
            "interval": interval,
            "summary": summary,
            "error": None if ok else "empty frame",
        }
    except Exception as exc:
        return {
            "ok": False,
            "method": "get_history",
            "rics": rics,
            "fields": fields,
            "start": start,
            "interval": interval,
            "summary": _frame_summary(None),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=3),
        }


def build_tiers(plan: dict[str, Any]) -> list[dict[str, Any]]:
    probe = plan.get("entitlement_probe", {})
    basic_fields = list(probe.get("basic_fields", ["TR.CommonName", "TR.PriceClose", "TR.Volume"]))
    history_fields = list(probe.get("history_fields", ["TR.PriceClose", "TR.Volume"]))
    history_start = str(probe.get("history_start", "2024-01-01"))
    history_interval = str(probe.get("history_interval", "daily"))

    phases = plan.get("phases", {})
    p1 = phases.get("p1_idx_core", {})
    p2 = phases.get("p2_global_backbone", {})
    p3 = phases.get("p3_risk_derivatives", {})
    p4 = phases.get("p4_analyst", {})

    return [
        {
            "tier": "probe_rics",
            "description": "Handoff probe instruments",
            "rics": list(plan.get("probe_rics", [])),
            "snapshot_fields": basic_fields,
            "history_fields": history_fields,
            "history_start": history_start,
            "history_interval": history_interval,
        },
        {
            "tier": "p1_idx_core",
            "description": p1.get("title", "Indonesia / IDX core"),
            "rics": ["BBCA.JK", "BBRI.JK", ".JKSE"],
            "snapshot_fields": list(p1.get("metadata_snapshot", {}).get("fields", basic_fields)),
            "history_fields": list(p1.get("daily_history", {}).get("fields", history_fields)),
            "history_start": str(p1.get("daily_history", {}).get("start", history_start)),
            "history_interval": str(p1.get("daily_history", {}).get("interval", history_interval)),
        },
        {
            "tier": "p2_global_backbone",
            "description": p2.get("title", "Global cross-asset backbone"),
            "rics": list(p2.get("rics", [".SPX", "SPY", "USDIDR="]))[:6],
            "snapshot_fields": basic_fields,
            "history_fields": list(p2.get("daily_history", {}).get("fields", history_fields)),
            "history_start": str(p2.get("daily_history", {}).get("start", history_start)),
            "history_interval": str(p2.get("daily_history", {}).get("interval", history_interval)),
        },
        {
            "tier": "p3_risk_derivatives",
            "description": p3.get("title", "Derivatives / risk fields"),
            "rics": ["BBCA.JK", ".SPX", "NVDA.O"],
            "snapshot_fields": list(p3.get("snapshot", {}).get("fields", [])),
            "history_fields": None,
            "history_start": history_start,
            "history_interval": history_interval,
        },
        {
            "tier": "p4_analyst",
            "description": p4.get("title", "Analyst estimates"),
            "rics": ["BBCA.JK", "NVDA.O", "2330.TW"],
            "snapshot_fields": list(p4.get("snapshot", {}).get("fields", [])),
            "history_fields": None,
            "history_start": history_start,
            "history_interval": history_interval,
        },
    ]


def run_probe(plan_path: Path) -> dict[str, Any]:
    plan = load_plan(plan_path)
    tiers = build_tiers(plan)
    results: list[dict[str, Any]] = []

    with platform_session() as ld:
        for tier in tiers:
            tier_result: dict[str, Any] = {
                "tier": tier["tier"],
                "description": tier["description"],
                "rics": tier["rics"],
                "snapshot": probe_get_data(ld, tier["rics"], tier["snapshot_fields"]),
            }
            if tier.get("history_fields"):
                tier_result["history"] = probe_get_history(
                    ld,
                    tier["rics"][:3],
                    tier["history_fields"],
                    start=tier["history_start"],
                    interval=tier["history_interval"],
                )
            else:
                tier_result["history"] = None
            tier_result["ok"] = bool(tier_result["snapshot"]["ok"]) and (
                tier_result["history"] is None or bool(tier_result["history"]["ok"])
            )
            results.append(tier_result)

    ok_count = sum(1 for r in results if r["ok"])
    return {
        "generated_at": utc_now(),
        "plan_path": str(plan_path),
        "summary": {
            "tiers_total": len(results),
            "tiers_ok": ok_count,
            "tiers_failed": len(results) - ok_count,
            "all_ok": ok_count == len(results),
        },
        "tiers": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe LSEG entitlement across harvest tiers.")
    ap.add_argument("--plan", default=str(DEFAULT_PLAN), help="Harvest plan JSON path")
    ap.add_argument("--env", default=".env.local", help="Env file with LSEG credentials")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Output JSON path")
    args = ap.parse_args()

    load_env(args.env)
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        report = run_probe(Path(args.plan) if Path(args.plan).is_absolute() else REPO / args.plan)
    except Exception as exc:
        report = {
            "generated_at": utc_now(),
            "summary": {"all_ok": False, "error": f"{type(exc).__name__}: {exc}"},
            "tiers": [],
        }
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Entitlement probe failed: {exc}", file=sys.stderr)
        return 1

    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Wrote {out_path}")
    return 0 if report["summary"].get("all_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
