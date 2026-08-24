#!/usr/bin/env python3
"""Dataset-level coverage map: probed panels, collection bulk vs surface, proxy/synthetic paths."""

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
        "# Databank dataset coverage map",
        "",
        f"Generated: {audit.get('generated_at')}",
        "",
        audit.get("principle", ""),
        "",
        "## Summary",
        "",
    ]
    s = audit.get("summary") or {}
    lines.append(f"- Datasets profiled: **{s.get('registry_datasets_profiled')}** ({s.get('instant_datasets')} instant)")
    lines.append(f"- Materialized instant panels: **{s.get('materialized_instant')}** (disk probed: {s.get('disk_probed')})")
    lines.append(f"- Collection partitions: **{s.get('collection_partitions')}**")
    if s.get("bulk_rich_thin_surface"):
        lines.append(f"- Bulk-rich / thin registry surface: `{', '.join(s['bulk_rich_thin_surface'])}`")
    lines.append(f"- Proxy capability blocks: **{s.get('proxy_blocks')}**")
    lines.extend(["", "## Collections (bulk vs registry surface)", ""])
    for c in audit.get("collection_profiles") or []:
        if not (c.get("local_bytes") or c.get("bulk_profile", {}).get("latent_capabilities")):
            continue
        bp = c.get("bulk_profile") or {}
        lines.append(f"### {c.get('title')} (`{c.get('partition_id')}`)")
        lines.append(
            f"- Disk: {c.get('local_bytes_human')} · instant cards: {c.get('instant_card_count')} · "
            f"registry cards: {c.get('registry_card_count')}"
        )
        if bp.get("time_span"):
            lines.append(f"- Time span: {bp['time_span']}")
        if bp.get("latent_capabilities"):
            lines.append(f"- Latent capabilities: {', '.join(bp['latent_capabilities'])}")
        if bp.get("surface_vs_bulk"):
            lines.append(f"- Surface vs bulk: {bp['surface_vs_bulk']}")
        if bp.get("synthetic_paths"):
            lines.append("- Synthetic paths:")
            for sp in bp["synthetic_paths"]:
                lines.append(f"  - {sp}")
        lines.append("")

    lines.extend(["", "## Instant datasets with disk coverage", ""])
    for d in audit.get("dataset_profiles") or []:
        if d.get("analysis_readiness") != "instant":
            continue
        probe = d.get("disk_probe") or {}
        if not probe.get("row_count") and not probe.get("row_count_sampled"):
            continue
        rows = probe.get("row_count") or probe.get("row_count_sampled")
        tspan = ""
        if probe.get("time_min"):
            tspan = f" · {probe['time_min']} → {probe['time_max']}"
        caps = ", ".join(d.get("research_capabilities") or []) or "—"
        geos = ", ".join(d.get("geographies") or []) or "—"
        lines.append(
            f"- **`{d['dataset_id']}`** — {rows:,} rows{tspan} · caps: {caps} · geo: {geos}"
        )
        if d.get("known_gap"):
            lines.append(f"  - Gap: {d['known_gap']}")

    lines.extend(["", "## Proxy & synthetic coverage paths", ""])
    for block in audit.get("proxy_coverage") or []:
        lines.append(
            f"### {block.get('target_geography')} × `{block.get('target_capability')}` "
            f"(effective rank {block.get('effective_rank')})"
        )
        for p in block.get("paths") or []:
            lines.append(f"- [{p.get('kind')}] {p.get('label')} — **{p.get('status')}** (rank {p.get('rank')})")
        lines.append("")

    lines.extend(["", "## Built synthesis recipes", ""])
    for s in audit.get("synthesis_profiles") or []:
        lines.append(f"- **{s.get('title')}** (`{s.get('id')}`) — joins: {', '.join(s.get('join_keys') or [])}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    from scripts.research_data_mcp.dataset_coverage import build_dataset_coverage_audit

    audit = build_dataset_coverage_audit(ROOT)
    if args.json:
        out_dir = ROOT / "docs/status/generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "databank_dataset_coverage.json"
        md_path = out_dir / "databank_dataset_coverage.md"
        json_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        md_path.write_text(_render_md(audit), encoding="utf-8")
        drive_dir = ROOT / "drive/docs/status/generated"
        drive_dir.mkdir(parents=True, exist_ok=True)
        (drive_dir / "databank_dataset_coverage.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
        (drive_dir / "databank_dataset_coverage.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Wrote {json_path}")
    else:
        s = audit["summary"]
        print(
            f"profiled={s.get('registry_datasets_profiled')} instant={s.get('instant_datasets')} "
            f"materialized={s.get('materialized_instant')} probed={s.get('disk_probed')}"
        )
        for pid in s.get("bulk_rich_thin_surface") or []:
            print(f"  bulk-rich thin-surface: {pid}")
        for block in (audit.get("proxy_coverage") or [])[:8]:
            print(
                f"  proxy {block.get('target_geography'):12} {block.get('target_capability'):22} "
                f"effective={block.get('effective_rank')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
