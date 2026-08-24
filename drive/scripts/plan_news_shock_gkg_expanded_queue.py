#!/usr/bin/env python3
"""Materialize the expanded-universe GDELT monthly queue (plan-only, no fetch)."""

from __future__ import annotations

import argparse
import gzip
import json
from datetime import date
from pathlib import Path


def parse_ymd(value: str) -> date:
    y, m, d = map(int, value.split("-"))
    return date(y, m, d)


def add_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def month_windows(start: date, end: date, run_tag: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    cur = date(start.year, start.month, 1)
    idx = 0
    while cur < end:
        nxt = min(add_month(cur), end)
        label = f"{cur:%Y%m%d}_{nxt:%Y%m%d}"
        run_id = f"expanded_gkg_window_{label}_{run_tag}"
        rows.append(
            {
                "month_index": idx,
                "start_date": cur.isoformat(),
                "end_date": nxt.isoformat(),
                "run_id": run_id,
            }
        )
        cur = nxt
        idx += 1
    return rows


def artifact_complete(repo_root: Path, run_id: str) -> bool:
    norm = (
        repo_root
        / "data_lake/news_shock_taxonomy/normalized/gdelt_gkg_expanded_bulk"
        / run_id
        / "asia_gkg_filtered.csv.gz"
    )
    scored = (
        repo_root
        / "data_lake/news_shock_taxonomy/processed"
        / run_id
        / "asia_gkg_scored.csv.gz"
    )
    panel = (
        repo_root
        / "data_lake/news_shock_taxonomy/processed"
        / run_id
        / "daily_country_shock_panel.csv"
    )
    if not (norm.is_file() and scored.is_file() and panel.is_file()):
        return False
    try:
        with gzip.open(norm, "rb") as fh:
            fh.read(1)
        with gzip.open(scored, "rb") as fh:
            fh.read(1)
    except OSError:
        return False
    return norm.stat().st_size > 0 and scored.stat().st_size > 0 and panel.stat().st_size > 0


def overlay_complete(repo_root: Path, run_id: str) -> bool:
    overlay_dir = repo_root / "data_lake/news_shock_taxonomy/derived/gdelt_crypto_overlay" / run_id
    return overlay_dir.is_dir() and any(overlay_dir.iterdir())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--queue-start", default="2018-01-01")
    parser.add_argument("--queue-end", default="2026-07-01")
    parser.add_argument("--run-tag", default="20260626TexpandedZ")
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path("data_lake/news_shock_taxonomy/derived/gdelt_expanded_queue_state"),
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    state_dir = (repo_root / args.state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)

    windows = month_windows(parse_ymd(args.queue_start), parse_ymd(args.queue_end), args.run_tag)
    pending: list[dict[str, object]] = []
    complete = 0
    for row in windows:
        run_id = str(row["run_id"])
        done = artifact_complete(repo_root, run_id)
        if done:
            complete += 1
        status = "complete" if done else "pending"
        overlay = overlay_complete(repo_root, run_id) if done else False
        entry = {
            **row,
            "status": status,
            "overlay_complete": overlay,
            "worker_command": (
                "bash scripts/run_news_shock_gkg_expanded_windows_worker.sh "
                f"{run_id} {row['start_date']} {row['end_date']} <WINDOWS_HOST>"
            ),
        }
        pending.append(entry)

    manifest = {
        "generated_at": date.today().isoformat(),
        "queue_start": args.queue_start,
        "queue_end": args.queue_end,
        "run_tag": args.run_tag,
        "partition": "news.gdelt-expanded",
        "countries_config": "config/news_shock_expanded_universe.json",
        "total_months": len(windows),
        "complete_months": complete,
        "pending_months": len(windows) - complete,
        "execute_forward": (
            "QUEUE_START={start} QUEUE_END={end} RUN_TAG={tag} "
            "bash scripts/run_news_shock_gkg_expanded_forward_queue.sh"
        ).format(start=args.queue_start, end=args.queue_end, tag=args.run_tag),
        "execute_work_steal_windows": (
            "QUEUE_START={start} QUEUE_END={end} RUN_TAG={tag} "
            "bash scripts/run_news_shock_gkg_expanded_work_steal_queue.sh helper_<name> windows <WINDOWS_HOST>"
        ).format(start=args.queue_start, end=args.queue_end, tag=args.run_tag),
        "windows": pending,
    }

    manifest_path = state_dir / "queue_manifest.json"
    pending_path = state_dir / "pending_windows.jsonl"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    with pending_path.open("w", encoding="utf-8") as fh:
        for entry in pending:
            if entry["status"] == "pending":
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    summary = (
        f"expanded_queue_planned total={len(windows)} complete={complete} "
        f"pending={len(windows) - complete} manifest={manifest_path}"
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
