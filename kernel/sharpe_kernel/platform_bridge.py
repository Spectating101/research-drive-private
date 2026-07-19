"""Connect research data panels (registry) to the live alpha pipeline.

Built at different times; this module is the explicit glue layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_REGISTRY = "config/research_query_registry.json"
FUSED_DATASET_ID = "cross_asset_fused_primary_panel"

# Shock columns that predict forward vol better than direction (research sprint v1).
STRESS_COLS = (
    "financial_stress_per_1k_rows",
    "geopolitical_security_per_1k_rows",
    "political_instability_per_1k_rows",
    "macro_policy_per_1k_rows",
    "trade_supply_chain_per_1k_rows",
)
# Data-discovered anchor (blind sweep): GDELT market-relevance score, not shock taxonomy.
MKT_REL_COL = "mean_market_relevance_score_weighted"


def load_registry(repo_root: Path, registry_path: str | Path | None = None) -> dict[str, Any]:
    path = repo_root / (registry_path or DEFAULT_REGISTRY)
    return json.loads(path.read_text(encoding="utf-8"))


def _dataset_entry(reg: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    datasets = reg.get("datasets", [])
    if isinstance(datasets, dict):
        ds = datasets.get(dataset_id)
        if ds:
            return ds
        raise KeyError(f"unknown dataset_id: {dataset_id}")
    for row in datasets:
        if isinstance(row, dict) and row.get("dataset_id") == dataset_id:
            return row
    raise KeyError(f"unknown dataset_id: {dataset_id}")


def resolve_dataset_parquet(
    repo_root: Path,
    dataset_id: str,
    *,
    registry_path: str | Path | None = None,
) -> Path:
    """Return primary parquet for a registry dataset's default_run_id."""
    reg = load_registry(repo_root, registry_path)
    ds = _dataset_entry(reg, dataset_id)
    run_id = ds.get("default_run_id")
    if not run_id:
        raise ValueError(f"dataset {dataset_id} has no default_run_id")
    rel = ds.get("primary_artifact") or ds.get("default_parquet")
    if rel:
        rel = str(rel).replace("{run_id}", str(run_id))
        path = repo_root / rel
    else:
        root = ds.get("local_root")
        fname = ds.get("local_file")
        if not root or not fname:
            raise ValueError(f"dataset {dataset_id} has no resolvable parquet path")
        path = repo_root / str(root) / str(run_id) / str(fname)
    if not path.exists():
        raise FileNotFoundError(f"missing panel for {dataset_id}: {path}")
    return path


def global_news_risk_overlay(
    repo_root: Path,
    *,
    as_of: pd.Timestamp | None = None,
    registry_path: str | Path | None = None,
    dataset_id: str = FUSED_DATASET_ID,
    lookback_weeks: int = 4,
    floor_gross: float = 0.55,
    ceiling_gross: float = 1.0,
) -> dict[str, Any]:
    """Aggregate Asia shock intensity → gross exposure scaler for multi-asset book.

    High recent stress → scale risky weights down (vol-overlay framing from sprint v1).
    """
    path = resolve_dataset_parquet(repo_root, dataset_id, registry_path=registry_path)
    df = pd.read_parquet(path)
    if "week_end" not in df.columns:
        raise ValueError(f"{path} missing week_end")

    df = df.copy()
    df["week_end"] = pd.to_datetime(df["week_end"], errors="coerce")
    cols = [c for c in STRESS_COLS if c in df.columns]
    if not cols:
        raise ValueError(f"no stress columns in {path}")

    as_of = pd.Timestamp(as_of or df["week_end"].max())
    hist = df[df["week_end"] <= as_of].sort_values("week_end")
    if hist.empty:
        return {"gross_scalar": 1.0, "reason": "no_history", "path": str(path)}

    recent = hist.tail(int(lookback_weeks) * 13)  # ~13 countries per week
    if recent.empty:
        return {"gross_scalar": 1.0, "reason": "no_recent", "path": str(path)}

    # Country-week z within each week, then mean across countries/weeks.
    z_parts: list[pd.Series] = []
    for week, grp in recent.groupby("week_end"):
        vals = grp[cols].astype(float)
        row_mean = vals.mean(axis=1)
        mu, sd = float(row_mean.mean()), float(row_mean.std(ddof=1))
        if not np.isfinite(sd) or sd < 1e-12:
            z = pd.Series(0.0, index=grp.index)
        else:
            z = (row_mean - mu) / sd
        z_parts.append(z)
    z_all = pd.concat(z_parts) if z_parts else pd.Series(dtype=float)
    stress_z = float(z_all.mean()) if len(z_all) else 0.0

    # Map z to gross scalar: calm (z<=0) → ceiling; stressed (z>=2) → floor.
    t = float(np.clip(stress_z, 0.0, 2.0) / 2.0)
    gross_scalar = float(ceiling_gross - t * (ceiling_gross - floor_gross))

    return {
        "gross_scalar": gross_scalar,
        "stress_z": stress_z,
        "lookback_weeks": int(lookback_weeks),
        "floor_gross": float(floor_gross),
        "ceiling_gross": float(ceiling_gross),
        "panel_path": str(path),
        "as_of_week": str(hist["week_end"].max().date()),
        "stress_cols": cols,
    }


