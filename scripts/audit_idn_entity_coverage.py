#!/usr/bin/env python3
"""Audit IDX entity-news coverage — explains gaps before factor research.

Outputs:
  backtests/outputs/platform/idn_entity_coverage/latest.json
  backtests/outputs/platform/idn_entity_coverage/latest.md
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from idn_eval_splits import time_cutoff  # noqa: E402

OUT = REPO / "backtests/outputs/platform/idn_entity_coverage"
ENTITY_PANEL = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/ticker_week_entity_market_panel.parquet"
BROADCAST_PANEL = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
UNIVERSE_CFG = REPO / "config/markets/asia_yfinance_universes.json"
OVERLAY_ROOT = REPO / "data_lake/news_shock_taxonomy/derived/gdelt_entity_ticker_overlay"
PROCESSED_ROOT = REPO / "data_lake/news_shock_taxonomy/processed"
CLUSTER_INVENTORY = Path("/home/phyrexian/cluster-lab-logs/windows-cluster-inventory.csv")
WINDOW_RE = re.compile(r"asia_gkg_window_(\d{8})_(\d{8})")


def load_liquid() -> list[str]:
    cfg = json.loads(UNIVERSE_CFG.read_text(encoding="utf-8"))
    for u in cfg.get("universes", []):
        if u.get("id") == "indonesia_liquid_core":
            return list(u["tickers"])
    return []


def window_keys_from_processed() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for panel in PROCESSED_ROOT.glob("*/daily_country_shock_panel.csv"):
        match = WINDOW_RE.match(panel.parent.name)
        if match:
            keys.add((match.group(1), match.group(2)))
    return keys


def window_keys_from_overlay() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    manifest = OVERLAY_ROOT / "manifest.json"
    if manifest.exists():
        for item in json.loads(manifest.read_text(encoding="utf-8")):
            if item.get("status") != "complete":
                continue
            match = WINDOW_RE.match(str(item.get("window", "")))
            if match:
                keys.add((match.group(1), match.group(2)))
    for summary in OVERLAY_ROOT.glob("*/summary.json"):
        match = WINDOW_RE.match(summary.parent.name)
        if match:
            keys.add((match.group(1), match.group(2)))
    return keys


def cluster_status() -> list[dict]:
    rows: list[dict] = []
    if not CLUSTER_INVENTORY.exists():
        return rows
    for line in CLUSTER_INVENTORY.read_text(encoding="utf-8").splitlines()[1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4:
            rows.append({"hostname": parts[0], "ip": parts[1], "status": parts[3]})
    return rows


def panel_holdout_coverage(df: pd.DataFrame, liquid: set[str]) -> dict:
    sub = df[df["yahoo_symbol"].isin(liquid)].copy()
    sub["year"] = sub["week_end"].dt.year
    by_year = sub.groupby("year").agg(weeks=("week_end", "nunique"), rows=("yahoo_symbol", "count"))
    cut = time_cutoff(sub["week_end"])
    holdout = sub[sub["week_end"] >= cut]
    return {
        "rows": int(len(sub)),
        "weeks_total": int(sub["week_end"].nunique()),
        "holdout_cutoff": str(cut.date()),
        "weeks_holdout": int(holdout["week_end"].nunique()),
        "tickers_any": int(sub["yahoo_symbol"].nunique()),
        "by_year": {int(k): {"weeks": int(v.weeks), "rows": int(v.rows)} for k, v in by_year.iterrows()},
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    liquid = set(load_liquid())

    proc_keys = window_keys_from_processed()
    ov_keys = window_keys_from_overlay()
    missing_overlay = sorted(proc_keys - ov_keys)

    ent = pd.read_parquet(ENTITY_PANEL)
    ent["week_end"] = pd.to_datetime(ent["week_end"])
    idn_ent = ent[ent["country_iso3"] == "IDN"]
    entity_cov = panel_holdout_coverage(idn_ent, liquid)

    b = pd.read_parquet(BROADCAST_PANEL, columns=["week_end", "country_iso3", "yahoo_symbol"])
    b["week_end"] = pd.to_datetime(b["week_end"])
    idn_b = b[(b["country_iso3"] == "IDN") & (b["yahoo_symbol"].isin(liquid))]
    broadcast_weeks = int(idn_b["week_end"].nunique())
    b_cut = time_cutoff(idn_b["week_end"])
    b_cut_s = b_cut.strftime("%Y%m%d")
    broadcast_holdout = int(idn_b[idn_b["week_end"] >= b_cut]["week_end"].nunique())
    missing_holdout = [k for k in missing_overlay if k[1] >= b_cut_s]
    manifest_path = OVERLAY_ROOT / "manifest.json"
    overlay_complete = 0
    if manifest_path.exists():
        overlay_complete = sum(
            1 for item in json.loads(manifest_path.read_text(encoding="utf-8")) if item.get("status") == "complete"
        )

    joined_cluster = sum(1 for row in cluster_status() if row.get("status") == "joined")

    manifest = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "plain_summary": (
            "IDX factor tests looked broken because the fused entity panel only had a thin slice of weeks in "
            "the OOS holdout window, while price/broadcast data is fine. Root cause: entity article overlays "
            f"were built for {len(ov_keys)} months locally but the published fused panel did not aggregate all of them."
        ),
        "layers": {
            "country_panels_months": len(proc_keys),
            "entity_overlay_months": len(ov_keys),
            "overlay_manifest_complete": overlay_complete,
            "missing_overlay_months": len(missing_overlay),
            "missing_overlay_holdout": len(missing_holdout),
            "holdout_cutoff": entity_cov["holdout_cutoff"],
            "broadcast_liquid_weeks": broadcast_weeks,
            "broadcast_liquid_weeks_holdout": broadcast_holdout,
            "entity_panel_liquid_weeks_holdout": entity_cov["weeks_holdout"],
        },
        "entity_panel_liquid": entity_cov,
        "missing_overlay_keys_sample": [f"{a}_{b}" for a, b in missing_holdout[:12]],
        "cluster": {"inventory_hosts": cluster_status(), "joined_count": joined_cluster},
        "next_steps": [
            "Aggregate all complete overlays into entity weekly panel (--overlay-aggregate-only).",
            "Rebuild fused IDX entity-market panel (phase=fused).",
            f"Build entity overlays for {len(missing_overlay)} missing months (priority: {len(missing_holdout)} in holdout).",
            "Re-run scripts/run_idn_single_factor_screen.py after rebuild.",
        ],
    }

    latest = OUT / "latest.json"
    latest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# IDX entity coverage audit",
        f"- built: {manifest['built_at_utc']}",
        "",
        "## What went wrong (plain English)",
        "",
        manifest["plain_summary"],
        "",
        "Two different data layers were mixed up:",
        "",
        f"| Layer | What it is | Liquid IDX weeks (OOS holdout since {entity_cov['holdout_cutoff']}) |",
        "|-------|------------|---------------------------------------------------------------------|",
        f"| **Broadcast panel** | Country news copied to every ticker + yfinance returns | **{broadcast_holdout}** weeks |",
        f"| **Entity panel** | Firm-specific GDELT mentions matched to tickers | **{entity_cov['weeks_holdout']}** weeks |",
        "",
        "Factor tests on **firm attention** (`entity_mention_rows`) need the entity panel. ",
        "With only ~12 OOS weeks, ticker pick/avoid lists were empty or unstable.",
        "",
        "## Pipeline status",
        f"- Country news months built: **{len(proc_keys)}**",
        f"- Entity overlay months on disk: **{len(ov_keys)}** (manifest complete: {overlay_complete})",
        f"- Missing overlays (have country panel, no entity scan): **{len(missing_overlay)}**",
        f"- Missing overlays in holdout window: **{len(missing_holdout)}**",
        f"- Cluster nodes joined: **{joined_cluster}**",
        "",
        "## Entity panel rows by year (liquid 50)",
    ]
    for year, block in sorted(entity_cov["by_year"].items()):
        lines.append(f"- {year}: {block['weeks']} weeks, {block['rows']} rows")
    lines += ["", "## Next steps"] + [f"- {s}" for s in manifest["next_steps"]]

    (OUT / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(manifest["layers"], indent=2))
    print(f"wrote {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
