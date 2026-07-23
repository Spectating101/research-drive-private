#!/usr/bin/env python3
"""Build ticker-level news-market research panels (Phase 1 + Phase 2).

Phase 1 (broadcast):
  country-week fused news shocks -> each liquid ticker in that country + ticker returns

Phase 2 (entity):
  GDELT article organizations -> entity master resolve -> ticker-day/week mention shocks

Phase 2 join (fused):
  entity-resolved ticker shocks + ticker returns (+ optional country broadcast features)
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from ticker_research_panel_lib import (  # noqa: E402
    REPO,
    aggregate_entity_hits_to_daily,
    build_entity_alias_index,
    build_entity_broadcast_residual,
    build_entity_long_panel,
    build_weekly_entity_news,
    build_weekly_ticker_returns,
    canonical_article_source_dirs,
    canonical_article_url,
    latest_run,
    liquidity_bucket,
    load_country_week_news,
    load_entity_universe,
    match_entities_in_text,
    now_run_id,
    parse_gkg_organizations,
    shock_hint_columns,
    write_frame,
    _article_source_for_window,
)

DEFAULT_FUSED_PANEL = (
    REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/cross_asset_fused_primary_panel.parquet"
)
DEFAULT_ENTITY_ROOT = REPO / "data_lake/entity_mapping/asia"
DEFAULT_MARKET_ROOT = REPO / "data_lake/markets/yfinance_asia"
DEFAULT_PROCESSED_ROOT = REPO / "data_lake/news_shock_taxonomy/processed"
DEFAULT_NORMALIZED_ROOT = REPO / "data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk"
DEFAULT_ENTITY_OVERLAY_ROOT = REPO / "data_lake/news_shock_taxonomy/derived/gdelt_entity_ticker_overlay"
DEFAULT_OUT_ROOT = REPO / "data_lake/research_panels/ticker_news_market"

SCORED_COLUMNS = [
    "date",
    "country_iso3",
    "organizations",
    "themes",
    "document_identifier",
    "shock_hints",
    "tone_avg",
    "market_relevance_score",
    "market_relevance_bucket",
    "collection_decision",
]
NORMALIZED_COLUMNS = [
    "date",
    "country_iso3",
    "organizations",
    "themes",
    "document_identifier",
    "shock_hints",
    "tone_avg",
]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--phase",
        choices=["broadcast", "entity", "fused", "tier3_extras", "all"],
        default="all",
        help="broadcast=phase1, entity=phase2, fused=entity-market, tier3_extras=long+residual, all=full",
    )
    ap.add_argument("--fused-panel", type=Path, default=DEFAULT_FUSED_PANEL)
    ap.add_argument("--entity-root", type=Path, default=DEFAULT_ENTITY_ROOT)
    ap.add_argument("--entity-run", default="latest")
    ap.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    ap.add_argument("--market-run", default="latest")
    ap.add_argument("--processed-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    ap.add_argument("--normalized-root", type=Path, default=DEFAULT_NORMALIZED_ROOT)
    ap.add_argument("--entity-overlay-root", type=Path, default=DEFAULT_ENTITY_OVERLAY_ROOT)
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--min-price-rows", type=int, default=200, help="Broadcast phase liquidity gate.")
    ap.add_argument("--min-price-rows-entity", type=int, default=60, help="Entity phase liquidity gate (lower for AUS/PHL/IND/VNM).")
    ap.add_argument("--alias-supplement", type=Path, default=REPO / "config/ticker_entity_aliases_v2.json")
    ap.add_argument("--min-market-relevance", type=float, default=0.0, help="Drop article rows below this score when present.")
    ap.add_argument("--dedupe-urls", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--countries", action="append", default=[])
    ap.add_argument("--max-windows", type=int, default=0, help="Limit entity overlay windows (0=all available).")
    ap.add_argument(
        "--force-entity-overlay",
        action="store_true",
        help="Rebuild per-window entity overlay even if summary.json exists.",
    )
    ap.add_argument(
        "--overlay-aggregate-only",
        action="store_true",
        help="Skip article scans; aggregate all complete overlays from manifest.json into daily/weekly entity panels.",
    )
    ap.add_argument(
        "--overlay-window",
        default="",
        help="Process only this overlay window name (substring match on window dir).",
    )
    return ap.parse_args()


def run_broadcast_phase(
    args: argparse.Namespace,
    out_dir: Path,
    entities: pd.DataFrame,
    market_run_dir: Path,
) -> dict[str, object]:
    country_news = load_country_week_news(args.fused_panel)
    if args.countries:
        country_news = country_news[country_news["country_iso3"].isin(args.countries)]
        entities = entities[entities["market_country"].isin(args.countries)]

    tickers = set(entities["yahoo_symbol"])
    prices = load_ticker_daily_prices(market_run_dir, tickers)
    weekly_returns = build_weekly_ticker_returns(prices, ffill_holidays=True)
    if weekly_returns.empty:
        raise ValueError("no ticker weekly returns built")

    ticker_meta = entities.rename(columns={"market_country": "country_iso3"})
    weekly_returns = weekly_returns.merge(
        ticker_meta[
            [
                "yahoo_symbol",
                "country_iso3",
                "entity_id",
                "exchange",
                "name",
                "instrument_type",
                "confidence",
                "row_count_daily",
            ]
        ],
        on="yahoo_symbol",
        how="left",
    )
    panel = weekly_returns.merge(country_news, on=["country_iso3", "week_end"], how="left")
    panel["join_mode"] = "country_broadcast"

    registry = ticker_meta.drop_duplicates(subset=["yahoo_symbol"]).sort_values(["country_iso3", "yahoo_symbol"])
    outputs = {
        "ticker_registry": write_frame(registry, out_dir / "ticker_registry"),
        "ticker_week_returns_panel": write_frame(weekly_returns, out_dir / "ticker_week_returns_panel"),
        "ticker_week_country_broadcast_panel": write_frame(panel, out_dir / "ticker_week_country_broadcast_panel"),
    }
    summary = {
        "phase": "broadcast",
        "tickers": int(registry["yahoo_symbol"].nunique()),
        "countries": sorted(registry["country_iso3"].dropna().unique().tolist()),
        "panel_rows": int(len(panel)),
        "week_min": str(panel["week_end"].min().date()) if not panel.empty else "",
        "week_max": str(panel["week_end"].max().date()) if not panel.empty else "",
        "outputs": outputs,
    }
    return summary


def load_ticker_daily_prices(market_run_dir: Path, tickers: set[str]) -> pd.DataFrame:
    from ticker_research_panel_lib import load_ticker_daily_prices as _load

    return _load(market_run_dir, tickers)


def process_entity_window(
    window_dir: Path,
    source_file: Path,
    source_kind: str,
    alias_index,
    out_root: Path,
    entities: pd.DataFrame,
    force: bool = False,
    min_market_relevance: float = 0.0,
    dedupe_urls: bool = True,
) -> dict[str, object]:
    out_dir = out_root / window_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    daily_path = out_dir / "daily_ticker_entity_shock_panel.csv"
    evidence_path = out_dir / "entity_event_evidence.csv.gz"
    summary_path = out_dir / "summary.json"
    if summary_path.exists() and not force:
        prior = json.loads(summary_path.read_text(encoding="utf-8"))
        if (
            prior.get("status") == "complete"
            and daily_path.exists()
            and evidence_path.exists()
        ):
            return prior
    if force:
        for path in (daily_path, evidence_path, summary_path):
            path.unlink(missing_ok=True)

    allowed_symbols = set(entities["yahoo_symbol"])
    hint_cols = shock_hint_columns()
    hit_rows: list[dict[str, object]] = []
    evidence_fields = [
        "date",
        "country_iso3",
        "yahoo_symbol",
        "entity_id",
        "matched_alias",
        "market_relevance_score",
        "tone_avg",
        "shock_hints",
        "document_identifier",
    ]
    evidence_partial = evidence_path.with_suffix(evidence_path.suffix + ".partial")
    rows_scanned = matched_rows = 0
    seen_urls: set[tuple[str, str, str]] = set()

    try:
        with gzip.open(source_file, "rt", encoding="utf-8", errors="replace", newline="") as src, gzip.open(
            evidence_partial, "wt", encoding="utf-8", newline=""
        ) as ev_out:
            reader = csv.DictReader(src)
            writer = csv.DictWriter(ev_out, fieldnames=evidence_fields + ["match_tier"])
            writer.writeheader()
            for row in reader:
                rows_scanned += 1
                country = str(row.get("country_iso3") or "").strip().upper()
                if not country:
                    continue
                relevance = pd.to_numeric(row.get("market_relevance_score"), errors="coerce")
                if min_market_relevance > 0 and pd.notna(relevance) and float(relevance) < min_market_relevance:
                    continue
                text = " ".join(
                    [
                        parse_gkg_organizations(str(row.get("organizations") or "")),
                        str(row.get("themes") or ""),
                        str(row.get("document_identifier") or ""),
                    ]
                )
                hits = match_entities_in_text(text, country, alias_index, country_only=True)
                if not hits:
                    continue
                hints = [h for h in str(row.get("shock_hints") or "").split("|") if h]
                hint_counter = Counter(hints)
                tone = pd.to_numeric(row.get("tone_avg"), errors="coerce")
                article_url = canonical_article_url(str(row.get("document_identifier") or ""))
                for hit in hits:
                    if hit.yahoo_symbol not in allowed_symbols:
                        continue
                    if dedupe_urls and article_url:
                        dedupe_key = (str(row.get("date", "")), article_url, hit.yahoo_symbol)
                        if dedupe_key in seen_urls:
                            continue
                        seen_urls.add(dedupe_key)
                    matched_rows += 1
                    payload = {
                        "date": row.get("date", ""),
                        "country_iso3": country,
                        "yahoo_symbol": hit.yahoo_symbol,
                        "entity_id": hit.entity_id,
                        "market_country": hit.market_country,
                        "matched_alias": hit.alias,
                        "match_tier": hit.match_tier,
                        "canonical_url": article_url,
                        "market_relevance_score": relevance,
                        "tone_avg": tone,
                    }
                    for hint in hint_cols:
                        payload[f"{hint}_rows"] = int(hint_counter.get(hint, 0))
                    hit_rows.append(payload)
                    writer.writerow(
                        {
                            "date": payload["date"],
                            "country_iso3": country,
                            "yahoo_symbol": hit.yahoo_symbol,
                            "entity_id": hit.entity_id,
                            "matched_alias": hit.alias,
                            "market_relevance_score": relevance if pd.notna(relevance) else "",
                            "tone_avg": tone if pd.notna(tone) else "",
                            "shock_hints": "|".join(hints),
                            "document_identifier": row.get("document_identifier", ""),
                            "match_tier": hit.match_tier,
                        }
                    )
    except (EOFError, OSError) as exc:
        if evidence_partial.exists():
            evidence_partial.unlink(missing_ok=True)
        return {
            "window": window_dir.name,
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "corrupt_input",
            "source_kind": source_kind,
            "input": str(source_file),
            "error": str(exc),
            "rows_scanned": rows_scanned,
            "entity_mention_rows": matched_rows,
        }

    evidence_partial.replace(evidence_path)
    daily = aggregate_entity_hits_to_daily(hit_rows)
    daily.to_csv(daily_path, index=False)
    summary = {
        "window": window_dir.name,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "complete",
        "source_kind": source_kind,
        "input": str(source_file),
        "rows_scanned": rows_scanned,
        "entity_mention_rows": matched_rows,
        "unique_ticker_days": int(len(daily)),
        "unique_tickers": int(daily["yahoo_symbol"].nunique()) if not daily.empty else 0,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def aggregate_entity_daily_from_overlay_manifest(overlay_root: Path) -> tuple[pd.DataFrame, list[dict]]:
    """Load daily entity shocks from all complete per-window overlays."""
    manifest_path = overlay_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing overlay manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    daily_frames: list[pd.DataFrame] = []
    complete: list[dict] = []
    for item in manifest:
        if item.get("status") != "complete":
            continue
        path = overlay_root / str(item["window"]) / "daily_ticker_entity_shock_panel.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df.insert(0, "entity_window", item["window"])
        daily_frames.append(df)
        complete.append(item)
    daily = pd.concat(daily_frames, ignore_index=True) if daily_frames else pd.DataFrame()
    return daily, complete


def run_entity_phase(
    args: argparse.Namespace,
    out_dir: Path,
    entities: pd.DataFrame,
) -> dict[str, object]:
    overlay_root = args.entity_overlay_root
    overlay_root.mkdir(parents=True, exist_ok=True)

    if bool(args.overlay_aggregate_only):
        daily, manifest = aggregate_entity_daily_from_overlay_manifest(overlay_root)
        weekly = build_weekly_entity_news(daily) if not daily.empty else pd.DataFrame()
        outputs = {
            "daily_ticker_entity_shock_panel": write_frame(daily, out_dir / "daily_ticker_entity_shock_panel"),
            "ticker_week_entity_news_panel": write_frame(weekly, out_dir / "ticker_week_entity_news_panel"),
        }
        return {
            "phase": "entity",
            "mode": "overlay_aggregate_only",
            "article_windows": len(manifest),
            "completed_windows": len(manifest),
            "daily_rows": int(len(daily)),
            "weekly_rows": int(len(weekly)),
            "outputs": outputs,
        }

    alias_index = build_entity_alias_index(entities, supplement_path=args.alias_supplement)
    sources = canonical_article_source_dirs(args.processed_root, args.normalized_root)
    if args.overlay_window:
        needle = str(args.overlay_window)
        filtered = [s for s in sources if needle in s[0].name or needle in str(s[1])]
        if not filtered:
            # Fallback: resolve directly from processed country-panel keys.
            import re

            window_re = re.compile(r"asia_gkg_window_(\d{8})_(\d{8})")
            for panel in args.processed_root.glob("*/daily_country_shock_panel.csv"):
                match = window_re.match(panel.parent.name)
                if not match or f"{match.group(1)}_{match.group(2)}" not in needle:
                    continue
                resolved = _article_source_for_window(args.processed_root, args.normalized_root, (match.group(1), match.group(2)))
                if resolved is not None:
                    filtered.append(resolved)
                    break
        sources = filtered
        if not sources:
            raise FileNotFoundError(f"no article source for overlay-window={needle}")
    if args.max_windows:
        sources = sources[: args.max_windows]
    if not sources:
        raise FileNotFoundError("no article-level scored/normalized windows available for entity overlay")

    overlay_root = args.entity_overlay_root
    overlay_root.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, (window_dir, source_file, source_kind) in enumerate(sources, 1):
        result = process_entity_window(
            window_dir,
            source_file,
            source_kind,
            alias_index,
            overlay_root,
            entities,
            force=args.force_entity_overlay,
            min_market_relevance=args.min_market_relevance,
            dedupe_urls=args.dedupe_urls,
        )
        manifest.append(result)
        (overlay_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"progress": f"{index}/{len(sources)}", **result}, separators=(",", ":")), flush=True)

    daily_frames = []
    for item in manifest:
        if item.get("status") not in {"complete"}:
            continue
        path = overlay_root / str(item["window"]) / "daily_ticker_entity_shock_panel.csv"
        if path.exists():
            df = pd.read_csv(path)
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df.insert(0, "entity_window", item["window"])
            daily_frames.append(df)
    daily = pd.concat(daily_frames, ignore_index=True) if daily_frames else pd.DataFrame()
    weekly = build_weekly_entity_news(daily) if not daily.empty else pd.DataFrame()

    outputs = {
        "daily_ticker_entity_shock_panel": write_frame(daily, out_dir / "daily_ticker_entity_shock_panel"),
        "ticker_week_entity_news_panel": write_frame(weekly, out_dir / "ticker_week_entity_news_panel"),
    }
    return {
        "phase": "entity",
        "alias_count": len(alias_index),
        "article_windows": len(sources),
        "completed_windows": sum(1 for item in manifest if item.get("status") == "complete"),
        "daily_rows": int(len(daily)),
        "weekly_rows": int(len(weekly)),
        "outputs": outputs,
    }


def run_fused_phase(
    args: argparse.Namespace,
    out_dir: Path,
    entities: pd.DataFrame,
    market_run_dir: Path,
) -> dict[str, object]:
    entity_weekly_path = out_dir / "ticker_week_entity_news_panel.parquet"
    if not entity_weekly_path.exists():
        entity_csv = out_dir / "ticker_week_entity_news_panel.csv"
        if not entity_csv.exists():
            raise FileNotFoundError("run entity phase first or provide ticker_week_entity_news_panel")
        entity_weekly = pd.read_csv(entity_csv)
    else:
        entity_weekly = pd.read_parquet(entity_weekly_path)
    entity_weekly["week_end"] = pd.to_datetime(entity_weekly["week_end"], errors="coerce")

    tickers = set(entities["yahoo_symbol"])
    prices = load_ticker_daily_prices(market_run_dir, tickers)
    weekly_returns = build_weekly_ticker_returns(prices, ffill_holidays=True)
    ticker_meta = entities.rename(columns={"market_country": "country_iso3"})

    panel = weekly_returns.merge(entity_weekly, on=["yahoo_symbol", "week_end"], how="inner", suffixes=("", "_entity"))
    if "market_country" in panel.columns:
        panel = panel.rename(columns={"market_country": "country_iso3"})
    panel = panel.merge(
        ticker_meta[
            ["yahoo_symbol", "country_iso3", "entity_id", "exchange", "name", "instrument_type", "confidence"]
        ].drop_duplicates(),
        on=["yahoo_symbol", "country_iso3"],
        how="left",
        suffixes=("", "_meta"),
    )

    broadcast_path = out_dir / "ticker_week_country_broadcast_panel.parquet"
    if broadcast_path.exists():
        broadcast = pd.read_parquet(broadcast_path)
        broadcast["week_end"] = pd.to_datetime(broadcast["week_end"], errors="coerce")
        bcols = [c for c in broadcast.columns if c.startswith("country_broadcast_")]
        if not bcols:
            rename_map = {c: f"country_broadcast_{c}" for c in broadcast.columns if c not in {
                "yahoo_symbol", "country_iso3", "week_end", "entity_id", "exchange", "name",
                "instrument_type", "confidence", "row_count_daily", "price", "return_1w",
                "return_4w", "fwd_return_1w", "fwd_return_2w", "fwd_return_4w", "fwd_vol_4w",
                "market_data_ffilled", "join_mode",
            }}
            broadcast = broadcast.rename(columns=rename_map)
            bcols = list(rename_map.values())
        panel = panel.merge(
            broadcast[["yahoo_symbol", "week_end", *bcols]],
            on=["yahoo_symbol", "week_end"],
            how="left",
        )
    panel["join_mode"] = "entity_resolved"
    if "row_count_daily" in panel.columns:
        panel["liquidity_bucket"] = panel["row_count_daily"].map(liquidity_bucket)
    elif "row_count_daily_meta" in panel.columns:
        panel["liquidity_bucket"] = panel["row_count_daily_meta"].map(liquidity_bucket)

    outputs = {
        "ticker_week_entity_market_panel": write_frame(panel, out_dir / "ticker_week_entity_market_panel"),
    }
    return {
        "phase": "fused",
        "panel_rows": int(len(panel)),
        "tickers": int(panel["yahoo_symbol"].nunique()) if not panel.empty else 0,
        "week_min": str(panel["week_end"].min().date()) if not panel.empty else "",
        "week_max": str(panel["week_end"].max().date()) if not panel.empty else "",
        "outputs": outputs,
        "panel_path": str(out_dir / "ticker_week_entity_market_panel.parquet"),
    }


def run_tier3_extras_phase(
    args: argparse.Namespace,
    out_dir: Path,
    entities: pd.DataFrame,
    market_run_dir: Path,
) -> dict[str, object]:
    entity_path = out_dir / "ticker_week_entity_news_panel.parquet"
    if not entity_path.exists():
        raise FileNotFoundError("run entity phase first")
    entity_weekly = pd.read_parquet(entity_path)
    tickers = set(entities["yahoo_symbol"])
    prices = load_ticker_daily_prices(market_run_dir, tickers)
    weekly_returns = build_weekly_ticker_returns(prices, ffill_holidays=True)
    ticker_meta = entities.rename(columns={"market_country": "country_iso3"})
    weekly_returns = weekly_returns.merge(
        ticker_meta[["yahoo_symbol", "country_iso3", "row_count_daily"]].drop_duplicates(),
        on="yahoo_symbol",
        how="left",
    )

    long_panel = build_entity_long_panel(weekly_returns, entity_weekly)
    meta = ticker_meta[["yahoo_symbol", "row_count_daily"]].drop_duplicates()
    if "row_count_daily" in long_panel.columns:
        long_panel = long_panel.drop(columns=["row_count_daily"])
    long_panel = long_panel.merge(meta, on="yahoo_symbol", how="left")
    long_panel["liquidity_bucket"] = long_panel["row_count_daily"].map(liquidity_bucket)

    fused_path = out_dir / "ticker_week_entity_market_panel.parquet"
    residual_panel = pd.DataFrame()
    if fused_path.exists():
        entity_market = pd.read_parquet(fused_path)
        broadcast_path = out_dir / "ticker_week_country_broadcast_panel.parquet"
        if broadcast_path.exists():
            residual_panel = build_entity_broadcast_residual(entity_market, pd.read_parquet(broadcast_path))

    outputs = {
        "ticker_week_entity_long_panel": write_frame(long_panel, out_dir / "ticker_week_entity_long_panel"),
    }
    if not residual_panel.empty:
        outputs["ticker_week_entity_residual_panel"] = write_frame(
            residual_panel, out_dir / "ticker_week_entity_residual_panel"
        )

    return {
        "phase": "tier3_extras",
        "long_rows": int(len(long_panel)),
        "long_with_news_pct": float(long_panel["has_entity_news"].mean() * 100) if not long_panel.empty else 0.0,
        "residual_rows": int(len(residual_panel)),
        "outputs": outputs,
    }


def main() -> int:
    args = parse_args()
    run_id = args.run_id or now_run_id()
    out_dir = args.out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    countries = args.countries or None
    entities_broadcast = load_entity_universe(
        args.entity_root,
        args.entity_run,
        min_price_rows=args.min_price_rows,
        countries=countries,
    )
    entities_entity = load_entity_universe(
        args.entity_root,
        args.entity_run,
        min_price_rows=args.min_price_rows_entity,
        countries=countries,
    )
    market_run_dir = latest_run(args.market_root) if args.market_run == "latest" else args.market_root / args.market_run

    summary: dict[str, object] = {
        "run_id": run_id,
        "built_at_utc": datetime.now(UTC).isoformat(),
        "phases": {},
        "lineage": {
            "fused_panel": str(args.fused_panel),
            "entity_root": str(latest_run(args.entity_root) if args.entity_run == "latest" else args.entity_root / args.entity_run),
            "market_run": str(market_run_dir),
            "entity_overlay_root": str(args.entity_overlay_root),
            "min_price_rows_broadcast": args.min_price_rows,
            "min_price_rows_entity": args.min_price_rows_entity,
            "alias_supplement": str(args.alias_supplement),
            "min_market_relevance": args.min_market_relevance,
            "dedupe_urls": args.dedupe_urls,
            "countries_filter": countries or [],
        },
    }

    phases = ["broadcast", "entity", "fused", "tier3_extras"] if args.phase == "all" else [args.phase]
    for phase in phases:
        if phase == "broadcast":
            summary["phases"]["broadcast"] = run_broadcast_phase(args, out_dir, entities_broadcast, market_run_dir)
        elif phase == "entity":
            summary["phases"]["entity"] = run_entity_phase(args, out_dir, entities_entity)
        elif phase == "fused":
            summary["phases"]["fused"] = run_fused_phase(args, out_dir, entities_entity, market_run_dir)
        elif phase == "tier3_extras":
            summary["phases"]["tier3_extras"] = run_tier3_extras_phase(
                args, out_dir, entities_entity, market_run_dir
            )

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
