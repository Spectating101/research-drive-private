#!/usr/bin/env python3
"""Export Skynet + Etherscan + USDT panels to professor-ready CSVs."""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stablecoin_skynet.unified_dataset import (
    DEFAULT_SCRAPES_ROOT,
    DEFAULT_SKYNET_HARVEST,
    build_unified_dataset,
    parse_skynet_project,
    write_unified_csv,
)

REPO = Path(__file__).resolve().parents[1]
SKYNET_HARVEST = DEFAULT_SKYNET_HARVEST
SCRAPES_ROOT = DEFAULT_SCRAPES_ROOT
USDT_FLOWS = REPO / "data/usdt_catalogue/bigquery_history/daily_usdt_flows_all.csv"


def _skynet_row(path: Path) -> dict[str, Any]:
    row = parse_skynet_project(path)
    return {
        "slug": row["skynet_slug"],
        "name": row["skynet_name"],
        "rank": row.get("skynet_rank"),
        "skynet_score": row.get("skynet_score"),
        "score_code_security": row.get("score_code_security"),
        "score_governance": row.get("score_governance"),
        "score_community": row.get("score_community"),
        "score_market": row.get("score_market"),
        "score_fundamental": row.get("score_fundamental"),
        "score_operation": row.get("score_operation"),
        "ai_summary": row.get("skynet_ai_summary"),
        "price_usd": row.get("skynet_price_usd"),
        "market_cap_usd": row.get("skynet_market_cap_usd"),
        "twitter_followers": row.get("skynet_twitter_followers"),
        "website": row.get("skynet_website"),
        "ethereum_address": row.get("primary_ethereum_address"),
        "governance_items": row.get("governance_items"),
        "token_open_source": row.get("token_open_source"),
        "token_mint_function": row.get("token_mint_function"),
        "token_honeypot": row.get("token_honeypot"),
        "token_age_days": row.get("token_age_days"),
        "exchange_pairs": row.get("exchange_pairs"),
        "exchange_count": row.get("exchange_count"),
        "exchange_volume_24h": row.get("exchange_volume_24h"),
        "website_scan_deducted_score": row.get("website_scan_deducted_score"),
        "pulse_items": row.get("pulse_items"),
        "price_bars_1y": row.get("price_bars_1y"),
        "endpoints_with_data": row.get("skynet_endpoints_with_data"),
        "harvested_at": row.get("skynet_harvested_at"),
        "skynet_url": row.get("skynet_url"),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return 0
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def export_skynet(out_dir: Path) -> int:
    rows = [_skynet_row(p) for p in sorted(SKYNET_HARVEST.glob("*.json"))]
    rows.sort(key=lambda r: (-(float(r["skynet_score"]) if r.get("skynet_score") is not None else -1), r["slug"]))
    return _write_csv(out_dir / "skynet_stablecoin_panel.csv", rows)


def _read_tokens_panel(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def export_etherscan_catalog(out_dir: Path) -> tuple[int, int, list[str]]:
    preferred_panels = [
        SCRAPES_ROOT / "d1cc38729356/tokens_panel.csv",
        SCRAPES_ROOT / "9e3b4b53ebbd/tokens_panel.csv",
    ]
    catalog_rows: list[dict[str, str]] = []
    seen_addr: set[str] = set()
    for panel_path in preferred_panels:
        if not panel_path.exists():
            continue
        for row in _read_tokens_panel(panel_path):
            addr = str(row.get("address") or "").lower().strip()
            if not addr or addr in seen_addr:
                continue
            if "ONCHAIN MARKET CAP" in str(row.get("price") or ""):
                continue
            seen_addr.add(addr)
            row = dict(row)
            row["source_scrape_job"] = panel_path.parent.name
            catalog_rows.append(row)

    detail_rows: list[dict[str, Any]] = []
    seen_detail: set[str] = set()
    for token_json in sorted(SCRAPES_ROOT.glob("*/tokens/*.json")):
        try:
            data = json.loads(token_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        addr = str(data.get("address") or token_json.stem).lower()
        if addr in seen_detail:
            continue
        listing = data.get("listing") or {}
        detail = data.get("detail") or {}
        links = detail.get("links") or {}
        seen_detail.add(addr)
        detail_rows.append(
            {
                "address": addr,
                "symbol": listing.get("symbol"),
                "name": listing.get("name"),
                "rank": listing.get("rank"),
                "price": listing.get("price"),
                "change_pct": listing.get("change_pct"),
                "volume_24h": listing.get("volume_24h"),
                "onchain_market_cap": listing.get("onchain_market_cap"),
                "circulating_market_cap": listing.get("circulating_market_cap"),
                "holders": listing.get("holders"),
                "decimals": detail.get("decimals"),
                "website": links.get("website"),
                "coingecko": links.get("coingecko"),
                "twitter": links.get("twitter"),
                "telegram": links.get("telegram"),
                "etherscan_url": listing.get("href") or data.get("source"),
                "harvested_at": data.get("harvested_at"),
                "source_scrape_job": token_json.parent.parent.name,
            }
        )

    if not catalog_rows and detail_rows:
        catalog_rows = [
            {
                "address": r["address"],
                "symbol": r.get("symbol"),
                "name": r.get("name"),
                "price": r.get("price"),
                "onchain_market_cap": r.get("onchain_market_cap"),
                "circulating_market_cap": r.get("circulating_market_cap"),
                "holders": r.get("holders"),
                "website": r.get("website"),
                "coingecko": r.get("coingecko"),
                "source_scrape_job": r.get("source_scrape_job"),
            }
            for r in detail_rows
        ]

    detail_by = {r["address"]: r for r in detail_rows}

    def _rank_key(row: dict[str, Any]) -> int:
        rank = row.get("rank")
        if rank is None and row.get("address"):
            rank = (detail_by.get(str(row["address"]).lower()) or {}).get("rank")
        return int("".join(c for c in str(rank or "999") if c.isdigit()) or "999")

    catalog_rows.sort(key=_rank_key)
    detail_rows.sort(key=_rank_key)

    catalog_n = _write_csv(out_dir / "etherscan_stablecoin_catalog.csv", catalog_rows)
    detail_n = _write_csv(out_dir / "etherscan_token_profiles.csv", detail_rows)
    jobs = sorted({str(r.get("source_scrape_job") or "") for r in detail_rows if r.get("source_scrape_job")})
    return catalog_n, detail_n, jobs


def export_usdt_flows(out_dir: Path) -> int:
    dest = out_dir / "usdt_daily_flows_bigquery.csv"
    if not USDT_FLOWS.exists():
        dest.write_text("", encoding="utf-8")
        return 0
    shutil.copy2(USDT_FLOWS, dest)
    with USDT_FLOWS.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def write_readme(out_dir: Path, counts: dict[str, int], etherscan_jobs: list[str]) -> None:
    text = f"""# Professor stablecoin data pack

Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

## Files

| File | Rows | Description |
|------|------|-------------|
| `skynet_stablecoin_panel.csv` | {counts.get("skynet", 0)} | CertiK Skynet stablecoin leaderboard (71 projects). Scores populated for top-tier coins; all rows include exchange/governance/website fields where harvested. |
| `etherscan_stablecoin_catalog.csv` | {counts.get("etherscan_catalog", 0)} | Merged Etherscan stablecoin listing scrapes (pilot catalog runs, deduped by token address). |
| `etherscan_token_profiles.csv` | {counts.get("etherscan_profiles", 0)} | Per-token Etherscan detail pages (links, decimals, holders). |
| `usdt_daily_flows_bigquery.csv` | {counts.get("usdt_flows", 0)} | Daily USDT transfer aggregates from BigQuery public dataset (historical). |
| `stablecoin_unified_panel.csv` | {counts.get("unified", 0)} | **Merged Skynet + Etherscan** panel (address-joined, coverage score). |

## Sources

- Skynet harvest: `stablecoin_skynet/data/harvest_20260622T132438Z/` (2026-06-22, 71/71 stablecoin leaderboard)
- Etherscan scrapes: `{", ".join(etherscan_jobs) or "none"}`
- USDT flows: `data/usdt_catalogue/bigquery_history/daily_usdt_flows_all.csv`

## Caveats for demo

- Etherscan catalog is a **pilot** (25 tokens per run), not the full 64-page sweep.
- Skynet `skynet_score` is only present for coins with full `info`/`summary` API payloads (~9); other rows still have governance/exchange/website fields.
- Full Etherscan sweep task `etherscan_stablecoin_catalog_sweep` has not been run yet.

## Regenerate

```bash
cd Sharpe-Renaissance
PYTHONPATH=. .venv/bin/python scripts/export_professor_stablecoin_pack.py
```
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = REPO / f"data/exports/professor_stablecoin_pack_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    skynet_n = export_skynet(out_dir)
    catalog_n, profile_n, etherscan_jobs = export_etherscan_catalog(out_dir)
    usdt_n = export_usdt_flows(out_dir)
    unified_rows, unified_manifest = build_unified_dataset(
        skynet_harvest_dir=SKYNET_HARVEST,
        scrapes_root=SCRAPES_ROOT,
    )
    unified_n = write_unified_csv(out_dir / "stablecoin_unified_panel.csv", unified_rows)
    (out_dir / "stablecoin_unified_manifest.json").write_text(
        json.dumps(unified_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    counts = {
        "skynet": skynet_n,
        "etherscan_catalog": catalog_n,
        "etherscan_profiles": profile_n,
        "usdt_flows": usdt_n,
        "unified": unified_n,
        **(unified_manifest.get("counts") or {}),
    }
    write_readme(out_dir, counts, etherscan_jobs)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(out_dir),
        "counts": counts,
        "etherscan_source_jobs": etherscan_jobs,
        "unified_join": unified_manifest.get("join_methods"),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2))
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
