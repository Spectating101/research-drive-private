"""Disk-backed caches for heavy IDN research panels (GDELT entity, bandar-lite)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)

CACHE_DIR = REPO / "data_lake/cache"
ENTITY_SOURCE = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/daily_ticker_entity_shock_panel.parquet"
BANDAR_SOURCE = REPO / "data_lake/research_panels/idn_fry_episode/daily_cross_section.parquet"
ENTITY_IDN_CACHE = CACHE_DIR / "gdelt_entity_daily_idn.parquet"
BANDAR_LITE_CACHE = CACHE_DIR / "idn_bandar_lite_latest.parquet"


def _write_meta(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_meta(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _cache_fresh(
    cache_path: Path,
    meta_path: Path,
    source_path: Path,
    *,
    max_age_hours: float,
) -> bool:
    if not cache_path.exists() or not meta_path.exists():
        return False
    meta = _read_meta(meta_path) or {}
    built = float(meta.get("built_at_unix", 0))
    if (time.time() - built) > float(max_age_hours) * 3600.0:
        return False
    if source_path.exists():
        return int(meta.get("source_mtime_ns", -1)) == source_path.stat().st_mtime_ns
    return True


def refresh_entity_idn_cache(*, force: bool = False, max_age_hours: float = 24.0) -> Path:
    """Build .JK-only subset of GDELT entity daily panel."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = CACHE_DIR / "gdelt_entity_daily_idn.meta.json"
    if not force and _cache_fresh(ENTITY_IDN_CACHE, meta_path, ENTITY_SOURCE, max_age_hours=max_age_hours):
        return ENTITY_IDN_CACHE
    if not ENTITY_SOURCE.exists():
        raise FileNotFoundError(f"missing entity source: {ENTITY_SOURCE}")

    df = pd.read_parquet(ENTITY_SOURCE)
    if "yahoo_symbol" not in df.columns:
        raise ValueError("entity panel missing yahoo_symbol")
    df = df[df["yahoo_symbol"].astype(str).str.endswith(".JK")].copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df.to_parquet(ENTITY_IDN_CACHE, index=False)
    _write_meta(
        meta_path,
        {
            "built_at_unix": time.time(),
            "source": str(ENTITY_SOURCE),
            "source_mtime_ns": ENTITY_SOURCE.stat().st_mtime_ns,
            "n_rows": int(len(df)),
            "n_symbols": int(df["yahoo_symbol"].nunique()) if not df.empty else 0,
        },
    )
    return ENTITY_IDN_CACHE


def load_entity_idn_daily(*, max_age_hours: float = 24.0, force_refresh: bool = False) -> pd.DataFrame:
    """Cached .JK entity panel; rebuilds at most once per TTL or source change."""
    try:
        refresh_entity_idn_cache(force=force_refresh, max_age_hours=max_age_hours)
    except FileNotFoundError:
        return pd.DataFrame()
    if not ENTITY_IDN_CACHE.exists():
        return pd.DataFrame()
    return pd.read_parquet(ENTITY_IDN_CACHE)


def refresh_bandar_lite_snapshot(
    as_of: str | pd.Timestamp | None = None,
    *,
    force: bool = False,
    max_age_hours: float = 6.0,
) -> Path:
    """Latest bandar_lite_label per .JK symbol on or before as_of."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else None
    meta_path = CACHE_DIR / "idn_bandar_lite_latest.meta.json"
    cache_key = str(as_of_ts.date()) if as_of_ts is not None else "latest"
    if (
        not force
        and _cache_fresh(BANDAR_LITE_CACHE, meta_path, BANDAR_SOURCE, max_age_hours=max_age_hours)
        and (_read_meta(meta_path) or {}).get("as_of_key") == cache_key
    ):
        return BANDAR_LITE_CACHE
    if not BANDAR_SOURCE.exists():
        raise FileNotFoundError(f"missing bandar source: {BANDAR_SOURCE}")

    cs = pd.read_parquet(BANDAR_SOURCE, columns=["date", "yahoo_symbol", "bandar_lite_label"])
    cs = cs[cs["yahoo_symbol"].astype(str).str.endswith(".JK")].copy()
    cs["date"] = pd.to_datetime(cs["date"], errors="coerce")
    if as_of_ts is not None:
        cs = cs[cs["date"] <= as_of_ts]
    snap = cs.sort_values("date").groupby("yahoo_symbol", as_index=False).tail(1)
    snap.to_parquet(BANDAR_LITE_CACHE, index=False)
    _write_meta(
        meta_path,
        {
            "built_at_unix": time.time(),
            "as_of_key": cache_key,
            "as_of": str(as_of_ts.date()) if as_of_ts is not None else None,
            "source": str(BANDAR_SOURCE),
            "source_mtime_ns": BANDAR_SOURCE.stat().st_mtime_ns,
            "n_symbols": int(len(snap)),
            "max_date": str(snap["date"].max().date()) if not snap.empty else None,
        },
    )
    return BANDAR_LITE_CACHE


def load_bandar_lite_snapshot(
    as_of: str | pd.Timestamp | None = None,
    *,
    max_age_hours: float = 6.0,
    force_refresh: bool = False,
) -> pd.DataFrame:
    try:
        refresh_bandar_lite_snapshot(as_of, force=force_refresh, max_age_hours=max_age_hours)
    except FileNotFoundError:
        return pd.DataFrame()
    if not BANDAR_LITE_CACHE.exists():
        return pd.DataFrame()
    return pd.read_parquet(BANDAR_LITE_CACHE)


def bandar_lite_map_for_symbols(
    symbols: list[str],
    as_of: str | pd.Timestamp,
    *,
    max_age_hours: float = 6.0,
) -> dict[str, str]:
    snap = load_bandar_lite_snapshot(as_of, max_age_hours=max_age_hours)
    if snap.empty:
        return {s: "unclear" for s in symbols}
    m = snap.set_index("yahoo_symbol")["bandar_lite_label"].astype(str).to_dict()
    return {s: m.get(s, "unclear") for s in symbols}
