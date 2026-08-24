#!/usr/bin/env python3
"""Audit desk entitlements (what we CAN access) vs materialized coverage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "kernel") not in sys.path:
    sys.path.insert(0, str(REPO / "kernel"))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)

CAP_SHORT = {
    "daily_prices": "Prices",
    "country_news_shocks": "CtyNews",
    "entity_news_shocks": "EntNews",
    "fundamentals": "Fund",
    "estimates_revisions": "Est/Rev",
    "index_pit_survivorship": "PIT",
    "risk_overlay": "Risk",
    "entity_join_gdelt_ric": "Join",
    "governance_regulatory": "Gov",
    "social_sentiment": "Social",
    "onchain_crypto": "Chain",
}


def _render_md(audit: dict) -> str:
    lines = [
        "# Databank access scope (entitlements vs materialized)",
        "",
        f"Generated: {audit.get('generated_at')}",
        "",
        audit.get("principle", ""),
        "",
        "## Summary",
        "",
    ]
    s = audit.get("summary") or {}
    lines.append(f"- Entitlement sources: **{s.get('entitlement_sources')}**")
    lines.append(
        f"- Accessible cells (partial+): **{s.get('accessible_cells_ge_2')}** / {s.get('total_cells')}"
    )
    lines.append(f"- Gap cells (reachable but thin/absent on disk): **{s.get('gap_cells')}**")
    if s.get("not_wired_sources"):
        lines.append(f"- Not wired (licensed, no ingest): `{', '.join(s['not_wired_sources'])}`")
    lines.append(f"- Materialized matrix loaded: **{s.get('materialized_matrix_loaded')}**")
    lines.extend(["", "## Entitlement heatmap (what we CAN reach)", ""])
    ent = audit.get("entitlement_matrix") or {}
    caps = list((audit.get("combined_matrix") or {}).get(next(iter(ent), ""), {}).keys()) if ent else []
    if not caps and ent:
        caps = list(next(iter(ent.values())).keys())
    cap_labels = [CAP_SHORT.get(c, c) for c in caps]
    lines.append("| Geography | " + " | ".join(cap_labels) + " |")
    lines.append("|" + "---|" * (len(cap_labels) + 1))
    for geo, row in ent.items():
        cells = [row.get(c, "—") for c in caps]
        lines.append(f"| {geo} | " + " | ".join(cells) + " |")

    if audit.get("materialized_matrix"):
        lines.extend(["", "## Materialized heatmap (0–3 instant-panel scores)", ""])
        mat = audit["materialized_matrix"]
        lines.append("| Geography | " + " | ".join(cap_labels) + " |")
        lines.append("|" + "---|" * (len(cap_labels) + 1))
        for geo, row in mat.items():
            cells = [str(row.get(c, 0)) for c in caps]
            lines.append(f"| {geo} | " + " | ".join(cells) + " |")

    lines.extend(["", "## Priority gaps (accessible but not materialized)", ""])
    for cell in audit.get("priority_gaps") or []:
        lines.append(
            f"- **{cell['geography']}** × `{cell['capability']}` — accessible `{cell['accessible']}`, "
            f"materialized {cell.get('materialized_score')} ({cell['gap']}) via {', '.join(cell.get('sources') or [])}"
        )

    lines.extend(["", "## Sources (entitlement view)", ""])
    for row in audit.get("sources") or []:
        lines.append(f"### `{row.get('source_id')}` — {row.get('subscription_status')}")
        if row.get("license_holder"):
            lines.append(f"- License: {row['license_holder']}")
        if row.get("fetch_modes"):
            lines.append(f"- Fetch: {', '.join(row['fetch_modes'])}")
        if row.get("reachable_products"):
            lines.append(f"- Products: {'; '.join(row['reachable_products'][:6])}")
        if row.get("license_blocks"):
            for blk in row["license_blocks"]:
                lines.append(f"- **Blocked:** {blk.get('capability')} — {blk.get('reason')}")
        if row.get("notes"):
            lines.append(f"- Note: {row['notes']}")
        lines.append("")

    probe = audit.get("refinitiv_entitlement_probe")
    if probe:
        lines.extend(["## LSEG entitlement probe (frozen run)", ""])
        sm = probe.get("summary") or {}
        lines.append(f"- Run: `{probe.get('canonical_run_id')}` — pass {sm.get('pass')}, fail {sm.get('fail')}")
        for blk in probe.get("blocked_categories") or []:
            lines.append(f"- Blocked: {blk.get('description')} — {blk.get('reason')}")
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="Write JSON + MD to docs/status/generated/")
    args = ap.parse_args()

    from scripts.research_data_mcp.access_scope import build_access_coverage_audit

    audit = build_access_coverage_audit(ROOT)
    if args.json:
        out_dir = ROOT / "docs/status/generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "databank_access_scope.json"
        md_path = out_dir / "databank_access_scope.md"
        json_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        md_path.write_text(_render_md(audit), encoding="utf-8")
        drive_dir = ROOT / "drive/docs/status/generated"
        drive_dir.mkdir(parents=True, exist_ok=True)
        (drive_dir / "databank_access_scope.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
        (drive_dir / "databank_access_scope.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Wrote {json_path}")
    else:
        s = audit["summary"]
        print(
            f"entitlement_sources={s.get('entitlement_sources')} "
            f"accessible_cells={s.get('accessible_cells_ge_2')}/{s.get('total_cells')} "
            f"gaps={s.get('gap_cells')}"
        )
        if s.get("not_wired_sources"):
            print(f"  not_wired: {', '.join(s['not_wired_sources'])}")
        for cell in (audit.get("priority_gaps") or [])[:12]:
            print(
                f"  gap {cell['geography']:12} {cell['capability']:24} "
                f"access={cell['accessible']:12} mat={cell.get('materialized_score')} ({cell['gap']})"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
