#!/usr/bin/env python3
"""
Fetch credential-free market universes from Yahoo Finance.

This is the broad daily market layer for Sharpe-Renaissance. It writes one file
per universe plus a manifest, using a consistent OHLCV schema:

  source, universe, instrument, date, open, high, low, close, adj_close, volume

Yahoo/yfinance is useful for accessible research coverage, but it is not a
replacement for Refinitiv/WRDS when we need survivorship-safe, audit-grade data.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class Universe:
    universe_id: str
    description: str
    tickers: list[str]


def _read_ticker_file(path: Path) -> list[str]:
    tickers: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        tickers.append(line.split()[0].strip())
    return tickers


def _dedupe(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        t = item.strip()
        if not t or t in seen:
            continue
        out.append(t)
        seen.add(t)
    return out


def load_universes(config_path: Path, only: set[str] | None = None) -> list[Universe]:
    cfg = json.loads(config_path.read_text())
    base = config_path.resolve().parents[2] if config_path.parts[-3:-1] == ("config", "markets") else Path.cwd()
    universes: list[Universe] = []
    for raw in cfg.get("universes", []):
        uid = str(raw["id"])
        if only and uid not in only:
            continue
        tickers: list[str] = []
        tickers.extend(str(x) for x in raw.get("tickers", []))
        if raw.get("tickers_file"):
            tf = Path(raw["tickers_file"])
            if not tf.is_absolute():
                tf = base / tf
            tickers.extend(_read_ticker_file(tf))
        universes.append(
            Universe(
                universe_id=uid,
                description=str(raw.get("description", "")),
                tickers=_dedupe(tickers),
            )
        )
    return universes


def _flatten_single_ticker(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    sub = df.copy()
    if isinstance(sub.columns, pd.MultiIndex):
        try:
            if ticker in set(str(x) for x in sub.columns.get_level_values(0)):
                sub = sub.xs(ticker, axis=1, level=0, drop_level=True)
            elif ticker in set(str(x) for x in sub.columns.get_level_values(1)):
                sub = sub.xs(ticker, axis=1, level=1, drop_level=True)
        except Exception:
            return pd.DataFrame()
    sub = sub.reset_index()
    date_col = "Date" if "Date" in sub.columns else ("Datetime" if "Datetime" in sub.columns else None)
    if date_col is None or "Close" not in sub.columns:
        return pd.DataFrame()

    def col(name: str) -> pd.Series:
        if name not in sub.columns:
            return pd.Series([pd.NA] * len(sub))
        s = sub[name]
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        return s

    out = pd.DataFrame(
        {
            "instrument": ticker,
            "date": pd.to_datetime(sub[date_col], errors="coerce").dt.date.astype("string"),
            "open": pd.to_numeric(col("Open"), errors="coerce"),
            "high": pd.to_numeric(col("High"), errors="coerce"),
            "low": pd.to_numeric(col("Low"), errors="coerce"),
            "close": pd.to_numeric(col("Close"), errors="coerce"),
            "adj_close": pd.to_numeric(col("Adj Close"), errors="coerce"),
            "volume": pd.to_numeric(col("Volume"), errors="coerce"),
        }
    )
    return out.dropna(subset=["date", "close"])


def fetch_batch(tickers: list[str], period: str, interval: str) -> tuple[pd.DataFrame, list[str]]:
    import yfinance as yf

    try:
        raw = yf.download(
            tickers,
            period=period,
            interval=interval,
            auto_adjust=False,
            group_by="ticker",
            threads=True,
            progress=False,
        )
    except Exception:
        return pd.DataFrame(), tickers

    frames: list[pd.DataFrame] = []
    failed: list[str] = []
    if raw is None or raw.empty:
        return pd.DataFrame(), tickers

    for ticker in tickers:
        frame = _flatten_single_ticker(raw, ticker)
        if frame.empty:
            failed.append(ticker)
        else:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(), failed or tickers
    return pd.concat(frames, ignore_index=True), failed


def write_panel(df: pd.DataFrame, out_base: Path, write_parquet: bool) -> tuple[Path, Path | None]:
    csv_path = out_base.with_suffix(".csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    parquet_path: Path | None = None
    if write_parquet:
        parquet_path = out_base.with_suffix(".parquet")
        try:
            df.to_parquet(parquet_path, index=False)
        except Exception:
            parquet_path = None
    return csv_path, parquet_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch accessible yfinance market universes.")
    ap.add_argument("--config", type=Path, default=Path("config/markets/accessible_yfinance_universes.json"))
    ap.add_argument("--out-root", type=Path, default=Path("data_lake/markets/yfinance_accessible"))
    ap.add_argument("--period", default="10y")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--only", nargs="*", default=[], help="Universe ids to run. Default: all.")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--write-parquet", action="store_true")
    ap.add_argument("--max-tickers-per-universe", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out_root / run_id
    only = set(args.only) if args.only else None
    universes = load_universes(args.config, only=only)

    if args.dry_run:
        for u in universes:
            print(f"{u.universe_id}: {len(u.tickers)} tickers")
        return 0

    manifest_rows: list[dict[str, object]] = []
    error_rows: list[dict[str, str]] = []
    for u in universes:
        tickers = u.tickers[: args.max_tickers_per_universe] if args.max_tickers_per_universe else u.tickers
        frames: list[pd.DataFrame] = []
        failed_all: list[str] = []
        print(f"== {u.universe_id}: {len(tickers)} tickers ==")
        for i in range(0, len(tickers), max(1, args.batch_size)):
            batch = tickers[i : i + max(1, args.batch_size)]
            df, failed = fetch_batch(batch, args.period, args.interval)
            if not df.empty:
                df.insert(0, "universe", u.universe_id)
                df.insert(0, "source", "yfinance")
                frames.append(df)
            failed_all.extend(failed)
            ok_count = 0 if df.empty else df["instrument"].nunique()
            print(f"  batch {i}-{i + len(batch) - 1}: rows={len(df)} instruments={ok_count} failed={len(failed)}")
            if args.sleep:
                time.sleep(args.sleep)

        if frames:
            panel = pd.concat(frames, ignore_index=True)
            panel = panel.sort_values(["instrument", "date"]).reset_index(drop=True)
            csv_path, parquet_path = write_panel(panel, out_dir / u.universe_id, args.write_parquet)
            rows = int(len(panel))
            instruments = int(panel["instrument"].nunique())
            date_min = str(panel["date"].min())
            date_max = str(panel["date"].max())
        else:
            csv_path = out_dir / f"{u.universe_id}.csv"
            parquet_path = None
            rows = instruments = 0
            date_min = date_max = ""

        manifest_rows.append(
            {
                "run_id": run_id,
                "universe": u.universe_id,
                "description": u.description,
                "requested_tickers": len(tickers),
                "returned_instruments": instruments,
                "rows": rows,
                "date_min": date_min,
                "date_max": date_max,
                "csv_path": str(csv_path),
                "parquet_path": str(parquet_path or ""),
                "failed_tickers": len(_dedupe(failed_all)),
            }
        )
        for ticker in _dedupe(failed_all):
            error_rows.append({"run_id": run_id, "universe": u.universe_id, "ticker": ticker})

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.csv"
    with manifest_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()) if manifest_rows else ["run_id"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    errors_path = out_dir / "failed_tickers.csv"
    with errors_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["run_id", "universe", "ticker"])
        writer.writeheader()
        writer.writerows(error_rows)

    print(f"wrote manifest: {manifest_path}")
    print(f"wrote failed ticker list: {errors_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
