#!/usr/bin/env python3
"""
Build a ticker-level watchlist from the Asia news-market country signal layer.

This script is explicitly a screening step, not a trading engine. It maps the latest
country-level model signal (e.g. `pred_fwd_return_1w`) onto a country-ticker set
and ranks tickers by a conservative composite score.

Outputs
-------
- watchlist_long_tickers.csv
- watchlist_short_tickers.csv
- ticker_signal_panel.csv
- summary.json
- README.md
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_ROOT = REPO / "backtests/outputs/asia_news_market_modeling"
DEFAULT_PANEL_FILE = (
    REPO
    / "data_lake/research_panels/asia_news_market/post_gdelt_parallel_20260526_marresume_repaired/"
    / "asia_country_week_news_market_primary_panel.parquet"
)
DEFAULT_OUT_ROOT = REPO / "backtests/outputs/asia_news_market_ticker_watchlist"
DEFAULT_COUNTRY_UNIVERSE_CONFIG = REPO / "config/markets/asia_yfinance_universes.json"
DEFAULT_MARKET_ROOT = REPO / "data_lake/markets/yfinance_asia"
DEFAULT_SOURCED_MAPPED_FILE = (
    REPO / "data_lake/markets/sourced_universes/20260526Tmarket_controls/asia_etf_holdings_mapped.csv"
)


DEFAULT_TARGET = "fwd_return_1w"
DEFAULT_PRED_COL = "pred_fwd_return_1w"
LOOKBACK_WINDOWS = {
    "ret_21d": 21,
    "ret_63d": 63,
    "vol_20d": 20,
    "vol_60d": 60,
}


COUNTRY_FROM_TICKER_SUFFIX: dict[str, str] = {
    ".TW": "TWN",
    ".KS": "KOR",
    ".T": "JPN",
    ".SS": "CHN",
    ".SZ": "CHN",
    ".HK": "HKG",
    ".JK": "IDN",
    ".SI": "SGP",
    ".KL": "MYS",
    ".BK": "THA",
    ".VN": "VNM",
    ".NS": "IND",
    ".BO": "IND",
}

COUNTRY_FROM_SOURCE_NAME = {
    "Taiwan": "TWN",
    "Korea": "KOR",
    "Japan": "JPN",
    "China": "CHN",
    "Hong Kong": "HKG",
    "Vietnam": "VNM",
    "Malaysia": "MYS",
    "Singapore": "SGP",
    "Thailand": "THA",
    "India": "IND",
    "Indonesia": "IDN",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-root", type=Path, default=DEFAULT_MODEL_ROOT)
    p.add_argument("--model-run", default="", help="Model run folder under --model-root. Default: latest.")
    p.add_argument(
        "--prediction-col",
        default=DEFAULT_PRED_COL,
        help="Prediction column from walk-forward model output.",
    )
    p.add_argument("--target", default=DEFAULT_TARGET, help="Fallback target column used when prediction-col is missing.")
    p.add_argument("--asof", type=str, default="", help="Week-end date YYYY-MM-DD. Default: latest week in model output.")

    p.add_argument("--panel-file", type=Path, default=DEFAULT_PANEL_FILE, help="Primary panel file for fallback signal fallback.")
    p.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT, help="YFinance market run folder or root.")
    p.add_argument("--market-run", default="latest", help="Market run id under --market-root or path to a single market file.")
    p.add_argument(
        "--country-config",
        type=Path,
        default=DEFAULT_COUNTRY_UNIVERSE_CONFIG,
        help="Universe config JSON with country-focused ticker universes.",
    )
    p.add_argument(
        "--sourced-mapped-file",
        type=Path,
        default=DEFAULT_SOURCED_MAPPED_FILE,
        help="ETF-holdings mapped CSV with `country`/`yahoo_symbol` columns (optional).",
    )
    p.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    p.add_argument("--run-id", default="")
    p.add_argument("--top", type=int, default=50, help="Watchlist size for both long and short.")
    p.add_argument("--min-data-points", type=int, default=60, help="Minimum rows per ticker for momentum/liquidity features.")
    p.add_argument("--min-volume-rank", type=float, default=0.10, help="Keep only top fraction by liquidity (0-1).")
    p.add_argument("--include-country-only", action="store_true", help="Only use country-level mapping from panel (no ETF mapped universe augment).")
    return p.parse_args()


@dataclass
class SignalContext:
    country_iso3: str
    as_of: str
    prediction_col: str
    pred_value: float
    target_value: float
    risk_score: float
    source: str


def _latest_subdir(root: Path) -> Path:
    if not root.exists():
        raise FileNotFoundError(f"missing root: {root}")
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        raise FileNotFoundError(f"no subdirectories under {root}")
    return sorted(dirs, key=lambda p: p.stat().st_mtime)[-1]


def _load_prediction_frame(model_root: Path, model_run: str, pred_col: str, target: str) -> pd.DataFrame:
    run_dir = _latest_subdir(model_root) if not model_run else (model_root / model_run)
    if not run_dir.exists():
        raise FileNotFoundError(f"model run not found: {run_dir}")

    preds_csv = run_dir / "walkforward_predictions.csv"
    if preds_csv.exists():
        df = pd.read_csv(preds_csv)
        if pred_col not in df.columns and pred_col != "":
            # fallback: create best available pred column
            for c in [f"pred_{target}", "pred_return_1w"]:
                if c in df.columns:
                    df[pred_col] = df[c]
                    break
            if pred_col not in df.columns:
                raise ValueError(f"Prediction column '{pred_col}' missing and no fallback found in {preds_csv}")
    else:
        primary_csv = run_dir / "walkforward_summary.csv"
        if primary_csv.exists():
            # final fallback only for schema continuity
            df = pd.read_csv(primary_csv)
            if "target" in df.columns and "pearson" in df.columns:
                # synthesize one-row placeholders per country from summary panel
                countries = sorted(df["target"].astype(str).unique())
                rows = []
                for c in countries:
                    rows.append(
                        {
                            "country_iso3": c.replace("fwd_return_", "").upper()[:3],
                            "week_end": pd.Timestamp.utcnow().normalize(),
                            "news_rows": 0.0,
                            "news_days": 0.0,
                            "risk_score": 0.0,
                            pred_col: 0.0,
                            "fwd_return_1w": 0.0,
                        }
                    )
                df = pd.DataFrame(rows)
            else:
                raise FileNotFoundError(f"No walkforward prediction file in {run_dir}")
        else:
            raise FileNotFoundError(f"No walkforward prediction file in {run_dir}")

    req = [
        "country_iso3",
        "week_end",
        "news_rows",
        "news_days",
        "risk_score",
        "pred_fwd_return_1w",
        "fwd_return_1w",
    ]
    for col in req:
        if col not in df.columns:
            raise ValueError(f"Prediction frame missing required column: {col}")
    df["week_end"] = pd.to_datetime(df["week_end"], errors="coerce")
    df["country_iso3"] = df["country_iso3"].astype(str).str.upper().str.strip()
    for c in [pred_col, "fwd_return_1w", "risk_score"]:
        if c not in df.columns and c != pred_col:
            continue
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["week_end", "country_iso3"])
    return df


def _load_country_map_from_universes(path: Path) -> dict[str, set[str]]:
    cfg = json.loads(path.read_text())
    ticker_map: dict[str, set[str]] = {}
    for uni in cfg.get("universes", []):
        tickers = [str(t) for t in uni.get("tickers", []) if str(t).strip()]
        uid = str(uni.get("id", "")).strip()
        description = str(uni.get("description", "")).lower()
        include_universe = all(
            token in uid for token in ["asia", "expanded", "core", "liquid", "idx"]
        )
        # Skip broad benchmark/ETF/FX universes (not mostly equities).
        if not tickers or "etf" in uid or "bench" in uid or "fx" in uid:
            continue
        for raw in tickers:
            t = str(raw).strip().upper()
            if "." not in t:
                continue
            country = None
            for suffix, iso in COUNTRY_FROM_TICKER_SUFFIX.items():
                if t.endswith(suffix):
                    country = iso
                    break
            if not country:
                if "idn" in uid:
                    country = "IDN"
                elif "taiwan" in uid:
                    country = "TWN"
                elif "korea" in uid:
                    country = "KOR"
                elif "japan" in uid:
                    country = "JPN"
                elif "china" in uid or "hk" in uid:
                    country = "CHN"
                elif "asean" in uid or "malesia" in uid or "malaysia" in uid:
                    # split by explicit suffix after we have parsed above
                    if t.endswith(".SI"):
                        country = "SGP"
                if not country and "hkg" in description:
                    country = "HKG"
            if country:
                ticker_map.setdefault(country, set()).add(t)
    return ticker_map


def _append_sourced_country_map(
    ticker_map: dict[str, set[str]],
    source_file: Path,
) -> None:
    if not source_file.exists():
        return
    try:
        df = pd.read_csv(source_file)
    except Exception:
        return
    if "yahoo_symbol" not in df.columns:
        return
    valid_col = "yfinance_valid_5d"
    valid_mask = True
    if valid_col in df.columns:
        valid_mask = df[valid_col].fillna(False).astype(str).str.lower().isin({"true", "1", "yes"})
    for row in df.loc[valid_mask].itertuples(index=False):
        symbol = str(getattr(row, "yahoo_symbol", "")).strip().upper()
        country_name = str(getattr(row, "country", "")).strip()
        country = COUNTRY_FROM_SOURCE_NAME.get(country_name)
        if not symbol or not country:
            continue
        ticker_map.setdefault(country, set()).add(symbol)


def _market_run_dir_or_file(market_root: Path, market_run: str) -> list[Path]:
    if market_run and (market_root / market_run).exists():
        target = market_root / market_run
        if target.is_dir():
            return [p for p in target.iterdir() if p.suffix.lower() in {".csv", ".parquet"}]
        if target.is_file():
            return [target]
    # Try latest run dir under root.
    if market_root.is_dir():
        latest = _latest_subdir(market_root)
        return [p for p in latest.iterdir() if p.suffix.lower() in {".csv", ".parquet"}]
    raise FileNotFoundError(f"Market run not found: {market_run} under {market_root}")


def _read_market_files(files: list[Path], tickers: set[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    wanted = {t for t in tickers if t}
    for p in sorted(files):
        if not p.is_file():
            continue
        try:
            if p.suffix.lower() == ".csv":
                df = pd.read_csv(p)
            else:
                df = pd.read_parquet(p)
        except Exception:
            continue
        if "instrument" not in df.columns:
            continue
        keep = df["instrument"].astype(str).str.upper().isin(wanted)
        if not keep.any():
            continue
        sub = df.loc[keep].copy()
        if "date" not in sub.columns:
            continue
        sub["instrument"] = sub["instrument"].astype(str).str.upper()
        sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
        sub = sub.dropna(subset=["date", "instrument"])
        for col in ["open", "high", "low", "close", "adj_close", "volume"]:
            if col in sub.columns:
                sub[col] = pd.to_numeric(sub[col], errors="coerce")
        sub["price"] = sub["adj_close"].where(sub["adj_close"].gt(0), sub.get("close"))
        frames.append(sub)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return out[["instrument", "date", "price", "adj_close", "volume"]].dropna(subset=["date"])


def _compute_price_features(df: pd.DataFrame, min_points: int) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["instrument", "as_of_date", "as_of_price", "ret_21d", "ret_63d", "vol_20d", "vol_60d", "liq_20d"])

    rows: list[dict[str, float | str | int | None]] = []
    grouped = df.sort_values(["instrument", "date"]).groupby("instrument")
    for t, g in grouped:
        g = g.copy().sort_values("date").reset_index(drop=True)
        if len(g) < min_points:
            continue
        g = g.dropna(subset=["price"]).sort_values("date").reset_index(drop=True)
        g["ret_1d"] = g["price"].pct_change()
        latest = g.iloc[-1]
        for name, window in LOOKBACK_WINDOWS.items():
            if name.startswith("ret_"):
                g[name] = g["price"].pct_change(window)
            else:
                g[name] = g["ret_1d"].rolling(window).std(ddof=1) * (252.0 ** 0.5)
        rows.append(
            {
                "instrument": t,
                "as_of_date": pd.Timestamp(latest["date"]).strftime("%Y-%m-%d"),
                "as_of_price": float(latest["price"]) if pd.notna(latest["price"]) else np.nan,
                "volume_20d": float(g["volume"].tail(20).mean()) if g["volume"].notna().any() else np.nan,
                "ret_21d": float(g["ret_21d"].iloc[-1]) if "ret_21d" in g.columns else np.nan,
                "ret_63d": float(g["ret_63d"].iloc[-1]) if "ret_63d" in g.columns else np.nan,
                "vol_20d": float(g["vol_20d"].iloc[-1]) if "vol_20d" in g.columns else np.nan,
                "vol_60d": float(g["vol_60d"].iloc[-1]) if "vol_60d" in g.columns else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out

    for c in ["ret_21d", "ret_63d", "vol_20d", "vol_60d", "volume_20d"]:
        den = float(out[c].std(ddof=0))
        out[f"z_{c}"] = (out[c] - out[c].mean()) / den if den else 0.0
    out["volume_rank"] = out["volume_20d"].rank(pct=True)
    out = out.sort_values("volume_rank", ascending=False)
    return out


def _zscore(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    med = s.median()
    mad = s.sub(med).abs().median()
    if not np.isfinite(mad) or mad == 0:
        return pd.Series(0.0, index=s.index)
    return (s - med) / (mad * 1.4826)


def _build_signal_context(preds: pd.DataFrame, asof: str | None, pred_col: str) -> dict[str, SignalContext]:
    d = preds.copy()
    if asof:
        asof_ts = pd.Timestamp(asof)
        if pd.isna(asof_ts):
            asof_ts = d["week_end"].max()
    else:
        asof_ts = d["week_end"].max()

    d = d[d["week_end"] <= asof_ts]
    if d.empty:
        raise ValueError("No prediction rows on or before as_of date.")
    latest_week = d["week_end"].max()
    latest_rows = d[d["week_end"] == latest_week][["country_iso3", pred_col, "fwd_return_1w", "risk_score"]].copy()
    latest_rows[pred_col] = pd.to_numeric(latest_rows[pred_col], errors="coerce")
    latest_rows["risk_score"] = pd.to_numeric(latest_rows["risk_score"], errors="coerce").fillna(0.0)
    latest_rows = latest_rows.dropna(subset=[pred_col])

    if latest_rows.empty:
        # use latest non-null row across all countries as fallback
        latest_rows = d.groupby("country_iso3")[pred_col].last().reset_index()
        latest_rows.columns = ["country_iso3", pred_col]
        latest_rows["fwd_return_1w"] = d.groupby("country_iso3")["fwd_return_1w"].last().values
        latest_rows["risk_score"] = d.groupby("country_iso3")["risk_score"].last().values

    return {
        r["country_iso3"]: SignalContext(
            country_iso3=str(r["country_iso3"]),
            as_of=str(latest_week.date()),
            prediction_col=pred_col,
            pred_value=float(r[pred_col]),
            target_value=float(r["fwd_return_1w"]) if pd.notna(r.get("fwd_return_1w", np.nan)) else float("nan"),
            risk_score=float(r["risk_score"]) if pd.notna(r.get("risk_score", np.nan)) else 0.0,
            source="model_walkforward",
        )
        for _, r in latest_rows.iterrows()
    }


def _country_ticker_map(
    config_path: Path,
    include_country_only: bool,
    sourced_file: Path,
) -> dict[str, set[str]]:
    m = _load_country_map_from_universes(config_path)
    if not include_country_only:
        _append_sourced_country_map(m, sourced_file)
    return m


def _build_ticker_signal_panel(
    ticker_map: dict[str, set[str]],
    price_features: pd.DataFrame,
    signal_context: dict[str, SignalContext],
    min_liq_rank: float,
) -> pd.DataFrame:
    if price_features.empty:
        return pd.DataFrame(columns=["instrument"])
    panel = price_features.copy()
    # Attach country by suffix fallback.
    panel["country_iso3"] = panel["instrument"].map(
        lambda t: next((iso for suff, iso in COUNTRY_FROM_TICKER_SUFFIX.items() if str(t).endswith(suff)), "")
    )
    # enforce mapping overrides from universe map for better control
    inverse = {t: iso for iso, tickers in ticker_map.items() for t in tickers}
    panel["country_iso3"] = panel["instrument"].map(inverse).fillna(panel["country_iso3"])
    panel = panel[panel["country_iso3"].astype(bool)]
    panel["country_iso3"] = panel["country_iso3"].astype(str).str.upper()

    ctx_rows = [
        {
            "country_iso3": c,
            "country_pred": v.pred_value,
            "country_fwd_target": v.target_value,
            "country_risk_score": v.risk_score,
            "signal_as_of": v.as_of,
            "signal_source": v.source,
        }
        for c, v in signal_context.items()
    ]
    ctx_df = pd.DataFrame(ctx_rows)
    panel = panel.merge(ctx_df, on="country_iso3", how="left")
    panel = panel.dropna(subset=["country_pred"])

    # keep top liquidity names; helps avoid stale/illiquid symbols.
    if "volume_rank" not in panel.columns:
        panel["volume_rank"] = 0.5
    panel = panel.sort_values("volume_rank", ascending=False).copy()
    if 0 < min_liq_rank < 1:
        cutoff = panel["volume_rank"].quantile(1 - min_liq_rank)
        panel = panel[panel["volume_rank"] >= cutoff]

    for c in ["country_pred", "country_fwd_target", "country_risk_score", "ret_21d", "ret_63d", "vol_20d", "vol_60d"]:
        panel[c] = pd.to_numeric(panel[c], errors="coerce")

    panel["pred_z"] = _zscore(panel["country_pred"])
    panel["fwd_target_z"] = _zscore(panel["country_fwd_target"])
    panel["risk_z"] = -_zscore(panel["country_risk_score"])  # lower risk preferred
    panel["ret21_z"] = _zscore(panel["ret_21d"])
    panel["ret63_z"] = _zscore(panel["ret_63d"])
    panel["vol20_z"] = -_zscore(panel["vol_20d"])
    panel["vol60_z"] = -_zscore(panel["vol_60d"])
    panel["liq_z"] = _zscore(panel["volume_rank"])

    # Conservative composite:
    panel["ticker_score_long"] = (
        0.55 * panel["pred_z"]
        + 0.12 * panel["fwd_target_z"]
        + 0.10 * panel["ret21_z"]
        + 0.08 * panel["ret63_z"]
        + 0.07 * panel["liq_z"]
        + 0.08 * panel["risk_z"]
    )
    panel["ticker_score_short"] = (
        -0.55 * panel["pred_z"]
        - 0.12 * panel["fwd_target_z"]
        - 0.10 * panel["ret21_z"]
        + 0.10 * panel["vol20_z"]
        + 0.08 * panel["risk_z"]
    )
    return panel


def write_readme(out_dir: Path, summary: dict[str, object]) -> None:
    lines = [
        "# Asia News Market Ticker Watchlist",
        "",
        f"- Built UTC: `{summary['built_at_utc']}`",
        f"- Signal date (`as_of`): `{summary['as_of']}`",
        f"- Data source: `{summary['model_run']}`",
        f"- Tickers ranked: `{summary['n_tickers']}`",
        f"- Countries covered: `{', '.join(summary['countries'])}`",
        f"- Long watchlist top-N: `{summary['top_n']}`",
        f"- Short watchlist top-N: `{summary['top_n']}`",
        "",
        "## Output files",
        "- `ticker_signal_panel.csv`: ticker-level feature panel used for ranking.",
        "- `watchlist_long_tickers.csv`: long candidates (highest `ticker_score_long`).",
        "- `watchlist_short_tickers.csv`: short candidates (highest `ticker_score_short`).",
        "- `summary.json`: run metadata and fingerprints.",
        "",
        "## Interpretation",
        "- This is screening output for research only.",
        "- `country_pred` is mapped from the latest available country-level walk-forward signal.",
        "- `ticker_score_long` and `ticker_score_short` are heuristic composites,",
        "  not direct trading predictions.",
        "- `min_liquidity_rank` is used to filter stale/illiquid symbols from the panel.",
        "- Next step should be cross-checking these watchlists against independent signals (news volume,",
        "  corporate actions, and event calendars) before any capital allocation.",
    ]
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    preds = _load_prediction_frame(args.model_root, args.model_run, args.prediction_col, args.target)
    ctx = _build_signal_context(preds, args.asof or None, args.prediction_col)

    symbol_map = _country_ticker_map(args.country_config, args.include_country_only, args.sourced_mapped_file)
    # keep only countries that have predictions
    symbol_map = {c: sorted(t for t in v if t) for c, v in symbol_map.items() if c in ctx}
    all_tickers = sorted({t for v in symbol_map.values() for t in v})

    market_files = _market_run_dir_or_file(args.market_root, args.market_run)
    market = _read_market_files(market_files, set(all_tickers))
    features = _compute_price_features(market, min_points=args.min_data_points)
    panel = _build_ticker_signal_panel(symbol_map, features, ctx, args.min_volume_rank)

    if panel.empty:
        summary = {
            "built_at_utc": datetime.now(UTC).isoformat(),
            "run_id": run_id,
            "as_of": args.asof or "",
            "model_run": str(args.model_run or "latest"),
            "message": "No tickers passed all filters; check model/market coverage.",
            "n_tickers": 0,
            "countries": sorted(ctx.keys()),
            "top_n": int(args.top),
            "min_data_points": int(args.min_data_points),
            "min_liquidity_rank": float(args.min_volume_rank),
        }
        write_readme(out_dir, summary)
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        (out_dir / "ticker_signal_panel.csv").write_text("instrument\n")
        (out_dir / "watchlist_long_tickers.csv").write_text("instrument\n")
        (out_dir / "watchlist_short_tickers.csv").write_text("instrument\n")
        print(json.dumps(summary, indent=2))
        return 0

    panel = panel.sort_values("ticker_score_long", ascending=False).reset_index(drop=True)
    long_list = panel.head(int(args.top)).copy()
    short_list = panel.sort_values("ticker_score_short", ascending=False).head(int(args.top)).copy()

    panel["score_rank_long"] = panel["ticker_score_long"].rank(ascending=False, method="dense").astype("int64")
    panel["score_rank_short"] = panel["ticker_score_short"].rank(ascending=False, method="dense").astype("int64")
    panel.to_csv(out_dir / "ticker_signal_panel.csv", index=False)
    long_list.to_csv(out_dir / "watchlist_long_tickers.csv", index=False)
    short_list.to_csv(out_dir / "watchlist_short_tickers.csv", index=False)

    summary = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "as_of": panel["signal_as_of"].iloc[0] if "signal_as_of" in panel.columns and not panel.empty else str(args.asof or ""),
        "model_run": str(args.model_run or "latest"),
        "model_panel_file": str(args.panel_file),
        "prediction_col": str(args.prediction_col),
        "target": str(args.target),
        "n_tickers": int(len(panel)),
        "n_ticker_by_country": {c: int(len(v)) for c, v in symbol_map.items()},
        "n_tickers_long": int(len(long_list)),
        "n_tickers_short": int(len(short_list)),
        "countries": sorted(ctx.keys()),
        "top_n": int(args.top),
        "min_data_points": int(args.min_data_points),
        "min_liquidity_rank": float(args.min_volume_rank),
        "outputs": {
            "ticker_signal_panel": str(out_dir / "ticker_signal_panel.csv"),
            "watchlist_long": str(out_dir / "watchlist_long_tickers.csv"),
            "watchlist_short": str(out_dir / "watchlist_short_tickers.csv"),
            "summary": str(out_dir / "summary.json"),
            "readme": str(out_dir / "README.md"),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_readme(out_dir, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
