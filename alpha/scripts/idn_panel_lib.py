"""IDX daily OHLCV panels — full exchange + liquid Yahoo overlay."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
IDX_ALL_PANEL = REPO / "data_lake/markets/yfinance_asia/idn_idx_all_daily_panel.parquet"
IDX_LIQUID_PANEL = REPO / "data_lake/markets/yfinance_asia/idn_liquid_daily_panel.parquet"
TRADABLE_MIN_ROWS = 252
TRADABLE_MIN_END = pd.Timestamp("2026-06-01")
PANEL_START_DEFAULT = "2022-01-01"


def _read_long_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.MultiIndex):
        if "date" in df.columns and "symbol" in df.columns:
            df = df.set_index(["date", "symbol"])
    df = df.sort_index()
    df.index.names = ["date", "symbol"]
    return df


def load_merged_long_panel(*, min_date: str | None = PANEL_START_DEFAULT) -> pd.DataFrame:
    """Full legacy/catchup panel overlaid with liquid Yahoo (newer dates + new listings)."""
    base = _read_long_panel(IDX_ALL_PANEL)
    overlay = _read_long_panel(IDX_LIQUID_PANEL)
    if base.empty and overlay.empty:
        return pd.DataFrame()
    if base.empty:
        merged = overlay
    elif overlay.empty:
        merged = base
    else:
        merged = pd.concat([base, overlay]).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]

    if min_date:
        d = pd.to_datetime(merged.index.get_level_values("date"))
        merged = merged[d >= pd.Timestamp(min_date)]
    return merged


def load_idx_close_volume(
    symbols: list[str] | None = None,
    *,
    min_date: str | None = PANEL_START_DEFAULT,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    long = load_merged_long_panel(min_date=min_date)
    if long.empty:
        return pd.DataFrame(), pd.DataFrame()
    if symbols:
        syms = set(symbols)
        mask = long.index.get_level_values("symbol").isin(syms)
        long = long[mask]
    close = long["close"].unstack("symbol").sort_index()
    vol = long["volume"].unstack("symbol").sort_index() if "volume" in long.columns else pd.DataFrame()
    return close, vol


def resolve_tradable_universe(
    *,
    min_rows: int = TRADABLE_MIN_ROWS,
    min_end: pd.Timestamp = TRADABLE_MIN_END,
    min_date: str | None = PANEL_START_DEFAULT,
) -> list[str]:
    """Symbols with enough post-2022 history and recent data (full exchange + liquid overlay)."""
    long = load_merged_long_panel(min_date=min_date)
    if long.empty:
        return []
    df = long.reset_index()
    df["date"] = pd.to_datetime(df["date"])
    g = df.groupby("symbol").agg(n=("close", "count"), dmax=("date", "max"))
    ok = g[(g["n"] >= min_rows) & (g["dmax"] >= min_end)]
    return sorted(ok.index.astype(str).tolist())


def load_research_universe(*, mode: str = "tradable") -> list[str]:
    """Research universe from panel history — not static config lists."""
    mode = (mode or "tradable").strip().lower()
    if mode == "tradable":
        return resolve_tradable_universe()
    if mode == "merged":
        long = load_merged_long_panel(min_date=None)
        if long.empty:
            return []
        return sorted(long.index.get_level_values("symbol").astype(str).unique().tolist())
    if mode == "liquid":
        # Prefer the curated liquid parquet (full liquid-50), not bank-only liquid_core.
        if IDX_LIQUID_PANEL.exists():
            long = _read_long_panel(IDX_LIQUID_PANEL)
            if not long.empty:
                return sorted(long.index.get_level_values("symbol").astype(str).unique().tolist())
        close, vol, tradable = load_idx_panel_for_universe(mode="tradable", min_date="2022-01-01")
        if close.empty:
            return []
        from idn_name_type_lib import liquid_core_symbols

        core = liquid_core_symbols(close.pct_change(), vol, close=close)
        return core or tradable[: min(50, len(tradable))]
    raise ValueError(f"unknown universe mode {mode!r}; use liquid|tradable|merged")


def load_idx_panel_for_universe(
    symbols: list[str] | None = None,
    *,
    mode: str = "tradable",
    min_date: str | None = "2019-07-01",
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Daily close/volume wide panels from local idx_all + liquid overlay."""
    syms = symbols or load_research_universe(mode=mode)
    close, vol = load_idx_close_volume(syms, min_date=min_date)
    use = [s for s in syms if s in close.columns]
    if not use:
        return pd.DataFrame(), pd.DataFrame(), []
    c = close[use].sort_index()
    v = vol[use].sort_index() if not vol.empty else pd.DataFrame(index=c.index, columns=use)
    return c, v, use


def panel_manifest() -> dict:
    tradable = resolve_tradable_universe()
    long = load_merged_long_panel()
    dates = pd.to_datetime(long.index.get_level_values("date"))
    return {
        "idx_all_panel": str(IDX_ALL_PANEL),
        "idx_liquid_panel": str(IDX_LIQUID_PANEL),
        "n_symbols_merged": int(long.index.get_level_values("symbol").nunique()) if not long.empty else 0,
        "n_tradable": len(tradable),
        "date_min": str(dates.min().date()) if len(dates) else None,
        "date_max": str(dates.max().date()) if len(dates) else None,
    }
