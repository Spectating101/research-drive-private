#!/usr/bin/env python3
"""Data lineage audit for IDX episode + reward dataset."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_episode_reward_lib import OUT_DIR, audit_data_lineage, build_episode_dataset  # noqa: E402

OUT = REPO / "backtests/outputs/idn_behavior_model"


def main() -> int:
    df = build_episode_dataset()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_DIR / "daily_episodes.parquet", index=False)

    report = audit_data_lineage(df)
    OUT.mkdir(parents=True, exist_ok=True)
    out_json = OUT / "data_lineage_audit.json"
    out_md = OUT / "data_lineage_audit.md"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# IDX episode data lineage audit",
        "",
        f"Generated: {report.get('generated_at', '')}",
        "",
        "## Universe",
        f"- Liquid core: **{report['universe']['liquid_core_n']}**",
        f"- Episode universe: **{report['universe']['episode_universe_n']}**",
        f"- Added vs liquid: {', '.join(report['universe']['added_vs_liquid']) or '(none)'}",
        "",
        "## Source timelines",
        "",
    ]
    for name, meta in report.get("sources", {}).items():
        lines.append(f"### {name}")
        for k, v in meta.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    lines.extend(["## Weekly cross-ref coverage by year", ""])
    lines.append("| year | rows | entity_tone% | broadcast_news% | prior_return% |")
    lines.append("|------|------|--------------|-----------------|---------------|")
    for row in report.get("weekly_crossref_by_year", []):
        lines.append(
            f"| {row['year']} | {row['rows']} | {row['entity_tone_pct']} | "
            f"{row['broadcast_news_pct']} | {row['prior_return_pct']} |"
        )

    lines.extend(["", "## Episode rows by year", ""])
    lines.append("| year | rows | syms | regime% | entity% | broadcast% | full_crossref% |")
    lines.append("|------|------|------|---------|---------|------------|----------------|")
    for row in report.get("episodes_by_year", []):
        lines.append(
            f"| {row['year']} | {row['rows']} | {row['symbols']} | {row['regime_pct']} | "
            f"{row['entity_tone_pct']} | {row['broadcast_news_pct']} | {row.get('full_crossref_pct', 'n/a')} |"
        )

    lines.extend(["", "## Known gaps", ""])
    for g in report.get("known_gaps", []):
        lines.append(f"- {g}")

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "json": str(out_json), "md": str(out_md)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
