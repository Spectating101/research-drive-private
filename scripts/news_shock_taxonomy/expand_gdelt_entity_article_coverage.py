#!/usr/bin/env python3
"""Pull normalized GDELT article windows from GDrive for entity-tier (Tier 3) coverage.

For each country-panel month that exists locally, ensure `asia_gkg_filtered.csv.gz`
is present and gzip-valid under normalized/gdelt_gkg_asia_bulk. Optionally score to
processed/ for richer market_relevance fields.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WINDOW_RE = re.compile(r"^asia_gkg_window_(\d{8})_(\d{8})_")


def _drive_roots() -> list[str]:
    from scripts.research_data_mcp.storage_tiers import gdelt_normalized_drive_roots

    roots = gdelt_normalized_drive_roots(REPO)
    if roots:
        return roots
    return [
        "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/news_shock_taxonomy/gdelt_gkg_asia_backfill_2018_2023/normalized/gdelt_gkg_asia_bulk",
        "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk",
    ]


DRIVE_ROOTS = _drive_roots()
NORMALIZED_ROOT = REPO / "data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk"
PROCESSED_ROOT = REPO / "data_lake/news_shock_taxonomy/processed"
STATE_DIR = REPO / "data_lake/news_shock_taxonomy/derived/gdelt_entity_article_prefetch"
SCORE_SCRIPT = REPO / "scripts/news_shock_taxonomy/score_gdelt_gkg_asia.py"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def panel_window_keys() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for panel in PROCESSED_ROOT.glob("*/daily_country_shock_panel.csv"):
        match = WINDOW_RE.match(panel.parent.name)
        if match:
            keys.add((match.group(1), match.group(2)))
    return keys


def drive_inventory() -> dict[tuple[str, str], tuple[str, str]]:
    out: dict[tuple[str, str], tuple[str, str]] = {}
    for root in DRIVE_ROOTS:
        proc = subprocess.run(
            [
                "rclone",
                "lsf",
                root,
                "--files-only",
                "--recursive",
                "--include",
                "asia_gkg_window_*/asia_gkg_filtered.csv.gz",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            window = line.split("/")[0]
            match = WINDOW_RE.match(window)
            if match:
                out[(match.group(1), match.group(2))] = (root, window)
    return out


def gzip_valid(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 1024:
        return False
    try:
        with gzip.open(path, "rb") as handle:
            while handle.read(1024 * 1024):
                pass
        return True
    except (EOFError, OSError):
        return False


def local_normalized_path(window_name: str) -> Path:
    return NORMALIZED_ROOT / window_name / "asia_gkg_filtered.csv.gz"


def local_scored_path(window_name: str) -> Path:
    return PROCESSED_ROOT / window_name / "asia_gkg_scored.csv.gz"


def find_local_normalized(key: tuple[str, str]) -> Path | None:
    start, end = key
    prefix = f"asia_gkg_window_{start}_{end}_"
    candidates = sorted(
        NORMALIZED_ROOT.glob(f"{prefix}*/asia_gkg_filtered.csv.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        if gzip_valid(path):
            return path
    return None


def find_local_scored(key: tuple[str, str]) -> Path | None:
    start, end = key
    prefix = f"asia_gkg_window_{start}_{end}_"
    candidates = sorted(
        PROCESSED_ROOT.glob(f"{prefix}*/asia_gkg_scored.csv.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        if gzip_valid(path):
            return path
    return None


def pull_window(remote_root: str, window_name: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    remote = f"{remote_root}/{window_name}/asia_gkg_filtered.csv.gz"
    subprocess.run(
        ["rclone", "copyto", remote, str(dest), "--retries", "5", "--low-level-retries", "10"],
        check=True,
    )
    if not gzip_valid(dest):
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"pulled gzip failed validation: {window_name}")


def score_window(input_path: Path) -> Path:
    run_id = input_path.parent.name
    out = local_scored_path(run_id)
    if gzip_valid(out):
        return out
    subprocess.run(
        [
            sys.executable,
            str(SCORE_SCRIPT),
            "--input",
            str(input_path),
            "--run-id",
            run_id,
        ],
        check=True,
        cwd=str(REPO),
    )
    if not gzip_valid(out):
        raise RuntimeError(f"scoring produced invalid gzip: {out}")
    return out


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="Max windows to process (0=all missing)")
    ap.add_argument("--score", action="store_true", help="Also run score_gdelt_gkg_asia after pull")
    ap.add_argument("--force", action="store_true", help="Re-pull even if local file exists")
    ap.add_argument("--start", default="", help="Skip keys before YYYYMMDD start month")
    ap.add_argument("--end", default="", help="Stop after YYYYMMDD end month")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = STATE_DIR / "manifest.jsonl"

    panel_keys = panel_window_keys()
    drive = drive_inventory()
    targets = sorted(panel_keys & drive.keys())
    if args.start:
        targets = [k for k in targets if k[0] >= args.start]
    if args.end:
        targets = [k for k in targets if k[0] <= args.end]

    processed = 0
    summary = {"started_at": now_iso(), "targets": len(targets), "results": []}

    for key in targets:
        if args.limit and processed >= args.limit:
            break
        start, end = key
        remote_root, window_name = drive[key]
        record: dict[str, object] = {
            "window_key": f"{start}_{end}",
            "window_name": window_name,
            "remote_root": remote_root,
            "ts": now_iso(),
        }

        try:
            scored = find_local_scored(key)
            normalized = find_local_normalized(key)
            if scored and not args.force:
                record.update({"action": "skip", "status": "scored_exists", "path": str(scored)})
            elif normalized and not args.force:
                record.update({"action": "skip", "status": "normalized_exists", "path": str(normalized)})
                if args.score:
                    scored = score_window(normalized)
                    record.update({"scored": str(scored), "status": "scored"})
            elif not args.force:
                # Re-pull when a local normalized file exists but is corrupt/truncated.
                stale = local_normalized_path(window_name)
                if stale.exists() and not gzip_valid(stale):
                    stale.unlink(missing_ok=True)
                    record["note"] = "removed_invalid_local_copy"
            if record.get("action"):
                pass
            else:
                dest = local_normalized_path(window_name)
                if dest.exists() and not args.force:
                    dest.unlink()
                pull_window(remote_root, window_name, dest)
                record.update({"action": "pull", "status": "pulled", "path": str(dest)})
                if args.score:
                    scored = score_window(dest)
                    record.update({"scored": str(scored), "status": "scored"})
                processed += 1
        except Exception as exc:
            record.update({"action": "error", "status": "failed", "error": str(exc)})
            processed += 1

        with manifest_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        summary["results"].append(record)
        print(json.dumps(record, separators=(",", ":")), flush=True)

    summary["finished_at"] = now_iso()
    summary["processed"] = processed
    (STATE_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
