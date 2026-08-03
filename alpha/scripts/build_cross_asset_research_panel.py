#!/usr/bin/env python3
"""Fuse GDELT news-shock, entity mapping, Asia equities, crypto, and macro controls.

Produces a research-ready multi-layer panel:
  news (country-day / country-week)
  + market returns (country proxies)
  + crypto news overlay (country-day / country-week)
  + global crypto + macro controls (week)
  + entity coverage registry (country static)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_asia_news_market_panel import (  # noqa: E402
    MARKET_PROXIES,
    PRIMARY_PROXY,
    SHOCK_COLUMNS,
    build_weekly_market,
    build_weekly_news,
    latest_run,
    load_daily_news,
    load_market_panels,
    write_frame,
)

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
DEFAULT_NEWS_ROOT = REPO / "data_lake/news_shock_taxonomy/processed"
DEFAULT_CRYPTO_OVERLAY_ROOT = REPO / "data_lake/news_shock_taxonomy/derived/gdelt_crypto_overlay"
DEFAULT_MARKET_ROOT = REPO / "data_lake/markets/yfinance_asia"
DEFAULT_ENTITY_ROOT = REPO / "data_lake/entity_mapping/asia"
DEFAULT_ALPHA_PANEL = REPO / "data_lake/daily_alpha_panel.csv"
DEFAULT_MACRO_ROOT = REPO / "data_lake/public_macro_market_baseline"
DEFAULT_OUT_ROOT = REPO / "data_lake/research_panels/cross_asset_fused"

WINDOW_RE = re.compile(r"^asia_gkg_window_(\d{8})_(\d{8})_")

GLOBAL_CRYPTO = ["BTC-USD", "ETH-USD"]
GLOBAL_MACRO = ["SPY", "GLD", "DBC", "BIL", "IWM", "EFA", "EEM"]

EQUITY_TYPES = {"equity_or_fund", "company"}
ETF_TYPES = {"etf_or_fund"}

INSTRUMENT_COUNTRY_MAP: dict[str, str] = {}
for _country, (_ptype, _inst) in PRIMARY_PROXY.items():
    INSTRUMENT_COUNTRY_MAP[_inst] = _country
for _proxy in MARKET_PROXIES:
    INSTRUMENT_COUNTRY_MAP.setdefault(_proxy.instrument, _proxy.country_iso3)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--news-root", type=Path, default=DEFAULT_NEWS_ROOT)
    ap.add_argument("--crypto-overlay-root", type=Path, default=DEFAULT_CRYPTO_OVERLAY_ROOT)
    ap.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    ap.add_argument("--entity-root", type=Path, default=DEFAULT_ENTITY_ROOT)
    ap.add_argument("--alpha-panel", type=Path, default=DEFAULT_ALPHA_PANEL)
    ap.add_argument("--macro-root", type=Path, default=DEFAULT_MACRO_ROOT)
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--market-run", default="latest")
    ap.add_argument("--entity-run", default="latest")
    return ap.parse_args()


def canonical_news_run_dirs(root: Path) -> list[Path]:
    choices: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for panel in root.glob("*/daily_country_shock_panel.csv"):
        match = WINDOW_RE.match(panel.parent.name)
        if not match:
            continue
        choices[(match.group(1), match.group(2))].append(panel.parent)
    out: list[Path] = []
    for _, paths in sorted(choices.items()):
        paths.sort(key=lambda p: (p / "daily_country_shock_panel.csv").stat().st_mtime, reverse=True)
        out.append(paths[0])
    if not out:
        raise FileNotFoundError(f"no canonical news windows under {root}")
    return out


def canonical_crypto_overlay_dirs(root: Path) -> list[Path]:
    choices: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for panel in root.glob("*/daily_country_crypto_panel.csv"):
        match = WINDOW_RE.match(panel.parent.name)
        if not match:
            continue
        choices[(match.group(1), match.group(2))].append(panel.parent)
    out: list[Path] = []
    for _, paths in sorted(choices.items()):
        paths.sort(key=lambda p: (p / "daily_country_crypto_panel.csv").stat().st_mtime, reverse=True)
        out.append(paths[0])
    return out


def load_daily_crypto_overlay(run_dirs: list[Path]) -> pd.DataFrame:
    if not run_dirs:
        return pd.DataFrame()
    frames = []
    for path in run_dirs:
        df = pd.read_csv(path / "daily_country_crypto_panel.csv")
        df.insert(0, "crypto_run_id", path.name)
        frames.append(df)
    crypto = pd.concat(frames, ignore_index=True)
    crypto["date"] = pd.to_datetime(crypto["date"], errors="coerce")
    crypto = crypto.dropna(subset=["date", "country_iso3"])
    for col in crypto.columns:
        if col.endswith("_rows") or col == "crypto_rows":
            crypto[col] = pd.to_numeric(crypto[col], errors="coerce").fillna(0.0)
    return crypto


def build_weekly_crypto(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return daily
    daily = daily.copy()
    daily["week_end"] = daily["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
    count_cols = [c for c in daily.columns if c.endswith("_rows") or c == "crypto_rows"]
    grouped = daily.groupby(["country_iso3", "week_end"], as_index=False)
    pieces = grouped[count_cols].sum()
    meta = grouped.agg(
        crypto_news_days=("date", "nunique"),
        source_crypto_runs=("crypto_run_id", lambda s: "|".join(sorted(set(map(str, s))))),
    )
    pieces = pieces.merge(meta, on=["country_iso3", "week_end"], how="left")
    denom = pieces["crypto_rows"].replace(0, pd.NA)
    for col in count_cols:
        if col == "crypto_rows":
            continue
        base = col.removesuffix("_rows")
        pieces[f"{base}_per_1k_crypto_rows"] = pieces[col] / denom * 1000.0
    return pieces.sort_values(["country_iso3", "week_end"]).reset_index(drop=True)


def load_global_prices(alpha_panel: Path) -> pd.DataFrame:
    if not alpha_panel.exists():
        return pd.DataFrame()
    df = pd.read_csv(alpha_panel)
    df = df.rename(columns={"Instrument": "instrument", "Date": "date", "Price_Close": "price"})
    wanted = set(GLOBAL_CRYPTO + GLOBAL_MACRO)
    df = df[df["instrument"].isin(wanted)].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    return df.dropna(subset=["date", "instrument", "price"])


def build_weekly_global_assets(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return prices
    frames = []
    for instrument, group in prices.groupby("instrument"):
        g = group.sort_values("date").set_index("date")
        weekly = g["price"].resample("W-FRI").last().dropna().to_frame("price")
        if weekly.empty:
            continue
        weekly["instrument"] = instrument
        weekly["return_1w"] = weekly["price"].pct_change()
        weekly["return_4w"] = weekly["price"].pct_change(4)
        weekly["fwd_return_1w"] = weekly["price"].shift(-1) / weekly["price"] - 1.0
        weekly["fwd_return_4w"] = weekly["price"].shift(-4) / weekly["price"] - 1.0
        frames.append(weekly.reset_index().rename(columns={"date": "week_end"}))
    long = pd.concat(frames, ignore_index=True)
    pivot_price = long.pivot(index="week_end", columns="instrument", values="price")
    pivot_ret = long.pivot(index="week_end", columns="instrument", values="return_1w")
    pivot_fwd = long.pivot(index="week_end", columns="instrument", values="fwd_return_1w")
    out = pd.DataFrame({"week_end": pivot_price.index})
    for instrument in pivot_price.columns:
        out[f"global_{instrument}_price"] = pivot_price[instrument].values
        out[f"global_{instrument}_return_1w"] = pivot_ret[instrument].values
        out[f"global_{instrument}_fwd_return_1w"] = pivot_fwd[instrument].values
    return out.sort_values("week_end").reset_index(drop=True)


def build_weekly_market_ffill(market: pd.DataFrame) -> pd.DataFrame:
    """Weekly market panel with forward-filled holiday weeks (zero return when closed)."""
    frames = []
    for (country, proxy_type, instrument), group in market.groupby(["country_iso3", "proxy_type", "instrument"]):
        g = group.sort_values("date").set_index("date")
        observed = g["price"].astype(float).resample("W-FRI").last()
        filled = observed.ffill()
        weekly = filled.to_frame("price")
        if weekly.empty:
            continue
        weekly["country_iso3"] = country
        weekly["proxy_type"] = proxy_type
        weekly["instrument"] = instrument
        weekly["market_data_ffilled"] = observed.isna() & filled.notna()
        weekly["return_1w"] = weekly["price"].pct_change()
        weekly["return_4w"] = weekly["price"].pct_change(4)
        weekly["fwd_return_1w"] = weekly["price"].shift(-1) / weekly["price"] - 1.0
        weekly["fwd_return_2w"] = weekly["price"].shift(-2) / weekly["price"] - 1.0
        weekly["fwd_return_4w"] = weekly["price"].shift(-4) / weekly["price"] - 1.0
        weekly["fwd_vol_4w"] = weekly["return_1w"].shift(-1).rolling(4).std().shift(-3)
        frames.append(weekly.reset_index().rename(columns={"date": "week_end"}))
    if not frames:
        raise ValueError("no market proxy rows matched configured proxy map")
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(["country_iso3", "proxy_type", "instrument", "week_end"])
        .reset_index(drop=True)
    )


def select_primary_market_weekly(weekly_market: pd.DataFrame) -> pd.DataFrame:
    primary_rows = [(c, pt, inst) for c, (pt, inst) in PRIMARY_PROXY.items()]
    primary = pd.DataFrame(primary_rows, columns=["country_iso3", "proxy_type", "instrument"])
    return weekly_market.merge(primary, on=["country_iso3", "proxy_type", "instrument"], how="inner")


def load_vix_weekly(macro_root: Path) -> pd.DataFrame:
    candidates = sorted(macro_root.glob("*/raw/cboe/VIX_History.csv"))
    if not candidates:
        return pd.DataFrame()
    path = candidates[-1]
    vix = pd.read_csv(path)
    vix = vix.rename(columns={"DATE": "date", "CLOSE": "vix_close"})
    vix["date"] = pd.to_datetime(vix["date"], errors="coerce")
    vix["vix_close"] = pd.to_numeric(vix["vix_close"], errors="coerce")
    vix = vix.dropna(subset=["date", "vix_close"]).sort_values("date")
    vix["week_end"] = vix["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
    weekly = vix.groupby("week_end", as_index=False).agg(vix_close=("vix_close", "last"))
    weekly["vix_return_1w"] = weekly["vix_close"].pct_change()
    weekly["vix_fwd_return_1w"] = weekly["vix_close"].shift(-1) / weekly["vix_close"] - 1.0
    return weekly


def _supplement_benchmark_entities(master: pd.DataFrame) -> pd.DataFrame:
    """Add primary index/ETF proxies for countries missing from entity master."""
    present = set(master["market_country"].dropna().astype(str).str.strip())
    rows = []
    for country, (proxy_type, instrument) in PRIMARY_PROXY.items():
        if country in present:
            continue
        rows.append(
            {
                "entity_id": f"BENCHMARK:{instrument}",
                "market_country": country,
                "exchange": "INDEX" if proxy_type == "index" else "ETF_PROXY",
                "local_code": instrument,
                "yahoo_symbol": instrument,
                "instrument_type": "index" if proxy_type == "index" else "etf_or_fund",
                "source_tags": "benchmark_proxy_supplement",
                "confidence": "medium",
                "row_count_daily": pd.NA,
            }
        )
    if not rows:
        return master
    return pd.concat([master, pd.DataFrame(rows)], ignore_index=True)


def load_entity_coverage(entity_root: Path, entity_run: str) -> pd.DataFrame:
    run_dir = latest_run(entity_root) if entity_run == "latest" else entity_root / entity_run
    master_path = run_dir / "asia_entity_master.csv"
    if not master_path.exists():
        return pd.DataFrame()
    master = pd.read_csv(master_path)
    master["market_country"] = master["market_country"].fillna("").astype(str).str.strip()
    missing_country = master["market_country"] == ""
    master.loc[missing_country, "market_country"] = master.loc[missing_country, "yahoo_symbol"].map(
        INSTRUMENT_COUNTRY_MAP
    )
    master["market_country"] = master["market_country"].fillna("").astype(str).str.strip()
    master = _supplement_benchmark_entities(master)
    master = master[master["market_country"] != ""]
    grouped = master.groupby("market_country", as_index=False).agg(
        entity_count=("entity_id", "nunique"),
        equity_count=("instrument_type", lambda s: int(s.isin(EQUITY_TYPES).sum())),
        etf_count=("instrument_type", lambda s: int(s.isin(ETF_TYPES).sum())),
        index_count=("instrument_type", lambda s: int((s == "index").sum())),
        high_confidence_count=("confidence", lambda s: int((s == "high").sum())),
        median_price_history_rows=("row_count_daily", "median"),
    )
    grouped = grouped.rename(columns={"market_country": "country_iso3"})
    tradable = master[master["instrument_type"].isin(EQUITY_TYPES | ETF_TYPES)].copy()
    tradable["row_count_daily"] = pd.to_numeric(tradable["row_count_daily"], errors="coerce")
    top = (
        tradable.sort_values(["market_country", "row_count_daily"], ascending=[True, False], na_position="last")
        .groupby("market_country")
        .head(5)
        .groupby("market_country")["yahoo_symbol"]
        .apply(lambda s: "|".join(s.astype(str)))
        .reset_index()
        .rename(columns={"market_country": "country_iso3", "yahoo_symbol": "top_yahoo_symbols"})
    )
    out = grouped.merge(top, on="country_iso3", how="left")
    for country, (proxy_type, instrument) in PRIMARY_PROXY.items():
        mask = out["country_iso3"] == country
        if not mask.any():
            continue
        missing_top = out.loc[mask, "top_yahoo_symbols"].isna() | (out.loc[mask, "top_yahoo_symbols"] == "")
        if missing_top.any():
            out.loc[mask, "top_yahoo_symbols"] = instrument
    return out


def build_fused_primary_panel(
    weekly_news: pd.DataFrame,
    primary_market: pd.DataFrame,
    weekly_crypto: pd.DataFrame,
    weekly_global: pd.DataFrame,
    weekly_vix: pd.DataFrame,
    entity_cov: pd.DataFrame,
) -> pd.DataFrame:
    panel = weekly_news.merge(primary_market, on=["country_iso3", "week_end"], how="left")
    if not weekly_crypto.empty:
        panel = panel.merge(weekly_crypto, on=["country_iso3", "week_end"], how="left")
    if not weekly_global.empty:
        panel = panel.merge(weekly_global, on="week_end", how="left")
    if not weekly_vix.empty:
        panel = panel.merge(weekly_vix, on="week_end", how="left")
    if not entity_cov.empty:
        panel = panel.merge(entity_cov, on="country_iso3", how="left")
    return panel.sort_values(["country_iso3", "week_end"]).reset_index(drop=True)


def main() -> int:
    args = parse_args()
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out_root / run_id

    news_runs = canonical_news_run_dirs(args.news_root)
    crypto_runs = canonical_crypto_overlay_dirs(args.crypto_overlay_root)
    market_run_dir = (
        latest_run(args.market_root) if args.market_run == "latest" else args.market_root / args.market_run
    )

    daily_news = load_daily_news(news_runs)
    weekly_news = build_weekly_news(daily_news)
    market = load_market_panels(market_run_dir)
    weekly_market = build_weekly_market(market)
    weekly_market_ffill = build_weekly_market_ffill(market)
    primary_market = select_primary_market_weekly(weekly_market_ffill)

    daily_crypto = load_daily_crypto_overlay(crypto_runs)
    weekly_crypto = build_weekly_crypto(daily_crypto)

    global_prices = load_global_prices(args.alpha_panel)
    weekly_global = build_weekly_global_assets(global_prices)
    weekly_vix = load_vix_weekly(args.macro_root)

    entity_cov = load_entity_coverage(args.entity_root, args.entity_run)

    fused_all = weekly_news.merge(weekly_market, on=["country_iso3", "week_end"], how="inner")
    if not weekly_crypto.empty:
        fused_all = fused_all.merge(weekly_crypto, on=["country_iso3", "week_end"], how="left")
    if not weekly_global.empty:
        fused_all = fused_all.merge(weekly_global, on="week_end", how="left")
    if not weekly_vix.empty:
        fused_all = fused_all.merge(weekly_vix, on="week_end", how="left")

    primary_panel = build_fused_primary_panel(
        weekly_news, primary_market, weekly_crypto, weekly_global, weekly_vix, entity_cov
    )

    ffilled_weeks = int(primary_panel["market_data_ffilled"].fillna(False).sum()) if "market_data_ffilled" in primary_panel.columns else 0
    news_weeks_retained = int(primary_panel["return_1w"].notna().sum()) if "return_1w" in primary_panel.columns else 0

    outputs = {
        "daily_country_news_panel": write_frame(daily_news, out_dir / "daily_country_news_panel"),
        "daily_country_crypto_news_panel": write_frame(daily_crypto, out_dir / "daily_country_crypto_news_panel"),
        "country_week_news_panel": write_frame(weekly_news, out_dir / "country_week_news_panel"),
        "country_week_crypto_news_panel": write_frame(weekly_crypto, out_dir / "country_week_crypto_news_panel"),
        "market_country_week_panel": write_frame(weekly_market, out_dir / "market_country_week_panel"),
        "market_country_week_ffill_panel": write_frame(weekly_market_ffill, out_dir / "market_country_week_ffill_panel"),
        "primary_market_week_panel": write_frame(primary_market, out_dir / "primary_market_week_panel"),
        "global_assets_week_panel": write_frame(weekly_global, out_dir / "global_assets_week_panel"),
        "macro_vix_week_panel": write_frame(weekly_vix, out_dir / "macro_vix_week_panel"),
        "country_entity_coverage": write_frame(entity_cov, out_dir / "country_entity_coverage"),
        "cross_asset_country_week_panel": write_frame(fused_all, out_dir / "cross_asset_country_week_panel"),
        "cross_asset_fused_primary_panel": write_frame(primary_panel, out_dir / "cross_asset_fused_primary_panel"),
    }

    summary = {
        "run_id": run_id,
        "built_at_utc": datetime.now(UTC).isoformat(),
        "lineage": {
            "news_windows": len(news_runs),
            "crypto_overlay_windows": len(crypto_runs),
            "market_run": str(market_run_dir),
            "entity_run": str(latest_run(args.entity_root) if args.entity_run == "latest" else args.entity_root / args.entity_run),
            "alpha_panel": str(args.alpha_panel),
            "macro_root": str(args.macro_root),
        },
        "coverage": {
            "news_date_min": str(daily_news["date"].min().date()) if not daily_news.empty else "",
            "news_date_max": str(daily_news["date"].max().date()) if not daily_news.empty else "",
            "countries": sorted(daily_news["country_iso3"].dropna().unique().tolist()),
            "primary_panel_rows": int(len(primary_panel)),
            "primary_panel_weeks": int(primary_panel["week_end"].nunique()) if not primary_panel.empty else 0,
            "primary_panel_weeks_with_returns": news_weeks_retained,
            "primary_panel_ffilled_market_weeks": ffilled_weeks,
            "entity_countries": int(entity_cov["country_iso3"].nunique()) if not entity_cov.empty else 0,
        },
        "join_keys": {
            "country_week": ["country_iso3", "week_end"],
            "global_week": ["week_end"],
            "entity_static": ["country_iso3"],
        },
        "outputs": outputs,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
