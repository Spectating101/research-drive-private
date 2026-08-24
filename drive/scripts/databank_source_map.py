#!/usr/bin/env python3
"""Audit registry ↔ canonical source map; optional registry source_id stamp."""

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


def _render_md(audit: dict) -> str:
    lines = [
        "# Databank source map audit",
        "",
        f"Generated: {audit.get('generated_at')}",
        "",
        "## Summary",
        "",
    ]
    s = audit.get("summary") or {}
    lines.append(f"- Registry datasets: **{s.get('registry_datasets')}**")
    lines.append(f"- Mapped to a source system: **{s.get('mapped_datasets')}**")
    lines.append(f"- Unmapped: **{s.get('unmapped_datasets')}**")
    lines.append(f"- Source systems defined: **{s.get('source_systems')}**")
    if s.get("orphan_desk_connectors"):
        lines.append(f"- Desk connectors without source map entry: `{', '.join(s['orphan_desk_connectors'])}`")
    lines.extend(["", "## Sources", ""])
    for row in audit.get("sources") or []:
        mat = row.get("materialization") or {}
        ingested = mat.get("ingested")
        ing_label = "yes" if ingested is True else ("no" if ingested is False else "live/partial")
        lines.append(f"### {row.get('label')} (`{row.get('id')}`)")
        lines.append(
            f"- **Mode:** {row.get('access_mode')} · **Status:** {row.get('status')} · "
            f"**Materialized:** {ing_label} · **Registry cards:** {row.get('registry_dataset_count')} "
            f"({row.get('instant_dataset_count')} instant)"
        )
        if row.get("desk_connector_label"):
            lines.append(f"- **Desk connector:** {row.get('desk_connector_label')}")
        if row.get("capabilities"):
            lines.append(f"- **Capabilities:** {', '.join(row['capabilities'])}")
        if row.get("geographies"):
            lines.append(f"- **Geographies:** {', '.join(row['geographies'])}")
        if row.get("known_gaps"):
            lines.append(f"- **Gaps:** {'; '.join(row['known_gaps'])}")
        if row.get("bulk_note"):
            lines.append(f"- **Bulk:** {row['bulk_note']}")
        if row.get("notes"):
            lines.append(f"- **Note:** {row['notes']}")
        lines.append("")
    if audit.get("unmapped_registry_ids"):
        lines.extend(["## Unmapped registry IDs", ""])
        for did in audit["unmapped_registry_ids"][:30]:
            lines.append(f"- `{did}`")
        if len(audit["unmapped_registry_ids"]) > 30:
            lines.append(f"- … and {len(audit['unmapped_registry_ids']) - 30} more")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="Write JSON to docs/status/generated/")
    ap.add_argument("--stamp-registry", action="store_true", help="Write source_id on registry cards")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from scripts.research_data_mcp.source_map import build_source_map_audit, stamp_registry_sources

    audit = build_source_map_audit(ROOT)
    if args.json:
        out_dir = ROOT / "docs/status/generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "databank_source_map.json"
        md_path = out_dir / "databank_source_map.md"
        json_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        md_path.write_text(_render_md(audit), encoding="utf-8")
        drive_dir = ROOT / "drive/docs/status/generated"
        drive_dir.mkdir(parents=True, exist_ok=True)
        (drive_dir / "databank_source_map.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
        (drive_dir / "databank_source_map.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Wrote {json_path}")
    else:
        s = audit["summary"]
        print(f"registry={s.get('registry_datasets')} mapped={s.get('mapped_datasets')} unmapped={s.get('unmapped_datasets')}")
        for row in audit.get("sources") or []:
            if row.get("registry_dataset_count") or row.get("access_mode") == "planned":
                print(
                    f"  {row['id']:28} {row.get('access_mode',''):22} "
                    f"cards={row.get('registry_dataset_count',0):3} instant={row.get('instant_dataset_count',0):2} "
                    f"{row.get('label','')}"
                )

    if args.stamp_registry:
        stamp = stamp_registry_sources(ROOT, dry_run=args.dry_run)
        print(json.dumps(stamp, indent=2))

    return 0 if not audit.get("unmapped_registry_ids") else 0


if __name__ == "__main__":
    raise SystemExit(main())
