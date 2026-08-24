#!/usr/bin/env python3
"""Build an Asia country-week news-shock and market-return panel.

This is the first research-ready bridge between the GDELT Asia news-shock
backlog and accessible market data. It intentionally works from completed
monthly processed windows, so the always-on downloader can keep running while
this script produces usable panels from whatever has already landed.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DEFAULT_NEWS_ROOT = REPO / "data_lake/news_shock_taxonomy/processed"
DEFAULT_MARKET_ROOT = REPO / "data_lake/markets/yfinance_asia"
DEFAULT_OUT_ROOT = REPO / "data_lake/research_panels/asia_news_market"

SHOCK_COLUMNS = [
    "financial_stress_rows",
    "geopolitical_security_rows",
    "governance_corruption_rows",
    "health_rows",
    "macro_policy_rows",
    "natural_environment_rows",
    "political_instability_rows",
    "trade_supply_chain_rows",
]


@dataclass(frozen=True)
class MarketProxy:
    country_iso3: str
    proxy_type: str
    instrument: str


MARKET_PROXIES = [
    MarketProxy("AUS", "index", "^AXJO"),
    MarketProxy("AUS", "etf", "EWA"),
    MarketProxy("CHN", "index", "000001.SS"),
    MarketProxy("CHN", "etf", "MCHI"),
    MarketProxy("CHN", "fx_usd_local", "USDCNY=X"),
    MarketProxy("HKG", "index", "^HSI"),
    MarketProxy("HKG", "etf", "EWH"),
    MarketProxy("HKG", "fx_usd_local", "USDHKD=X"),
    MarketProxy("IDN", "index", "^JKSE"),
    MarketProxy("IDN", "etf", "EIDO"),
    MarketProxy("IDN", "fx_usd_local", "USDIDR=X"),
    MarketProxy("IND", "index", "^NSEI"),
    MarketProxy("IND", "etf", "INDA"),
    MarketProxy("JPN", "index", "^N225"),
    MarketProxy("JPN", "etf", "EWJ"),
    MarketProxy("JPN", "fx_usd_local", "USDJPY=X"),
    MarketProxy("KOR", "index", "^KS11"),
    MarketProxy("KOR", "etf", "EWY"),
    MarketProxy("KOR", "fx_usd_local", "USDKRW=X"),
    MarketProxy("MYS", "index", "^KLSE"),
    MarketProxy("MYS", "etf", "EWM"),
    MarketProxy("MYS", "fx_usd_local", "USDMYR=X"),
    MarketProxy("PHL", "index", "PSEI.PS"),
    MarketProxy("PHL", "etf", "EPHE"),
    MarketProxy("PHL", "fx_usd_local", "USDPHP=X"),
    MarketProxy("SGP", "index", "^STI"),
    MarketProxy("SGP", "etf", "EWS"),
    MarketProxy("SGP", "fx_usd_local", "USDSGD=X"),
    MarketProxy("THA", "index", "^SET.BK"),
    MarketProxy("THA", "etf", "THD"),
    MarketProxy("THA", "fx_usd_local", "USDTHB=X"),
    MarketProxy("TWN", "index", "^TWII"),
    MarketProxy("TWN", "etf", "EWT"),
    MarketProxy("TWN", "fx_usd_local", "USDTWD=X"),
    MarketProxy("VNM", "etf", "VNM"),
    MarketProxy("VNM", "fx_usd_local", "USDVND=X"),
]


PRIMARY_PROXY = {
    "AUS": ("index", "^AXJO"),
    "CHN": ("index", "000001.SS"),
    "HKG": ("index", "^HSI"),
    "IDN": ("index", "^JKSE"),
    "IND": ("index", "^NSEI"),
    "JPN": ("index", "^N225"),
    "KOR": ("index", "^KS11"),
    "MYS": ("index", "^KLSE"),
    "PHL": ("index", "PSEI.PS"),
    "SGP": ("index", "^STI"),
    "THA": ("index", "^SET.BK"),
    "TWN": ("index", "^TWII"),
    "VNM": ("etf", "VNM"),
}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--news-root", type=Path, default=DEFAULT_NEWS_ROOT)
    ap.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    ap.add_argument("--market-run", default="latest", help="Market run id or latest.")
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    ap.add_argument("--run-id", default="")
    ap.add_argument(
        "--news-run",
        action="append",
        default=[],
        help="Specific processed news run id. Repeatable. Default: all asia_gkg_window_* runs.",
    )
    return ap.parse_args()


def latest_run(root: Path) -> Path:
    candidates = [p for p in root.iterdir() if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"no run directories under {root}")
    return sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]


def news_run_dirs(root: Path, requested: list[str]) -> list[Path]:
    if requested:
        dirs = [root / run_id for run_id in requested]
    else:
        dirs = sorted(p for p in root.glob("asia_gkg_window_*") if p.is_dir())
    out = []
    for path in dirs:
        panel = path / "daily_country_shock_panel.csv"
        if panel.exists():
            out.append(path)
    if not out:
        raise FileNotFoundError(f"no completed daily_country_shock_panel.csv files under {root}")
    return out


def load_daily_news(run_dirs: list[Path]) -> pd.DataFrame:
    frames = []
    for path in run_dirs:
        df = pd.read_csv(path / "daily_country_shock_panel.csv")
        df.insert(0, "news_run_id", path.name)
        frames.append(df)
    news = pd.concat(frames, ignore_index=True)
    news["date"] = pd.to_datetime(news["date"], errors="coerce")
    news = news.dropna(subset=["date", "country_iso3"])
    for col in ["rows", "unique_urls", "high_priority_urls", "market_relevant_rows", "broad_context_rows", *SHOCK_COLUMNS]:
        if col not in news.columns:
            news[col] = 0
        news[col] = pd.to_numeric(news[col], errors="coerce").fillna(0.0)
    for col in ["mean_tone", "mean_market_relevance_score"]:
        news[col] = pd.to_numeric(news[col], errors="coerce")
    return news


def build_weekly_news(daily: pd.DataFrame) -> pd.DataFrame:
    daily = daily.copy()
    daily["week_end"] = daily["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
    daily["tone_weight_rows"] = daily["mean_tone"].fillna(0.0) * daily["rows"]
    daily["tone_nonnull_rows"] = daily["rows"].where(daily["mean_tone"].notna(), 0.0)
    daily["relevance_weight_rows"] = daily["mean_market_relevance_score"].fillna(0.0) * daily["rows"]
    daily["relevance_nonnull_rows"] = daily["rows"].where(daily["mean_market_relevance_score"].notna(), 0.0)
    grouped = daily.groupby(["country_iso3", "week_end"], as_index=False)
    pieces = grouped.agg(
        news_days=("date", "nunique"),
        news_rows=("rows", "sum"),
        unique_urls=("unique_urls", "sum"),
        high_priority_urls=("high_priority_urls", "sum"),
        market_relevant_rows=("market_relevant_rows", "sum"),
        broad_context_rows=("broad_context_rows", "sum"),
        tone_weight_rows=("tone_weight_rows", "sum"),
        tone_nonnull_rows=("tone_nonnull_rows", "sum"),
        relevance_weight_rows=("relevance_weight_rows", "sum"),
        relevance_nonnull_rows=("relevance_nonnull_rows", "sum"),
        source_news_runs=("news_run_id", lambda s: "|".join(sorted(set(map(str, s))))),
    )
    pieces["mean_tone_weighted"] = pieces["tone_weight_rows"] / pieces["tone_nonnull_rows"].replace(0, pd.NA)
    pieces["mean_market_relevance_score_weighted"] = (
        pieces["relevance_weight_rows"] / pieces["relevance_nonnull_rows"].replace(0, pd.NA)
    )
    pieces = pieces.drop(columns=["tone_weight_rows", "tone_nonnull_rows", "relevance_weight_rows", "relevance_nonnull_rows"])
    shock_week = grouped[SHOCK_COLUMNS].sum().reset_index()
    pieces = pieces.merge(shock_week, on=["country_iso3", "week_end"], how="left")

    denom = pieces["news_rows"].replace(0, pd.NA)
    pieces["market_relevant_share"] = pieces["market_relevant_rows"] / denom
    pieces["broad_context_share"] = pieces["broad_context_rows"] / denom
    for col in SHOCK_COLUMNS:
        base = col.removesuffix("_rows")
        pieces[f"{base}_share"] = pieces[col] / denom
        pieces[f"{base}_per_1k_rows"] = pieces[col] / denom * 1000.0
    return pieces.sort_values(["country_iso3", "week_end"]).reset_index(drop=True)


def load_market_panels(market_run_dir: Path) -> pd.DataFrame:
    files = [
        market_run_dir / "asia_benchmarks_fx_commodities.parquet",
        market_run_dir / "asia_etf_proxies.parquet",
    ]
    frames = []
    for path in files:
        if not path.exists():
            csv_path = path.with_suffix(".csv")
            if not csv_path.exists():
                continue
            df = pd.read_csv(csv_path)
        else:
            df = pd.read_parquet(path)
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"no benchmark/ETF market files found in {market_run_dir}")
    market = pd.concat(frames, ignore_index=True)
    market["date"] = pd.to_datetime(market["date"], errors="coerce")
    market["adj_close"] = pd.to_numeric(market["adj_close"], errors="coerce")
    market["close"] = pd.to_numeric(market["close"], errors="coerce")
    market = market.dropna(subset=["date", "instrument"])
    market["price"] = market["adj_close"].fillna(market["close"])
    proxy_map = pd.DataFrame([proxy.__dict__ for proxy in MARKET_PROXIES])
    market = market.merge(proxy_map, on="instrument", how="inner")
    return market


def build_weekly_market(market: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for (country, proxy_type, instrument), group in market.groupby(["country_iso3", "proxy_type", "instrument"]):
        g = group.sort_values("date").set_index("date")
        weekly = g["price"].resample("W-FRI").last().dropna().to_frame("price")
        if weekly.empty:
            continue
        weekly["country_iso3"] = country
        weekly["proxy_type"] = proxy_type
        weekly["instrument"] = instrument
        weekly["return_1w"] = weekly["price"].pct_change()
        weekly["return_4w"] = weekly["price"].pct_change(4)
        weekly["fwd_return_1w"] = weekly["price"].shift(-1) / weekly["price"] - 1.0
        weekly["fwd_return_2w"] = weekly["price"].shift(-2) / weekly["price"] - 1.0
        weekly["fwd_return_4w"] = weekly["price"].shift(-4) / weekly["price"] - 1.0
        weekly["fwd_vol_4w"] = weekly["return_1w"].shift(-1).rolling(4).std().shift(-3)
        frames.append(weekly.reset_index().rename(columns={"date": "week_end"}))
    if not frames:
        raise ValueError("no market proxy rows matched configured proxy map")
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["country_iso3", "proxy_type", "instrument", "week_end"]).reset_index(drop=True)


def write_frame(df: pd.DataFrame, path: Path) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = path.with_suffix(".csv")
    parquet_path = path.with_suffix(".parquet")
    df.to_csv(csv_path, index=False)
    parquet_written = False
    try:
        df.to_parquet(parquet_path, index=False)
        parquet_written = True
    except Exception:
        parquet_path = None
    return {
        "csv": str(csv_path),
        "parquet": str(parquet_path) if parquet_written and parquet_path else "",
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
    }


def main() -> int:
    args = parse_args()
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out_root / run_id
    market_run_dir = latest_run(args.market_root) if args.market_run == "latest" else args.market_root / args.market_run

    runs = news_run_dirs(args.news_root, args.news_run)
    daily_news = load_daily_news(runs)
    weekly_news = build_weekly_news(daily_news)
    market = load_market_panels(market_run_dir)
    weekly_market = build_weekly_market(market)
    panel = weekly_news.merge(weekly_market, on=["country_iso3", "week_end"], how="inner")

    primary_rows = []
    for country, (proxy_type, instrument) in PRIMARY_PROXY.items():
        primary_rows.append((country, proxy_type, instrument))
    primary = pd.DataFrame(primary_rows, columns=["country_iso3", "proxy_type", "instrument"])
    primary_panel = panel.merge(primary, on=["country_iso3", "proxy_type", "instrument"], how="inner")

    outputs = {
        "country_week_news_panel": write_frame(weekly_news, out_dir / "country_week_news_panel"),
        "market_country_week_panel": write_frame(weekly_market, out_dir / "market_country_week_panel"),
        "asia_country_week_news_market_panel": write_frame(panel, out_dir / "asia_country_week_news_market_panel"),
        "asia_country_week_news_market_primary_panel": write_frame(
            primary_panel,
            out_dir / "asia_country_week_news_market_primary_panel",
        ),
    }
    summary = {
        "run_id": run_id,
        "built_at_utc": datetime.now(UTC).isoformat(),
        "news_runs": [p.name for p in runs],
        "market_run": str(market_run_dir),
        "date_min": str(weekly_news["week_end"].min().date()) if not weekly_news.empty else "",
        "date_max": str(weekly_news["week_end"].max().date()) if not weekly_news.empty else "",
        "countries": sorted(weekly_news["country_iso3"].dropna().unique().tolist()),
        "market_proxy_count": int(weekly_market[["country_iso3", "proxy_type", "instrument"]].drop_duplicates().shape[0]),
        "outputs": outputs,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