def apply_gross_scalar_to_weights(
    weights: dict[str, float],
    gross_scalar: float,
    *,
    cash_ticker: str = "BIL",
) -> dict[str, float]:
    """Scale non-cash weights; park freed exposure in cash."""
    scalar = float(np.clip(gross_scalar, 0.0, 1.5))
    cash = str(cash_ticker)
    risky = {k: float(v) for k, v in weights.items() if k != cash and abs(v) > 1e-12}
    cash_w = float(weights.get(cash, 0.0))
    risky_sum = sum(risky.values())
    if risky_sum <= 1e-12:
        return dict(weights)

    scaled = {k: v * scalar for k, v in risky.items()}
    new_risky_sum = sum(scaled.values())
    out = dict(scaled)
    out[cash] = cash_w + (risky_sum - new_risky_sum)
    # renormalize if drift
    total = sum(out.values())
    if total > 1e-12 and abs(total - 1.0) > 1e-6:
        out = {k: v / total for k, v in out.items()}
    return out


def export_monthly_equity_curve(equity: pd.Series, out_path: Path) -> Path:
    s = equity.copy()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index().dropna()
    monthly = s.resample("ME").last().dropna()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_frame("equity").to_csv(out_path)
    return out_path


def load_integration_config(repo_root: Path, path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = repo_root / (path or "config/platform_integration.json")
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def _fused_run_dir(panel_path: Path) -> Path:
    return panel_path.parent


def crypto_regulation_overlay(
    repo_root: Path,
    *,
    as_of: pd.Timestamp | None = None,
    registry_path: str | Path | None = None,
    dataset_id: str = FUSED_DATASET_ID,
) -> dict[str, Any]:
    """Asia crypto regulation intensity → BTC/ETH sleeve scaler (sprint v3)."""
    fused = resolve_dataset_parquet(repo_root, dataset_id, registry_path=registry_path)
    crypto_path = _fused_run_dir(fused) / "country_week_crypto_news_panel.parquet"
    if not crypto_path.exists():
        return {"btc_eth_scalar": 1.0, "reason": "no_crypto_panel", "path": str(crypto_path)}

    crypto = pd.read_parquet(crypto_path)
    crypto["week_end"] = pd.to_datetime(crypto["week_end"], errors="coerce")
    col = "event_regulation_enforcement_per_1k_crypto_rows"
    if col not in crypto.columns:
        return {"btc_eth_scalar": 1.0, "reason": "no_reg_col"}

    as_of = pd.Timestamp(as_of or crypto["week_end"].max())
    hist = crypto[crypto["week_end"] <= as_of].sort_values("week_end")
    if hist.empty:
        return {"btc_eth_scalar": 1.0, "reason": "no_history"}

    asia = hist.groupby("week_end")[col].sum().tail(8)
    mu, sd = float(asia.mean()), float(asia.std(ddof=0))
    z = (float(asia.iloc[-1]) - mu) / sd if sd > 1e-12 else 0.0
    scalar = float(1.0 - 0.25 * np.clip(z, 0.0, 2.0) / 2.0)
    return {
        "btc_eth_scalar": scalar,
        "reg_z": float(z),
        "panel_path": str(crypto_path),
        "as_of_week": str(hist["week_end"].max().date()),
    }


def _load_fused_panel(repo_root: Path, *, registry_path: str | Path | None = None, dataset_id: str = FUSED_DATASET_ID) -> pd.DataFrame:
    path = resolve_dataset_parquet(repo_root, dataset_id, registry_path=registry_path)
    df = pd.read_parquet(path)
    df["week_end"] = pd.to_datetime(df["week_end"], errors="coerce")
    return df


def asia_weekly_relevance_state(
    repo_root: Path,
    *,
    as_of: pd.Timestamp | None = None,
    registry_path: str | Path | None = None,
    lookback_weeks: int = 52,
) -> dict[str, Any]:
    """Asia weekly level + cross-country dispersion of market-relevance scores."""
    df = _load_fused_panel(repo_root, registry_path=registry_path)
    if MKT_REL_COL not in df.columns:
        raise ValueError(f"fused panel missing {MKT_REL_COL}")

    as_of = pd.Timestamp(as_of or df["week_end"].max())
    hist = df[df["week_end"] <= as_of].copy()
    weekly = (
        hist.groupby("week_end", as_index=False)[MKT_REL_COL]
        .agg(level="mean", dispersion="std")
        .dropna(subset=["level"])
        .sort_values("week_end")
    )
    if weekly.empty:
        return {"reason": "no_weekly_history"}

    trail = weekly.tail(int(lookback_weeks))
    level_now = float(trail["level"].iloc[-1])
    disp_now = float(trail["dispersion"].iloc[-1]) if trail["dispersion"].notna().any() else 0.0
    lvl_mu, lvl_sd = float(trail["level"].mean()), float(trail["level"].std(ddof=0))
    disp_mu, disp_sd = float(trail["dispersion"].mean()), float(trail["dispersion"].std(ddof=0))
    level_z = (level_now - lvl_mu) / lvl_sd if lvl_sd > 1e-12 else 0.0
    disp_z = (disp_now - disp_mu) / disp_sd if disp_sd > 1e-12 else 0.0

    return {
        "as_of_week": str(trail["week_end"].iloc[-1].date()),
        "level": level_now,
        "dispersion": disp_now,
        "level_z": float(level_z),
        "dispersion_z": float(disp_z),
        "lookback_weeks": int(lookback_weeks),
        "panel_weeks": int(len(weekly)),
    }


def market_relevance_overlay(
    repo_root: Path,
    *,
    as_of: pd.Timestamp | None = None,
    registry_path: str | Path | None = None,
    lookback_weeks: int = 52,
    floor_gross: float = 0.55,
    ceiling_gross: float = 1.0,
    max_disp_tilt: float = 0.12,
) -> dict[str, Any]:
    """Vol leg: high Asia relevance level → scale gross down. Dispersion leg: tilt to cash."""
    state = asia_weekly_relevance_state(
        repo_root, as_of=as_of, registry_path=registry_path, lookback_weeks=lookback_weeks
    )
    if state.get("reason"):
        return {"gross_scalar": 1.0, "disp_tilt": 0.0, **state}

    # High relevance → higher forward vol (stable 434w); map level_z to gross scalar.
    t = float(np.clip(state["level_z"], 0.0, 2.0) / 2.0)
    gross_scalar = float(ceiling_gross - t * (ceiling_gross - floor_gross))
    # High cross-country dispersion → safe-haven tilt (BIL), discovered OOS on live book.
    disp_tilt = float(max_disp_tilt * np.clip(state["dispersion_z"], 0.0, 2.0) / 2.0)

    return {
        **state,
        "gross_scalar": gross_scalar,
        "disp_tilt": disp_tilt,
        "floor_gross": float(floor_gross),
        "ceiling_gross": float(ceiling_gross),
        "signal": MKT_REL_COL,
    }


def apply_dispersion_tilt_to_weights(
    weights: dict[str, float],
    disp_tilt: float,
    *,
    from_tickers: tuple[str, ...] = ("EEM", "EFA"),
    cash_ticker: str = "BIL",
) -> dict[str, float]:
    """Shift weight from intl/emerging sleeves toward cash when Asia relevance disperses."""
    tilt = float(np.clip(disp_tilt, 0.0, 0.25))
    if tilt <= 1e-12:
        return dict(weights)
    out = dict(weights)
    cash = str(cash_ticker)
    moved = 0.0
    for sym in from_tickers:
        if sym in out and out[sym] > 0:
            cut = float(out[sym]) * tilt
            out[sym] = float(out[sym]) - cut
            moved += cut
    if moved > 0:
        out[cash] = float(out.get(cash, 0.0)) + moved
    total = sum(out.values())
    if total > 1e-12 and abs(total - 1.0) > 1e-6:
        out = {k: v / total for k, v in out.items()}
    return out


def apply_crypto_scalar_to_weights(
    weights: dict[str, float],
    btc_eth_scalar: float,
    *,
    crypto_tickers: tuple[str, ...] = ("BTC-USD", "ETH-USD"),
    cash_ticker: str = "BIL",
) -> dict[str, float]:
    scalar = float(np.clip(btc_eth_scalar, 0.0, 1.5))
    out = dict(weights)
    cash = str(cash_ticker)
    freed = 0.0
    for sym in crypto_tickers:
        if sym in out:
            old = float(out[sym])
            new = old * scalar
            freed += old - new
            out[sym] = new
    if freed > 0:
        out[cash] = float(out.get(cash, 0.0)) + freed
    total = sum(out.values())
    if total > 1e-12 and abs(total - 1.0) > 1e-6:
        out = {k: v / total for k, v in out.items()}
    return out


def file_age_days(path: Path) -> float | None:
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    return (pd.Timestamp.utcnow().timestamp() - mtime) / 86400.0


def latest_child_run(root: Path, pattern: str = "*") -> Path | None:
    if not root.exists():
        return None
    runs = sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return runs[0] if runs else None
