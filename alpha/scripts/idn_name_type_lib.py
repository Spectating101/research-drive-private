"""Data-driven IDX name typing: compounder vs fry vs standard.

Classifies symbols from trailing price/volume behavior (no ticker hardcodes).
Theme groups (e.g. barito_prajogo) only force fry — structural clusters, not picks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
GROUPS_CFG = REPO / "config/markets/indonesia_stock_groups.json"
UNIVERSE_CFG = REPO / "config/markets/asia_yfinance_universes.json"
IDX_TICKERS_FILE = REPO / "config/markets/indonesia_idx_legacy_all.tickers.txt"
IDX_LEGACY_DB = REPO / "data_lake/markets/idx_legacy_restore/historical_data.db"
SNAPSHOT_PATH = REPO / "data_lake/research_panels/idn_name_types/latest.json"
SNAPSHOT_UNIVERSE_ID = "indonesia_idx_legacy_all"

FRY_GROUP_KEYS = ("barito_prajogo",)
FRY_SPIKE_RATE_MIN = 2.0  # % of days with >= +10% move
FRY_SPIKE_RATE_MIN_GROUP = 0.5
COMPOUNDER_SPIKE_MAX = 1.0  # % — must stay below fry bar
COMPOUNDER_ADV_QUANTILE = 0.75
COMPOUNDER_VOL_QUANTILE = 0.60
METRICS_LOOKBACK = 252
METRICS_MIN_DAYS = 60
LIQUID_CORE_N = 3  # regime / bank-beta sleeve size


def _read_ticker_file(path: Path) -> list[str]:
    tickers: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split("#", 1)[0].strip()
        if line:
            tickers.append(line.split()[0].strip())
    return tickers


def load_idx_all_universe() -> list[str]:
    """All IDX symbols from config (648 legacy-restore list)."""
    if IDX_TICKERS_FILE.exists():
        return sorted(set(_read_ticker_file(IDX_TICKERS_FILE)))
    if not UNIVERSE_CFG.exists():
        return []
    cfg = json.loads(UNIVERSE_CFG.read_text(encoding="utf-8"))
    for u in cfg.get("universes", []):
        if u.get("id") == SNAPSHOT_UNIVERSE_ID and u.get("tickers_file"):
            tf = REPO / u["tickers_file"]
            if tf.exists():
                return sorted(set(_read_ticker_file(tf)))
    return []


def load_idx_legacy_close_volume(
    symbols: list[str] | None = None,
    *,
    min_date: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily close/volume matrices from local IDX legacy SQLite (full exchange list)."""
    import sqlite3

    if not IDX_LEGACY_DB.exists():
        return pd.DataFrame(), pd.DataFrame()

    where: list[str] = []
    params: list[Any] = []
    if min_date:
        where.append("timestamp >= ?")
        params.append(min_date)
    if symbols:
        where.append(f"symbol IN ({','.join('?' for _ in symbols)})")
        params.extend(symbols)
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    q = f"SELECT symbol, timestamp, close, volume FROM historical_data_daily{clause}"

    with sqlite3.connect(IDX_LEGACY_DB) as conn:
        df = pd.read_sql(q, conn, params=params, parse_dates=["timestamp"])
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = df.dropna(subset=["close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
    close = df.pivot_table(index="timestamp", columns="symbol", values="close", aggfunc="last").sort_index()
    vol = df.pivot_table(index="timestamp", columns="symbol", values="volume", aggfunc="last").sort_index()
    return close, vol


def load_name_type_snapshot(path: Path | None = None) -> dict[str, Any] | None:
    p = path or SNAPSHOT_PATH
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def name_type_map(snapshot: dict[str, Any] | None = None) -> dict[str, str]:
    snap = snapshot or load_name_type_snapshot()
    if not snap:
        return {}
    by_sym = snap.get("name_type_by_symbol")
    if by_sym:
        return dict(by_sym)
    return {row["symbol"]: row["name_type"] for row in snap.get("symbols", [])}


def compounder_set_from_snapshot(snapshot: dict[str, Any] | None = None) -> frozenset[str]:
    snap = snapshot or load_name_type_snapshot()
    if not snap:
        return frozenset()
    return frozenset(snap.get("compounder_symbols", []))


def liquid_core_from_snapshot(snapshot: dict[str, Any] | None = None) -> list[str]:
    snap = snapshot or load_name_type_snapshot()
    if not snap:
        return []
    return list(snap.get("liquid_core_symbols", []))


def ensure_full_universe_snapshot(*, force: bool = False) -> dict[str, Any]:
    """Build name-type snapshot on entire IDX ticker list if missing or stale."""
    snap = load_name_type_snapshot()
    if (
        not force
        and snap
        and snap.get("universe_id") == SNAPSHOT_UNIVERSE_ID
        and int(snap.get("n_symbols", 0)) >= len(load_idx_all_universe()) - 5
    ):
        return snap
    return refresh_full_universe_snapshot()


def refresh_full_universe_snapshot() -> dict[str, Any]:
    """Classify all IDX legacy symbols; thresholds computed on full exchange cross-section."""
    symbols = load_idx_all_universe()
    close, vol = load_idx_legacy_close_volume(symbols)
    if close.empty:
        raise FileNotFoundError(f"No IDX legacy panel in {IDX_LEGACY_DB}")

    snap = build_name_type_snapshot(close, vol)
    snap["universe_id"] = SNAPSHOT_UNIVERSE_ID
    snap["n_symbols"] = int(len(symbols))
    snap["n_classified"] = int(len(snap.get("symbols", [])))
    snap["data_source"] = str(IDX_LEGACY_DB)
    snap["date_min"] = str(close.index.min().date())
    snap["date_max"] = str(close.index.max().date())
    snap["name_type_by_symbol"] = {row["symbol"]: row["name_type"] for row in snap["symbols"]}
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap


def load_groups() -> dict[str, set[str]]:
    if not GROUPS_CFG.exists():
        return {}
    raw = json.loads(GROUPS_CFG.read_text(encoding="utf-8")).get("groups", {})
    return {k: set(v.get("tickers", [])) for k, v in raw.items()}


def symbol_group_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for g, syms in load_groups().items():
        for s in syms:
            out[s] = g
    return out


def symbol_behavior_metrics(
    close: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    *,
    lookback: int = METRICS_LOOKBACK,
) -> pd.DataFrame:
    """Per-symbol ADV (IDR), spike_rate_pct, ann_vol_pct from trailing window."""
    if close.empty:
        return pd.DataFrame(columns=["adv", "spike_rate_pct", "ann_vol_pct", "n_days"])

    tail_c = close.tail(lookback)
    rets = tail_c.pct_change()
    rows: list[dict[str, Any]] = []
    vol_df = volume.tail(lookback) if volume is not None else None

    for sym in close.columns:
        r = rets[sym].dropna()
        if len(r) < METRICS_MIN_DAYS:
            continue
        px = tail_c[sym].loc[r.index]
        if vol_df is not None and sym in vol_df.columns:
            v = vol_df[sym].loc[r.index].fillna(0)
            adv = float((px * v).median())
        else:
            adv = float(px.median())  # price-only fallback when volume missing

        spike = float((r >= 0.10).mean() * 100)
        ann_vol = float(r.std() * np.sqrt(252) * 100) if len(r) > 5 else np.nan
        rows.append(
            {
                "symbol": sym,
                "adv": adv,
                "spike_rate_pct": spike,
                "ann_vol_pct": ann_vol,
                "n_days": int(len(r)),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["adv", "spike_rate_pct", "ann_vol_pct", "n_days"])
    return pd.DataFrame(rows).set_index("symbol")


def _compounder_thresholds(metrics: pd.DataFrame) -> tuple[float, float]:
    n = len(metrics)
    if n < 8:
        adv_thr = float(metrics["adv"].median())
        vol_thr = float(metrics["ann_vol_pct"].quantile(0.70))
    else:
        adv_thr = float(metrics["adv"].quantile(COMPOUNDER_ADV_QUANTILE))
        vol_thr = float(metrics["ann_vol_pct"].quantile(COMPOUNDER_VOL_QUANTILE))
    return adv_thr, vol_thr


def classify_name_types(
    rets: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    *,
    close: pd.DataFrame | None = None,
) -> dict[str, str]:
    """fry | compounder | standard from spike rate, liquidity, vol — no ticker list."""
    if close is None:
        close = (1 + rets.fillna(0)).cumprod()
    metrics = symbol_behavior_metrics(close, volume)
    grp_map = symbol_group_map()
    fry_from_group = {s for g in FRY_GROUP_KEYS for s in load_groups().get(g, set())}
    adv_thr, vol_thr = _compounder_thresholds(metrics) if not metrics.empty else (0.0, np.inf)

    out: dict[str, str] = {}
    for sym in rets.columns:
        if sym not in metrics.index:
            out[sym] = "standard"
            continue
        m = metrics.loc[sym]
        spike = float(m["spike_rate_pct"])
        min_fry = FRY_SPIKE_RATE_MIN_GROUP if sym in fry_from_group or grp_map.get(sym) in FRY_GROUP_KEYS else FRY_SPIKE_RATE_MIN
        if spike >= min_fry or sym in fry_from_group:
            out[sym] = "fry"
            continue
        if (
            float(m["adv"]) >= adv_thr
            and spike < COMPOUNDER_SPIKE_MAX
            and float(m["ann_vol_pct"]) <= vol_thr
        ):
            out[sym] = "compounder"
        else:
            out[sym] = "standard"
    return out


def compounder_symbols(
    rets: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    *,
    close: pd.DataFrame | None = None,
) -> frozenset[str]:
    nt = classify_name_types(rets, volume, close=close)
    return frozenset(s for s, t in nt.items() if t == "compounder")


def liquid_core_symbols(
    rets: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    *,
    close: pd.DataFrame | None = None,
    n: int = LIQUID_CORE_N,
) -> list[str]:
    """Top-N compounders by ADV — used for regime bank-beta sleeve (data-picked, not hardcoded)."""
    if close is None:
        close = (1 + rets.fillna(0)).cumprod()
    comps = compounder_symbols(rets, volume, close=close)
    if not comps:
        return []
    metrics = symbol_behavior_metrics(close, volume)
    ranked = metrics.loc[metrics.index.isin(comps)].sort_values("adv", ascending=False)
    return ranked.head(n).index.tolist()


def build_name_type_snapshot(
    close: pd.DataFrame,
    volume: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Auditable JSON: metrics + classification for every symbol."""
    rets = close.pct_change()
    metrics = symbol_behavior_metrics(close, volume)
    adv_thr, vol_thr = _compounder_thresholds(metrics) if not metrics.empty else (0.0, np.inf)
    name_types = classify_name_types(rets, volume, close=close)
    comps = sorted(compounder_symbols(rets, volume, close=close))
    core = liquid_core_symbols(rets, volume, close=close)

    per_sym = []
    for sym, row in metrics.iterrows():
        per_sym.append(
            {
                "symbol": sym,
                "name_type": name_types.get(sym, "standard"),
                "adv": round(float(row["adv"]), 0),
                "spike_rate_pct": round(float(row["spike_rate_pct"]), 3),
                "ann_vol_pct": round(float(row["ann_vol_pct"]), 2),
                "n_days": int(row["n_days"]),
            }
        )
    per_sym.sort(key=lambda x: (-x["adv"], x["symbol"]))

    return {
        "method": "data_driven",
        "universe_id": SNAPSHOT_UNIVERSE_ID,
        "lookback_days": METRICS_LOOKBACK,
        "thresholds": {
            "fry_spike_rate_min_pct": FRY_SPIKE_RATE_MIN,
            "compounder_spike_max_pct": COMPOUNDER_SPIKE_MAX,
            "compounder_adv_quantile": COMPOUNDER_ADV_QUANTILE,
            "compounder_vol_quantile": COMPOUNDER_VOL_QUANTILE,
            "adv_threshold": round(adv_thr, 0),
            "vol_threshold_pct": round(vol_thr, 2),
        },
        "compounder_symbols": comps,
        "liquid_core_symbols": core,
        "name_type_by_symbol": {s: name_types.get(s, "standard") for s in metrics.index},
        "name_type_counts": {
            k: sum(1 for v in name_types.values() if v == k) for k in ("compounder", "fry", "standard")
        },
        "symbols": per_sym,
    }


def write_name_type_snapshot(
    close: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Write snapshot for an arbitrary close/vol panel (tests / ad-hoc). Prefer refresh_full_universe_snapshot()."""
    snap = build_name_type_snapshot(close, volume)
    out = path or SNAPSHOT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap
