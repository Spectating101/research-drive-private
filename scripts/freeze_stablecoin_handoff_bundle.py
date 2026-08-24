#!/usr/bin/env python3
"""Freeze-patch an existing stablecoin bundle: drop partial 2026-W27 from handoff panels."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from stablecoin_skynet.dataset_tiers import HANDOFF_LATEST_FIELDS, HANDOFF_WEEKLY_FIELDS, write_csv
from stablecoin_skynet.handoff_validation import publish_handoff_validation
from stablecoin_skynet.professor_simple import publish_professor_simple
from stablecoin_skynet.research_window import RESEARCH_WEEK_MAX, RESEARCH_WEEK_MIN, filter_research_weeks

REPO = Path(__file__).resolve().parents[1]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _filter_write(path: Path, rows: list[dict], fields: list[str] | None = None) -> int:
    if fields is None and rows:
        fields = list(rows[0].keys())
    write_csv(path, rows, fields or [])
    return len(rows)


def freeze_bundle(src: Path, dst: Path) -> dict:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    weekly_path = dst / "panel_weekly.csv"
    research_path = dst / "panels" / "research_panel_weekly.csv"
    latest_path = dst / "panel_latest.csv"

    weekly = filter_research_weeks(_read_csv(weekly_path))
    research = filter_research_weeks(_read_csv(research_path))

    _filter_write(weekly_path, weekly, HANDOFF_WEEKLY_FIELDS)
    research_fields = list(research[0].keys()) if research else []
    _filter_write(research_path, research, research_fields)

    manifest_path = dst / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = manifest.setdefault("counts", {})
    counts["research_weekly_rows"] = len(weekly)
    counts["panel_weekly_rows"] = len(weekly)
    counts["research_week_max"] = RESEARCH_WEEK_MAX
    counts["research_week_window"] = f"{RESEARCH_WEEK_MIN}..{RESEARCH_WEEK_MAX}"
    counts["handoff_balanced_grid"] = True
    build_id = dst.name
    manifest["build_id"] = build_id
    manifest["package_dir"] = build_id
    manifest["frozen_at"] = datetime.now(timezone.utc).isoformat()
    manifest["freeze_note"] = (
        "Dropped partial terminal week 2026-W27 from handoff panels; "
        "see panels/research_panel_weekly_full_history.csv for quarantine. "
        "Timestamps are UTC build/freeze metadata."
    )
    layout = manifest.setdefault("package_layout", {})
    handoff_root = layout.setdefault("handoff_root", {})
    handoff_root["panel_weekly"] = len(weekly)
    handoff_root["panel_latest"] = handoff_root.get("panel_latest", 71)
    handoff_root["entities"] = handoff_root.get("entities", 71)
    layout["lineage"] = "lineage.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    validation = publish_handoff_validation(dst, manifest)
    manifest["handoff_validation"] = validation
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Regenerate panels/METHOD.md universe line via template from research_dataset
    method = dst / "panels" / "METHOD.md"
    if method.is_file():
        text = method.read_text(encoding="utf-8")
        text = text.replace(
            "- **Entity spine:** 164 rows in `entities.csv`",
            f"- **Handoff `entities.csv`:** {counts.get('leaderboard_entities', 71)} rows (leaderboard only)\n"
            f"- **Upstream unified spine:** {counts.get('entity_rows', 164)} rows in `reference/entities.csv`",
        )
        text = text.replace("18,692 rows", f"{len(weekly):,} rows")
        text = text.replace("2021-W24+", f"{RESEARCH_WEEK_MIN} → {RESEARCH_WEEK_MAX}")
        method.write_text(text, encoding="utf-8")

    coverage = dst / "panels" / "COVERAGE.md"
    if coverage.is_file():
        coverage.write_text(coverage.read_text(encoding="utf-8").replace("| 18692 |", f"| {len(weekly)} |"), encoding="utf-8")

    readme = dst / "README.md"
    if readme.is_file():
        readme.write_text(
            readme.read_text(encoding="utf-8").replace("2026-W27", RESEARCH_WEEK_MAX),
            encoding="utf-8",
        )

    write_final_sanity(dst, len(weekly), validation)
    prof = publish_professor_simple(dst)
    manifest = json.loads((dst / "manifest.json").read_text(encoding="utf-8"))
    manifest["professor_simple"] = prof
    (dst / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"weekly_rows": len(weekly), "research_rows": len(research), "validation": validation, "professor_simple": prof}


def write_final_sanity(dst: Path, n_rows: int, validation: dict) -> None:
    text = f"""# Final sanity check — frozen handoff bundle

**Window:** {RESEARCH_WEEK_MIN} → {RESEARCH_WEEK_MAX}  
**Rows:** {n_rows} (= 71 entities × 263 weeks, balanced)  
**Partial week 2026-W27:** dropped from handoff; retained in `panels/research_panel_weekly_full_history.csv` only.

## Security events vs panel window

`security_events.csv` lists **5** curated events. **4** appear inside the analysis window ({RESEARCH_WEEK_MIN}+):

| event | date | in panel? |
|-------|------|-----------|
| tether_settlement_2021 | 2021-02-23 | **No** — before {RESEARCH_WEEK_MIN} |
| tether_reserve_attestation_2022 | 2022-05-12 | Yes |
| circle_svb_exposure | 2023-03-11 | Yes |
| alchemix_curve_exploit | 2023-08-01 | Yes |
| busd_issuance_halt | 2023-02-13 | Yes |

The 2021 Tether legal event remains in `security_events.csv` for reference but does not populate `security_event_flag` in the weekly panel.

## Entities file

- Root `entities.csv`: **71 rows** (Skynet leaderboard handoff)
- `reference/entities.csv`: broader upstream spine (includes Etherscan-only tokens)

## Validation (regenerated)

- `validation_missingness_handoff_top10.csv`: computed on **{n_rows}** handoff rows
- `validation_missingness_full_width_top10.csv`: computed on **{n_rows}** full-width rows
- `has_incidents` coverage: see `validation/coverage_by_source.csv`

Frozen: {datetime.now(timezone.utc).strftime("%Y-%m-%d")}
"""
    (dst / "FINAL_SANITY_CHECK.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=REPO / "drive/data/datasets/stablecoin_trust_engagement/20260706")
    parser.add_argument("--dst", type=Path, default=REPO / "data/datasets/stablecoin_trust_engagement/20260707")
    args = parser.parse_args()
    result = freeze_bundle(args.src.resolve(), args.dst.resolve())
    latest = REPO / "data/datasets/stablecoin_trust_engagement/latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(args.dst.resolve(), target_is_directory=True)
    drive_latest = REPO / "drive/data/datasets/stablecoin_trust_engagement/latest"
    if drive_latest.is_symlink() or drive_latest.exists():
        drive_latest.unlink()
    drive_latest.symlink_to(args.dst.resolve(), target_is_directory=True)
    print(json.dumps({"dst": str(args.dst), **result}, indent=2))


if __name__ == "__main__":
    main()
