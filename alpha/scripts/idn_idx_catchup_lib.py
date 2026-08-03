"""Backfill IDX legacy SQLite from Yahoo Finance after local DB ends."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
IDX_LEGACY_DB = REPO / "data_lake/markets/idx_legacy_restore/historical_data.db"
CATCHUP_MANIFEST = REPO / "data_lake/markets/idx_legacy_restore/catchup_manifest.json"
IDX_ALL_PANEL = REPO / "data_lake/markets/yfinance_asia/idn_idx_all_daily_panel.parquet"

DEFAULT_BATCH_SIZE = 24
DEFAULT_SLEEP_S = 0.75


def _flatten_yf_frame(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    sub = raw.copy()
    if isinstance(sub.columns, pd.MultiIndex):
        try:
            if ticker in set(str(x) for x in sub.columns.get_level_values(0)):
                sub = sub.xs(ticker, axis=1, level=0, drop_level=True)
            elif ticker in set(str(x) for x in sub.columns.get_level_values(1)):
                sub = sub.xs(ticker, axis=1, level=1, drop_level=True)
            else:
                return pd.DataFrame()
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
            "timestamp": pd.to_datetime(sub[date_col], errors="coerce").dt.tz_localize(None),
            "open": pd.to_numeric(col("Open"), errors="coerce"),
            "high": pd.to_numeric(col("High"), errors="coerce"),
            "low": pd.to_numeric(col("Low"), errors="coerce"),
            "close": pd.to_numeric(col("Close"), errors="coerce"),
            "volume": pd.to_numeric(col("Volume"), errors="coerce"),
        }
    )
    return out.dropna(subset=["timestamp", "close"])


def symbol_latest_dates(db_path: Path | None = None) -> dict[str, pd.Timestamp]:
    p = db_path or IDX_LEGACY_DB
    if not p.exists():
        return {}
    with sqlite3.connect(p) as conn:
        df = pd.read_sql(
            "SELECT symbol, MAX(timestamp) AS max_ts FROM historical_data_daily GROUP BY symbol",
            conn,
            parse_dates=["max_ts"],
        )
    return {str(r.symbol): pd.Timestamp(r.max_ts) for r in df.itertuples(index=False)}


def global_latest_date(db_path: Path | None = None) -> pd.Timestamp | None:
    latest = symbol_latest_dates(db_path)
    if not latest:
        return None
    return max(latest.values())


def download_range(
    symbols: list[str],
    start: str,
    end: str,
) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    if not symbols:
        return {}
    try:
        raw = yf.download(
            symbols,
            start=start,
            end=end,
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            threads=True,
            progress=False,
        )
    except Exception:
        return {}

    out: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        frame = _flatten_yf_frame(raw, sym)
        if not frame.empty:
            out[sym] = frame
    return out


def upsert_daily_rows(
    symbol: str,
    frame: pd.DataFrame,
    *,
    db_path: Path | None = None,
    min_start: pd.Timestamp | None = None,
) -> int:
    p = db_path or IDX_LEGACY_DB
    if frame.empty:
        return 0
    rows = frame.copy()
    if min_start is not None:
        rows = rows[rows["timestamp"] > min_start]
    if rows.empty:
        return 0

    payload = [
        (
            symbol,
            ts.strftime("%Y-%m-%d"),
            float(o) if pd.notna(o) else None,
            float(h) if pd.notna(h) else None,
            float(l) if pd.notna(l) else None,
            float(c) if pd.notna(c) else None,
            float(v) if pd.notna(v) else None,
        )
        for ts, o, h, l, c, v in zip(
            rows["timestamp"],
            rows["open"],
            rows["high"],
            rows["low"],
            rows["close"],
            rows["volume"],
            strict=True,
        )
    ]
    with sqlite3.connect(p) as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO historical_data_daily
            (symbol, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        conn.commit()
    return len(payload)


def catchup_symbols(
    symbols: list[str],
    *,
    db_path: Path | None = None,
    end: datetime | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_s: float = DEFAULT_SLEEP_S,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Download Yahoo daily bars after each symbol's DB max date through end (exclusive)."""
    from idn_name_type_lib import load_idx_all_universe

    p = db_path or IDX_LEGACY_DB
    if not p.exists():
        raise FileNotFoundError(p)

    universe = symbols or load_idx_all_universe()
    latest = symbol_latest_dates(p)
    end_dt = (end or datetime.now(UTC)).date() + timedelta(days=1)
    end_s = end_dt.isoformat()

    # Group by start date for efficient batch downloads
    groups: dict[str, list[str]] = {}
    skipped: list[str] = []
    for sym in universe:
        max_ts = latest.get(sym)
        if max_ts is None:
            start = (datetime.now(UTC).date() - timedelta(days=365 * 5)).isoformat()
        else:
            if max_ts.date() >= end_dt - timedelta(days=1):
                skipped.append(sym)
                continue
            start = (max_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        groups.setdefault(start, []).append(sym)

    results = {
        "started_at_utc": datetime.now(UTC).isoformat(),
        "end_exclusive": end_s,
        "n_universe": len(universe),
        "n_skipped_up_to_date": len(skipped),
        "n_groups": len(groups),
        "rows_inserted": 0,
        "symbols_updated": 0,
        "symbols_failed": [],
        "symbols_empty": [],
        "dry_run": dry_run,
    }

    if dry_run:
        results["groups"] = {k: len(v) for k, v in groups.items()}
        return results

    for start, batch_group in sorted(groups.items()):
        for i in range(0, len(batch_group), batch_size):
            chunk = batch_group[i : i + batch_size]
            frames = download_range(chunk, start, end_s)
            for sym in chunk:
                frame = frames.get(sym)
                if frame is None or frame.empty:
                    results["symbols_empty"].append(sym)
                    continue
                min_start = latest.get(sym)
                n = upsert_daily_rows(sym, frame, db_path=p, min_start=min_start)
                if n > 0:
                    results["rows_inserted"] += n
                    results["symbols_updated"] += 1
                else:
                    results["symbols_empty"].append(sym)
            if sleep_s > 0:
                time.sleep(sleep_s)

    results["finished_at_utc"] = datetime.now(UTC).isoformat()
    results["global_max_after"] = str(global_latest_date(p).date()) if global_latest_date(p) else None
    CATCHUP_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    CATCHUP_MANIFEST.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def export_all_daily_panel(
    *,
    db_path: Path | None = None,
    out_path: Path | None = None,
    min_date: str | None = None,
) -> Path:
    """Export merged legacy+catchup SQLite table to long parquet panel."""
    from idn_name_type_lib import load_idx_legacy_close_volume

    p = db_path or IDX_LEGACY_DB
    symbols = list(symbol_latest_dates(p).keys())
    close, vol = load_idx_legacy_close_volume(symbols, min_date=min_date)
    if close.empty:
        raise FileNotFoundError(f"No rows to export from {p}")

    parts: list[pd.DataFrame] = []
    for sym in close.columns:
        df = pd.DataFrame(
            {
                "close": close[sym],
                "volume": vol[sym] if sym in vol.columns else pd.NA,
            }
        ).dropna(subset=["close"])
        df["symbol"] = sym
        parts.append(df.reset_index(names="date"))

    panel = pd.concat(parts, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel.set_index(["date", "symbol"]).sort_index()
    out = out_path or IDX_ALL_PANEL
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out)
    return out
