#!/usr/bin/env python3
"""Build unified Skynet + Etherscan stablecoin dataset."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from stablecoin_skynet.unified_dataset import (
    DEFAULT_COMMUNITY_DIR,
    DEFAULT_SCRAPES_ROOT,
    DEFAULT_SKYNET_HARVEST,
    build_unified_dataset,
    write_unified_csv,
)

REPO = Path(__file__).resolve().parents[1]


def _copy_community_bundle(out_dir: Path, community_dir: Path) -> list[str]:
    """Copy long-format community tables beside the unified panel."""
    copied: list[str] = []
    bundle = out_dir / "community"
    bundle.mkdir(parents=True, exist_ok=True)
    for rel in [
        "community_attention_panel.csv",
        "accounts.csv",
        "follower_growth_panel.csv",
        "holder_growth_panel.csv",
        "proxy_manifest.json",
        "PROFESSOR_HANDOFF.md",
        "coingecko/coingecko_community_snapshot.csv",
    ]:
        src = community_dir / rel
        if not src.is_file():
            continue
        dest = bundle / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(rel)
    return copied


def write_research_scope(out_dir: Path, manifest: dict) -> None:
    counts = manifest.get("counts") or {}
    text = f"""# Stablecoin research scope (professor-facing)

You asked about **stablecoins** with data from **CertiK Skynet** and **Etherscan**. We merged them into one panel and added **community attention proxies** because X/Twitter does not expose historical follower APIs.

## What you can study without guessing URLs

### 1. Security vs market footprint (cross-section)
**File:** `stablecoin_unified_panel.csv` ({counts.get('unified_rows', 0)} rows)

| Question | Columns |
|----------|---------|
| Which coins score high on Skynet but low on-chain adoption? | `skynet_score`, `etherscan_holders`, `etherscan_onchain_mcap_usd` |
| Governance / contract risk vs liquidity | `token_open_source`, `token_mint_function`, `exchange_volume_24h` |
| Official web presence vs CertiK website scan | `skynet_website`, `website_scan_deducted_score` |

**Start here:** filter `in_skynet_leaderboard=True`, sort by `coverage_score` descending.

### 2. Community growth & attention (proxies — not raw Twitter API)
**Files:** `community/community_attention_panel.csv` (long, ~20k rows), plus summary columns on unified panel

| Proxy | Window | What it measures |
|-------|--------|------------------|
| Google Trends weekly index | ~5 years | Public search interest in coin name |
| Reddit submissions / month (PullPush) | Historical sample | Discourse volume |
| Skynet Twitter follower series | ~4–6 weeks daily | Short-window official-account growth |
| On-chain holder series (Skynet) | ~weeks | Adoption proxy |
| CoinGecko snapshot | Point-in-time | Twitter/Reddit/Telegram counts today |

**Framing for papers:** Terra/UST and PLOS ONE stablecoin social work use **attention proxies**, not lifetime Twitter history.

**Unified panel columns:** `google_trends_peak`, `reddit_submissions_peak_month`, `community_twitter_growth_pct`, `community_holder_growth_pct`.

### 3. USDT flow history (Ethereum on-chain, not Etherscan scrape)
See professor pack `usdt_daily_flows_bigquery.csv` — daily transfer aggregates 2017→present.

## Coverage today

| Layer | Status |
|-------|--------|
| Skynet leaderboard | {counts.get('skynet_projects', 0)} projects |
| Etherscan matches | {counts.get('both_sources', 0)} linked (+ backfill running for ~50 more) |
| Community proxies | {counts.get('with_community_proxy', 0)} slugs on unified panel |
| Google Trends | {counts.get('with_google_trends', 0)} coins |
| Reddit proxy | {counts.get('with_reddit_proxy', 0)} coins |
| Twitter growth window | {counts.get('with_twitter_growth_window', 0)} coins |

## Suggested first analyses

1. **Scatter:** `skynet_score` vs `log(etherscan_holders)` for linked coins — security rating vs adoption.
2. **Attention ranking:** sort by `google_trends_peak` × `reddit_submissions_peak_month`.
3. **Growth window:** coins with `community_twitter_growth_pct` > 0 AND rising `holder_count` in `community/follower_growth_panel.csv`.
4. **Case study:** USDT row — full Skynet + Etherscan + BigQuery daily flows.

## Honest limits

- Skynet scores missing for smaller coins (~62/71) — governance/exchange fields still present.
- Etherscan catalog was a 25-token pilot; targeted backfill adds Skynet-known addresses.
- Twitter series is Skynet monitoring window only, not since account creation.
- CoinGecko community snapshot partial ({counts.get('community_slugs', 0)} registry; snapshot still filling).
"""
    (out_dir / "RESEARCH_SCOPE.md").write_text(text, encoding="utf-8")


def write_readme(out_dir: Path, manifest: dict) -> None:
    counts = manifest.get("counts") or {}
    text = f"""# Unified stablecoin dataset (Skynet + Etherscan)

Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

