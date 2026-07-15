"""JKSE PIT × IDN microstructure × estimate revisions synthesis."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.build_jkse_pit_idn_microstructure_revisions import (
    PANEL_FILE,
    build_coverage_summary,
    build_panel,
)


def run_jkse_pit_idn_synthesis(
    repo_root: Path,
    profile: dict[str, Any],
    *,
    preview_limit: int = 20,
) -> dict[str, Any]:
    paths = profile.get("paths") or {}
    refinitiv_run = str(paths.get("refinitiv_run", "2026-07-06-complete"))
    pit_path = repo_root / f"data_lake/refinitiv_backfill/{refinitiv_run}/processed/index_membership_pit.parquet"
    spine_path = repo_root / f"data_lake/research_panels/refinitiv/{refinitiv_run}/entity_market_spine.parquet"
    est_path = repo_root / f"data_lake/research_panels/refinitiv/{refinitiv_run}/estimate_revision_panel.parquet"
    idn_path = repo_root / str(paths.get("idn_daily", "data_lake/research_panels/idn_fry_episode/daily_cross_section.parquet"))

    panel = build_panel(
        pit_path=pit_path,
        spine_path=spine_path,
        est_path=est_path,
        idn_path=idn_path,
    )
    summary = build_coverage_summary(panel)

    publish_dir = repo_root / str(paths.get("publish_dir", "data_lake/research_panels/jkse_pit_idn"))
    publish_dir.mkdir(parents=True, exist_ok=True)
    panel_path = publish_dir / PANEL_FILE
    panel.to_parquet(panel_path, index=False)

    subdir = profile.get("output_subdir") or profile.get("id") or "jkse_pit_idn"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = repo_root / "data_lake" / "synthesis" / subdir / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    run_panel = run_dir / PANEL_FILE
    shutil.copy2(panel_path, run_panel)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile_id": profile.get("id"),
        "refinitiv_run": refinitiv_run,
        "summary": summary,
        "assumptions": profile.get("assumptions") or [],
        "publish_panel": str(panel_path.relative_to(repo_root)),
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (publish_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    preview_cols = [
        c
        for c in [
            "as_of_month",
            "ric",
            "yahoo_symbol",
            "company_name",
            "has_idn_features",
            "has_estimates",
            "idn_mean_return_1d",
            "idn_chase_days",
            "est_revision_1m",
        ]
        if c in panel.columns
    ]
    preview = panel.loc[panel["has_idn_features"] == 1, preview_cols].head(preview_limit).to_dict(orient="records")

    latest_pointer = repo_root / "data_lake" / "synthesis" / subdir / "latest.json"
    latest_pointer.parent.mkdir(parents=True, exist_ok=True)
    latest_pointer.write_text(
        json.dumps(
            {
                "profile_id": profile.get("id"),
                "generated_at": manifest["generated_at"],
                "run_dir": str(run_dir.relative_to(repo_root)),
                "summary": summary,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "profile_id": profile.get("id"),
        "title": profile.get("title"),
        "type": "jkse_pit_idn",
        "generated_at": manifest["generated_at"],
        "summary": summary,
        "preview": preview,
        "research_questions": profile.get("research_questions") or [],
        "artifacts": {
            "panel_parquet": str(panel_path.relative_to(repo_root)),
            "manifest_json": str(manifest_path.relative_to(repo_root)),
            "latest_pointer": str(latest_pointer.relative_to(repo_root)),
        },
    }
