#!/usr/bin/env python3
"""Restore last-known-good Refinitiv entitlement map after session outage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs/status/generated/refinitiv_value_entitlement_map.json"

ASIA_PIT_VARIANTS = [
    {"ok": True, "variant": "pit_0hash_sdate", "ric": "0#.TWII", "index_ric": ".TWII", "parameters": {"SDate": "20200115"}},
    {"ok": True, "variant": "pit_0hash_sdate", "ric": "0#.N225", "index_ric": ".N225", "parameters": {"SDate": "20200115"}},
    {"ok": True, "variant": "pit_0hash_sdate", "ric": "0#.KSE", "index_ric": ".KS11", "parameters": {"SDate": "20200115"}},
    {"ok": True, "variant": "pit_0hash_sdate", "ric": "0#.STI", "index_ric": ".STI", "parameters": {"SDate": "20200115"}},
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    report = {
        "generated_at": utc_now(),
        "restored": True,
        "priority_path": str(REPO / "config/refinitiv_collection_priority.json"),
        "summary": {"categories_total": 12, "pass": 9, "partial": 0, "fail": 3},
        "constituent_api_recommendation": {
            "method": "get_data",
            "variant": "pit_0hash_sdate",
            "ric_pattern": "0#.SPX",
            "parameters": {"SDate": "20180115"},
            "fields": ["TR.IndexConstituentRIC", "TR.IndexConstituentName"],
        },
        "categories": {
            "B1_B6_security_master": {"category_id": "B1_B6_security_master", "status": "pass"},
            "B7_B8_index_constituents": {
                "category_id": "B7_B8_index_constituents",
                "status": "pass",
                "probe": {
                    "ok": True,
                    "variants": [
                        {"ok": True, "variant": "pit_0hash_sdate", "ric": "0#.SPX", "index_ric": ".SPX"},
                        {"ok": True, "variant": "pit_0hash_sdate", "ric": "0#.JKSE", "index_ric": ".JKSE"},
                    ],
                    "best_variant": {"ok": True, "variant": "pit_0hash_sdate", "ric": "0#.SPX"},
                },
            },
            "B8_asia_pit_indices": {
                "category_id": "B8_asia_pit_indices",
                "status": "pass",
                "probe": {"ok": True, "variants": ASIA_PIT_VARIANTS, "best_variant": ASIA_PIT_VARIANTS[0]},
            },
            "C1_C5_corporate_actions": {"category_id": "C1_C5_corporate_actions", "status": "pass"},
            "A9_A11_risk": {"category_id": "A9_A11_risk", "status": "pass"},
            "D8_pit_fundamentals": {
                "category_id": "D8_pit_fundamentals",
                "status": "pass",
                "recommended_harvest": {
                    "method": "fundamental_and_reference.Definition",
                    "label": "frq_fy",
                    "parameters": {"SDate": "0", "EDate": "-20", "FRQ": "FY"},
                    "fields": [
                        "TR.Revenue",
                        "TR.NetIncome",
                        "TR.F.TotRevenue",
                        "TR.TotalDebt",
                        "TR.FreeCashFlow",
                        "TR.BookValuePerShare",
                    ],
                },
                "probe": {
                    "ok": True,
                    "best_variant": {
                        "label": "frq_fy",
                        "ok": True,
                        "parameters": {"SDate": "0", "EDate": "-20", "FRQ": "FY"},
                    },
                },
            },
            "E4_estimate_revisions": {"category_id": "E4_estimate_revisions", "status": "pass"},
            "E1_E3_consensus_snapshot": {"category_id": "E1_E3_consensus_snapshot", "status": "pass"},
            "H1_esg_snapshot": {"category_id": "H1_esg_snapshot", "status": "pass"},
            "G1_ownership": {"category_id": "G1_ownership", "status": "fail"},
            "I1_supply_chain": {"category_id": "I1_supply_chain", "status": "fail"},
            "F1_starmine_probe": {"category_id": "F1_starmine_probe", "status": "fail"},
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Restored {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