## What this is

One row per stablecoin **entity**, merging:

- **CertiK Skynet** stablecoin leaderboard ({counts.get("skynet_projects", 0)} projects) — security scores, governance, exchange, pulses
- **Etherscan** stablecoin listing scrapes ({counts.get("etherscan_tokens_indexed", 0)} token addresses) — on-chain market cap, holders, decimals

Joined primarily on **Ethereum contract address** (`primary_ethereum_address`).

## Files

| File | Description |
|------|-------------|
| `stablecoin_unified_panel.csv` | Main panel ({counts.get("unified_rows", 0)} rows) |
| `manifest.json` | Join stats and lineage |
| `JOIN_REPORT.md` | Human-readable coverage summary |

## Coverage

| Segment | Count |
|---------|------:|
| Both Skynet + Etherscan | {counts.get("both_sources", 0)} |
| Skynet only (no Etherscan match yet) | {counts.get("skynet_only", 0)} |
| Etherscan only (not on Skynet leaderboard) | {counts.get("etherscan_only", 0)} |
| Rows with Skynet score | {counts.get("with_skynet_score", 0)} |
| Rows with Etherscan holders | {counts.get("with_etherscan_holders", 0)} |

## Regenerate

```bash
cd Sharpe-Renaissance
PYTHONPATH=. .venv/bin/python scripts/build_stablecoin_unified_dataset.py
```
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def write_join_report(out_dir: Path, manifest: dict, rows: list[dict]) -> None:
    counts = manifest.get("counts") or {}
    both = [r for r in rows if r.get("in_skynet_leaderboard") and r.get("in_etherscan_stablecoin_list")]
    skynet_only = [r for r in rows if r.get("in_skynet_leaderboard") and not r.get("in_etherscan_stablecoin_list")]
    eth_only = [r for r in rows if not r.get("in_skynet_leaderboard")]

    lines = [
        "# Stablecoin join report",
        "",
        f"- Skynet harvest: `{manifest.get('skynet_harvest_dir')}`",
        f"- Etherscan scrapes: `{manifest.get('scrapes_root')}`",
        "",
        "## Summary",
        "",
        f"- **{counts.get('both_sources', 0)}** entities linked across both sources",
        f"- **{counts.get('skynet_only', 0)}** Skynet leaderboard coins without an Etherscan scrape match",
        f"- **{counts.get('etherscan_only', 0)}** Etherscan stablecoin tokens not on the Skynet leaderboard",
        "",
        "## Top linked entities (by coverage score)",
        "",
        "| Entity | Score | Skynet | Etherscan mcap | Holders |",
        "|--------|------:|-------:|---------------:|--------:|",
    ]
    for row in both[:15]:
        lines.append(
            f"| {row.get('canonical_name', '')[:40]} | {row.get('coverage_score', 0)} | "
            f"{row.get('skynet_score') or '—'} | "
            f"{row.get('etherscan_onchain_mcap_usd') or '—'} | "
            f"{row.get('etherscan_holders') or '—'} |"
        )

    if skynet_only:
        lines.extend(["", "## Skynet-only (need Etherscan address match or catalog expansion)", ""])
        for row in skynet_only[:20]:
            lines.append(
                f"- `{row.get('skynet_slug')}` — eth: `{row.get('primary_ethereum_address') or 'none'}`"
            )

    if eth_only:
        lines.extend(["", "## Etherscan-only (not on Skynet stablecoin leaderboard)", ""])
        for row in eth_only[:15]:
            lines.append(
                f"- `{row.get('etherscan_symbol')}` `{row.get('primary_ethereum_address')}` "
                f"(rank {row.get('etherscan_rank') or '?'})"
            )

    (out_dir / "JOIN_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skynet-harvest", type=Path, default=DEFAULT_SKYNET_HARVEST)
    parser.add_argument("--scrapes-root", type=Path, default=DEFAULT_SCRAPES_ROOT)
    parser.add_argument("--community-dir", type=Path, default=DEFAULT_COMMUNITY_DIR)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Default: data/exports/stablecoin_unified_YYYYMMDD",
    )
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = args.out_dir or (REPO / f"data/exports/stablecoin_unified_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, manifest = build_unified_dataset(
        skynet_harvest_dir=args.skynet_harvest,
        scrapes_root=args.scrapes_root,
        community_dir=args.community_dir,
    )
    manifest["output_dir"] = str(out_dir)
    row_count = write_unified_csv(out_dir / "stablecoin_unified_panel.csv", rows)
    manifest["counts"]["unified_rows"] = row_count
    manifest["community_files_copied"] = _copy_community_bundle(out_dir, args.community_dir)

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_readme(out_dir, manifest)
    write_join_report(out_dir, manifest, rows)
    write_research_scope(out_dir, manifest)

    print(json.dumps(manifest, indent=2))
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
