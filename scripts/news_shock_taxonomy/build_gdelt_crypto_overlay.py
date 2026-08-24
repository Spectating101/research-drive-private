#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROCESSED = REPO / "data_lake/news_shock_taxonomy/processed"
NORMALIZED = REPO / "data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk"
DEFAULT_CONFIG = REPO / "config/gdelt_crypto_overlay.json"
DEFAULT_OUT = REPO / "data_lake/news_shock_taxonomy/derived/gdelt_crypto_overlay"
WINDOW_RE = re.compile(r"^asia_gkg_window_(\d{8})_(\d{8})_")
csv.field_size_limit(sys.maxsize)


def canonical_windows() -> list[Path]:
    choices: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for panel in PROCESSED.glob("*/daily_country_shock_panel.csv"):
        match = WINDOW_RE.match(panel.parent.name)
        if match:
            choices[(match.group(1), match.group(2))].append(panel.parent)
    selected = []
    for _, paths in sorted(choices.items()):
        paths.sort(key=lambda p: (p / "daily_country_shock_panel.csv").stat().st_mtime, reverse=True)
        selected.append(paths[0])
    return selected


def compile_patterns(values: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(value, re.IGNORECASE) for value in values]


def matches(text: str, patterns: dict[str, list[re.Pattern[str]]]) -> list[str]:
    return [topic for topic, expressions in patterns.items() if any(exp.search(text) for exp in expressions)]


def process_window(directory: Path, out_root: Path, assets, events, source_override: Path | None = None) -> dict:
    source = (source_override or (NORMALIZED / directory.name / "asia_gkg_filtered.csv.gz")).resolve()
    if not source.exists():
        return {"window": directory.name, "status": "missing_normalized_input"}
    out_dir = out_root / directory.name
    out_dir.mkdir(parents=True, exist_ok=True)
    final_evidence = out_dir / "crypto_event_evidence.csv.gz"
    final_panel = out_dir / "daily_country_crypto_panel.csv"
    final_summary = out_dir / "summary.json"
    if final_summary.exists() and final_evidence.exists() and final_panel.exists():
        return json.loads(final_summary.read_text(encoding="utf-8"))

    evidence_partial = final_evidence.with_suffix(final_evidence.suffix + ".partial")
    panel_counts: dict[tuple[str, str], Counter] = defaultdict(Counter)
    seen_evidence = set()
    rows = matched = 0
    asset_counts = Counter()
    event_counts = Counter()
    fields = ["date", "country_iso3", "source_common_name", "document_identifier", "asset_topics", "event_topics", "shock_hints", "tone_avg"]

    with gzip.open(source, "rt", encoding="utf-8", errors="replace", newline="") as src, gzip.open(
        evidence_partial, "wt", encoding="utf-8", newline=""
    ) as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=fields)
        writer.writeheader()
        for row in reader:
            rows += 1
            text = " ".join(
                row.get(key, "")
                for key in ("document_identifier", "themes", "organizations", "source_common_name")
            )
            asset_topics = matches(text, assets)
            if not asset_topics:
                continue
            event_topics = matches(text, events)
            matched += 1
            asset_counts.update(asset_topics)
            event_counts.update(event_topics)
            key = (row.get("date", ""), row.get("country_iso3", ""))
            panel_counts[key]["crypto_rows"] += 1
            for topic in asset_topics:
                panel_counts[key][f"asset_{topic}_rows"] += 1
            for topic in event_topics:
                panel_counts[key][f"event_{topic}_rows"] += 1
            evidence_key = (key[0], key[1], row.get("document_identifier", ""))
            if evidence_key not in seen_evidence:
                seen_evidence.add(evidence_key)
                writer.writerow({
                    "date": key[0],
                    "country_iso3": key[1],
                    "source_common_name": row.get("source_common_name", ""),
                    "document_identifier": row.get("document_identifier", ""),
                    "asset_topics": "|".join(asset_topics),
                    "event_topics": "|".join(event_topics),
                    "shock_hints": row.get("shock_hints", ""),
                    "tone_avg": row.get("tone_avg", ""),
                })

    evidence_partial.replace(final_evidence)
    topic_columns = [f"asset_{topic}_rows" for topic in assets] + [f"event_{topic}_rows" for topic in events]
    with final_panel.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "country_iso3", "crypto_rows", *topic_columns])
        writer.writeheader()
        for (date, country), counts in sorted(panel_counts.items()):
            writer.writerow({"date": date, "country_iso3": country, **{column: counts[column] for column in ["crypto_rows", *topic_columns]}})

    try:
        input_ref = str(source.relative_to(REPO.resolve()))
    except ValueError:
        input_ref = str(source)
    summary = {
        "window": directory.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "input": input_ref,
        "rows_scanned": rows,
        "crypto_rows": matched,
        "unique_evidence_rows": len(seen_evidence),
        "asset_counts": dict(asset_counts),
        "event_counts": dict(event_counts),
    }
    final_summary.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-windows", type=int, default=0)
    parser.add_argument("--source-file", type=Path)
    parser.add_argument("--window-name")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    assets = {key: compile_patterns(value) for key, value in config["asset_topics"].items()}
    events = {key: compile_patterns(value) for key, value in config["event_topics"].items()}
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.source_file:
        if not args.window_name:
            parser.error("--window-name is required with --source-file")
        result = process_window(Path(args.window_name), args.out_dir, assets, events, args.source_file)
        manifest_path = args.out_dir / "manifest.json"
        manifest = []
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = [item for item in manifest if item.get("window") != result.get("window")]
        manifest.append(result)
        manifest.sort(key=lambda item: item.get("window", ""))
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({"progress": "1/1", **result}, separators=(",", ":")), flush=True)
        return

    windows = canonical_windows()
    if args.max_windows:
        windows = windows[: args.max_windows]
    manifest = []
    for index, window in enumerate(windows, 1):
        result = process_window(window, args.out_dir, assets, events)
        manifest.append(result)
        (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({"progress": f"{index}/{len(windows)}", **result}, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
