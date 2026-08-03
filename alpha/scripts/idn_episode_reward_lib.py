"""Behavioral episode + reward dataset for IDX (psych framing, short horizon)."""

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
OUT_DIR = REPO / "data_lake/research_panels/idn_episode_reward"
DAILY_PANEL = REPO / "data_lake/markets/yfinance_asia/idn_liquid_daily_panel.parquet"
IHSG_REGIME = REPO / "data_lake/markets/yfinance_asia/ihsg_regime_daily.parquet"
BROADCAST = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
ENTITY = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/ticker_week_entity_market_panel.parquet"
GROUPS_CFG = REPO / "config/markets/indonesia_stock_groups.json"

from idn_name_type_lib import (  # noqa: E402
    FRY_GROUP_KEYS,
    FRY_SPIKE_RATE_MIN,
    FRY_SPIKE_RATE_MIN_GROUP,
    classify_name_types,
    compounder_symbols,
    ensure_full_universe_snapshot,
    liquid_core_from_snapshot,
    liquid_core_symbols,
    load_groups,
    name_type_map,
    symbol_group_map,
)
MIN_HISTORY_DEFAULT = 40


def resolve_episode_universe(liquid: list[str] | None = None) -> list[str]:
    """Tradable full-exchange universe (+ liquid overlay names), unless overridden."""
    if liquid is not None:
        return sorted(set(liquid))
    from idn_panel_lib import resolve_tradable_universe

    tradable = resolve_tradable_universe()
    if tradable:
        return tradable

    from run_idn_invest_trial import load_liquid_universe

    base = load_liquid_universe()
    if not DAILY_PANEL.exists():
        return sorted(set(base))
    panel_syms = set(pd.read_parquet(DAILY_PANEL, columns=["close"]).index.get_level_values("symbol").unique())
    extras: set[str] = set()
    for g in FRY_GROUP_KEYS:
        extras.update(load_groups().get(g, set()))
    extras.update({"CUAN.JK", "BRPT.JK", "PTRO.JK", "CDIA.JK", "BREN.JK"})
    extras = {s for s in extras if s in panel_syms and s not in base}
    return sorted(set(base) | extras)


def _fwd_return(close: pd.Series, horizon: int) -> pd.Series:
    return close.shift(-horizon) / close - 1.0


def _week_end_for_index(idx: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(idx, index=idx).dt.to_period("W-FRI").dt.to_timestamp("W-FRI")


def build_weekly_crossref(liquid: list[str]) -> pd.DataFrame:
    """Weekly price + entity tone + broadcast news shocks."""
    from idn_sentiment_validation_lib import prepare_liquid_weekly
    from quant_ai.pipeline import SHOCKS

    w = prepare_liquid_weekly(BROADCAST, ENTITY, liquid)
    b = pd.read_parquet(BROADCAST)
    b["week_end"] = pd.to_datetime(b["week_end"])
    shock_cols = [f"{s}_per_1k_rows" for s in SHOCKS if f"{s}_per_1k_rows" in b.columns]
    broadcast_cols = ["week_end", "yahoo_symbol", "mean_tone_weighted", "fwd_return_1w", "fwd_return_4w"]
    broadcast_cols += [c for c in shock_cols if c not in broadcast_cols]
    bb = b[(b["country_iso3"] == "IDN") & (b["yahoo_symbol"].isin(liquid))][broadcast_cols].copy()
    w = w.merge(bb, on=["week_end", "yahoo_symbol"], how="left", suffixes=("", "_bc"))
    if "fwd_return_1w_bc" in w.columns:
        w["fwd_return_1w"] = w["fwd_return_1w"].fillna(w["fwd_return_1w_bc"])
        w = w.drop(columns=["fwd_return_1w_bc"], errors="ignore")
    if "fwd_return_4w_bc" in w.columns:
        w["fwd_return_4w"] = w["fwd_return_4w"].fillna(w["fwd_return_4w_bc"])
        w = w.drop(columns=["fwd_return_4w_bc"], errors="ignore")
    w["news_risk_sum"] = w[shock_cols].fillna(0).sum(axis=1) if shock_cols else np.nan
    w["has_entity_tone"] = w["mean_tone_avg"].notna() if "mean_tone_avg" in w.columns else False
    w["has_broadcast_news"] = w["mean_tone_weighted"].notna() if "mean_tone_weighted" in w.columns else False
    return w


def build_weekly_sentiment(liquid: list[str]) -> pd.DataFrame:
    """Backward-compatible alias."""
    return build_weekly_crossref(liquid)


def _tag_data_tier(df: pd.DataFrame) -> pd.Series:
    has_price = df["close"].notna() & df["reward_20d"].notna()
    has_regime = df["ihsg_regime"].notna()
    has_prior = df.get("prior_return_1w", pd.Series(index=df.index)).notna()
    has_entity = df.get("has_entity_tone", df.get("mean_tone_avg", pd.Series(index=df.index)).notna())
    has_broadcast = df.get("has_broadcast_news", df.get("mean_tone_weighted", pd.Series(index=df.index)).notna())
    tiers = []
    for p, r, pr, ent, bc in zip(has_price, has_regime, has_prior, has_entity, has_broadcast, strict=True):
        if not p:
            tiers.append("invalid")
        elif r and pr and (ent or bc):
            tiers.append("full_crossref")
        elif r and pr:
            tiers.append("price_regime")
        else:
            tiers.append("price_only")
    return pd.Series(tiers, index=df.index)


def audit_data_lineage(df: pd.DataFrame | None = None) -> dict[str, Any]:
    """Honest coverage report: source ranges, per-symbol windows, era gaps."""
    from run_idn_invest_trial import load_liquid_universe

    liquid = load_liquid_universe()
    universe = resolve_episode_universe(liquid)
    report: dict[str, Any] = {"generated_at": pd.Timestamp.utcnow().isoformat(), "universe": {}}

    # source files
    sources: dict[str, Any] = {}
    if DAILY_PANEL.exists():
        raw = pd.read_parquet(DAILY_PANEL)
        close = raw["close"].unstack("symbol").sort_index()
        sources["daily_panel"] = {
            "path": str(DAILY_PANEL.relative_to(REPO)),
            "date_min": str(close.index.min().date()),
            "date_max": str(close.index.max().date()),
            "symbols": int(close.shape[1]),
            "trading_days": int(len(close)),
        }
    if IHSG_REGIME.exists():
        tape = pd.read_parquet(IHSG_REGIME)
        tape.index = pd.to_datetime(tape.index)
        sources["ihsg_regime"] = {
            "path": str(IHSG_REGIME.relative_to(REPO)),
            "date_min": str(tape.index.min().date()),
            "date_max": str(tape.index.max().date()),
            "rows": int(len(tape)),
        }
    if BROADCAST.exists():
        b = pd.read_parquet(BROADCAST)
        b["week_end"] = pd.to_datetime(b["week_end"])
        bidn = b[(b["country_iso3"] == "IDN") & (b["yahoo_symbol"].isin(universe))]
        sources["broadcast_weekly"] = {
            "path": str(BROADCAST.relative_to(REPO)),
            "week_min": str(bidn["week_end"].min().date()) if len(bidn) else None,
            "week_max": str(bidn["week_end"].max().date()) if len(bidn) else None,
            "rows_liquid": int(len(bidn)),
        }
    if ENTITY.exists():
        e = pd.read_parquet(ENTITY)
        e["week_end"] = pd.to_datetime(e["week_end"])
        eidn = e[(e["country_iso3"] == "IDN") & (e["yahoo_symbol"].isin(universe))]
        sources["entity_weekly"] = {
            "path": str(ENTITY.relative_to(REPO)),
            "week_min": str(eidn["week_end"].min().date()) if len(eidn) else None,
            "week_max": str(eidn["week_end"].max().date()) if len(eidn) else None,
            "rows_liquid": int(len(eidn)),
            "warning": "entity panel sparse recent years; prefer broadcast shocks for news cross-ref",
        }
    report["sources"] = sources

    report["universe"] = {
        "liquid_core_n": len(liquid),
        "episode_universe_n": len(universe),
        "added_vs_liquid": sorted(set(universe) - set(liquid)),
        "in_liquid_missing_panel": sorted(set(liquid) - set(close.columns)) if DAILY_PANEL.exists() else [],
    }

    w = build_weekly_crossref(universe)
    w["year"] = pd.to_datetime(w["week_end"]).dt.year
    era_rows = []
    for y in sorted(w["year"].dropna().unique()):
        sub = w[w["year"] == y]
        era_rows.append(
            {
                "year": int(y),
                "rows": int(len(sub)),
                "entity_tone_pct": round(float(sub["has_entity_tone"].mean() * 100), 1),
                "broadcast_news_pct": round(float(sub["has_broadcast_news"].mean() * 100), 1),
                "prior_return_pct": round(float(sub["prior_return_1w"].notna().mean() * 100), 1),
            }
        )
    report["weekly_crossref_by_year"] = era_rows

    if df is None and OUT_DIR.joinpath("daily_episodes.parquet").exists():
        df = pd.read_parquet(OUT_DIR / "daily_episodes.parquet")
    if df is not None and not df.empty:
        df = df.copy()
        df["year"] = pd.to_datetime(df["date"]).dt.year
        ep_era = []
        for y in sorted(df["year"].unique()):
            sub = df[df["year"] == y]
            ep_era.append(
                {
                    "year": int(y),
                    "rows": int(len(sub)),
                    "symbols": int(sub["yahoo_symbol"].nunique()),
                    "regime_pct": round(float(sub["ihsg_regime"].notna().mean() * 100), 1),
                    "entity_tone_pct": round(float(sub.get("mean_tone_avg", pd.Series(dtype=float)).notna().mean() * 100), 1),
                    "broadcast_news_pct": round(float(sub.get("mean_tone_weighted", pd.Series(dtype=float)).notna().mean() * 100), 1),
                    "full_crossref_pct": round(float((sub.get("data_tier", pd.Series(dtype=str)) == "full_crossref").mean() * 100), 1)
                    if "data_tier" in sub.columns
                    else None,
                }
            )
        report["episodes_by_year"] = ep_era
        sym_rows = []
        for sym, g in df.groupby("yahoo_symbol"):
            sym_rows.append(
                {
                    "symbol": sym,
                    "name_type": g["name_type"].iloc[0],
                    "episode_rows": int(len(g)),
                    "date_min": str(g["date"].min().date()),
                    "date_max": str(g["date"].max().date()),
                    "entity_tone_pct": round(float(g.get("mean_tone_avg", pd.Series(dtype=float)).notna().mean() * 100), 1),
                    "broadcast_news_pct": round(float(g.get("mean_tone_weighted", pd.Series(dtype=float)).notna().mean() * 100), 1),
                }
            )
        report["per_symbol"] = sorted(sym_rows, key=lambda x: x["date_min"])

    gaps = []
    if ENTITY.exists() and BROADCAST.exists():
        e_max = pd.to_datetime(eidn["week_end"].max()) if len(eidn) else None
        b_max = pd.to_datetime(bidn["week_end"].max()) if len(bidn) else None
        if e_max and b_max and e_max < b_max:
            gaps.append(f"entity panel ends {e_max.date()} but broadcast continues to {b_max.date()}")
    gorengan = [s for s in universe if s in {"CUAN.JK", "BREN.JK", "CDIA.JK", "BRPT.JK", "PTRO.JK", "TPIA.JK"}]
    if DAILY_PANEL.exists():
        panel_start = close.index.min()
        for s in gorengan:
            if s in close.columns:
                d0 = close[s].first_valid_index()
                if d0 is not None and pd.Timestamp(d0) > pd.Timestamp(panel_start):
                    gaps.append(f"{s} price history starts {d0.date()} (after panel start {panel_start.date()})")
    report["known_gaps"] = gaps
    return report


def build_episode_dataset(
    liquid: list[str] | None = None,
    *,
    min_history: int = MIN_HISTORY_DEFAULT,
) -> pd.DataFrame:
    """One row per (date, symbol) with state features + short-horizon rewards."""
    syms = resolve_episode_universe(liquid)
    if not DAILY_PANEL.exists():
        raise FileNotFoundError(DAILY_PANEL)

    raw = pd.read_parquet(DAILY_PANEL)
    close = raw["close"].unstack("symbol").sort_index()
    vol = raw["volume"].unstack("symbol").sort_index()
    use = [s for s in syms if s in close.columns]
    close = close[use]
    vol = vol[use]
    rets = close.pct_change()

    snap = ensure_full_universe_snapshot()
    name_types = name_type_map(snap)
    grp_map = symbol_group_map()

    if IHSG_REGIME.exists():
        tape = pd.read_parquet(IHSG_REGIME)
        tape.index = pd.to_datetime(tape.index)
    else:
        from idn_regime_lib import fetch_and_cache

        tape, _ = fetch_and_cache()
    regime_cols = ["label", "dd_from_63d_high_pct", "bounce_from_20d_low_pct", "ret_5d_pct", "ret_20d_pct"]
    ihsg = tape[regime_cols].rename(columns=lambda c: f"ihsg_{c}" if c != "label" else "ihsg_regime")

    weekly = build_weekly_crossref(use)
    weekly["week_end"] = pd.to_datetime(weekly["week_end"])

    rows: list[pd.DataFrame] = []
    for sym in use:
        c = close[sym].dropna()
        r = rets[sym].reindex(c.index)
        v = vol[sym].reindex(c.index) if sym in vol.columns else pd.Series(index=c.index, dtype=float)
        df = pd.DataFrame(index=c.index)
        df["yahoo_symbol"] = sym
        df["name_type"] = name_types.get(sym, "standard")
        df["stock_group"] = grp_map.get(sym, "")
        df["close"] = c
        df["return_1d"] = r
        df["vol_20d"] = r.rolling(20, min_periods=10).std() * np.sqrt(252)
        df["max_ret_5d"] = r.rolling(5, min_periods=3).max()
        df["spike_10d_5d"] = (df["max_ret_5d"] >= 0.10).astype(int)
        df["spike_10d_count_20d"] = (r >= 0.10).rolling(20, min_periods=5).sum()
        df["mom_20d"] = c / c.shift(20) - 1.0
        df["dd_60d"] = c / c.rolling(60, min_periods=20).max() - 1.0
        if v.notna().any():
            df["vol_ratio_20d"] = v / v.rolling(20, min_periods=5).mean()
        df = df.join(ihsg, how="left")
        df["week_end"] = _week_end_for_index(df.index)
        df = df.reset_index(names="date")
        rows.append(df)

    panel = pd.concat(rows, ignore_index=True)
    panel = panel.merge(weekly, on=["week_end", "yahoo_symbol"], how="left", suffixes=("", "_wk"))

    # forward rewards (punishment = negative)
    for sym in use:
        m = panel["yahoo_symbol"] == sym
        c = panel.loc[m, "close"]
        for h in REWARD_HORIZONS:
            panel.loc[m, f"reward_{h}d"] = _fwd_return(c, h)

    panel["reward_5d_pct"] = panel["reward_5d"] * 100
    panel["reward_20d_pct"] = panel["reward_20d"] * 100
    panel["win_5d"] = (panel["reward_5d"] > 0).astype("Int64")
    panel["win_20d"] = (panel["reward_20d"] > 0).astype("Int64")

    panel["episode_state"] = _assign_episode_state(panel)
    panel["suggested_action"] = _suggest_action(panel)
    panel["group_sync_spikes_5d"] = group_sync_spike_count(panel)
    panel["data_tier"] = _tag_data_tier(panel)

    panel = panel.dropna(subset=["reward_20d"])
    panel = panel[panel.groupby("yahoo_symbol").cumcount() >= min_history]
    panel["panel_date_max"] = pd.Timestamp(close.index.max())
    panel["reward_horizon_days"] = 20
    return panel.sort_values(["date", "yahoo_symbol"]).reset_index(drop=True)


def _assign_episode_state(df: pd.DataFrame) -> pd.Series:
    """Composite behavioral state label."""
    reg = df["ihsg_regime"].fillna("unknown")
    nt = df["name_type"]
    spike = df["spike_10d_5d"].fillna(0).astype(int)
    prior = df.get("prior_return_1w", df.get("return_1w", pd.Series(0, index=df.index)))

    states = []
    for r, n, s, p in zip(reg, nt, spike, prior, strict=True):
        if n == "fry" and s == 1:
            st = "fry_spike_day"
        elif n == "fry":
            st = "fry_idle"
        elif n == "compounder" and r in ("washout", "recovery"):
            st = f"compounder_{r}"
        elif p is not None and np.isfinite(p) and p <= -0.05:
            st = "fade_candidate"
        elif p is not None and np.isfinite(p) and p >= 0.05:
            st = "chase_trap"
        elif r == "washout":
            st = "index_washout"
        elif r == "recovery":
            st = "index_recovery"
        else:
            st = "neutral"
        states.append(st)
    return pd.Series(states, index=df.index)


def _suggest_action(df: pd.DataFrame) -> pd.Series:
    """Rule-based action bucket (baseline policy)."""
    actions = []
    for st, nt, dd in zip(df["episode_state"], df["name_type"], df["dd_60d"], strict=True):
        if st == "fade_candidate":
            actions.append("fade_last_week")
        elif st == "fry_spike_day" and nt == "fry":
            actions.append("fry_hold_short")
        elif st in ("compounder_washout", "compounder_recovery") and dd is not None and dd <= -0.08:
            actions.append("compounder_dip")
        elif st == "chase_trap":
            actions.append("flat_avoid_chase")
        else:
            actions.append("flat")
    return pd.Series(actions, index=df.index)


def fry_spike_lifecycle_table(df: pd.DataFrame) -> pd.DataFrame:
    """Forward returns after +10% / +25% days, by name_type."""
    sub = df[df["return_1d"].notna()].copy()
    sub["spike_10"] = sub["return_1d"] >= 0.10
    sub["spike_25"] = sub["return_1d"] >= 0.25
    rows = []
    for label, mask in [("after_10pct", sub["spike_10"]), ("after_25pct", sub["spike_25"])]:
        hit = sub[mask]
        if hit.empty:
            continue
        for nt in ["fry", "compounder", "standard"]:
            h = hit[hit["name_type"] == nt]
            if h.empty:
                continue
            rows.append(
                {
                    "event": label,
                    "name_type": nt,
                    "n": len(h),
                    "mean_5d": round(float(h["reward_5d_pct"].mean()), 2),
                    "mean_20d": round(float(h["reward_20d_pct"].mean()), 2),
                    "win_5d": round(float(h["win_5d"].mean() * 100), 1),
                    "win_20d": round(float(h["win_20d"].mean() * 100), 1),
                }
            )
        top = hit.groupby("yahoo_symbol").size().sort_values(ascending=False).head(8)
        for sym, cnt in top.items():
            h = hit[hit["yahoo_symbol"] == sym]
            rows.append(
                {
                    "event": label,
                    "name_type": sym,
                    "n": int(cnt),
                    "mean_5d": round(float(h["reward_5d_pct"].mean()), 2),
                    "mean_20d": round(float(h["reward_20d_pct"].mean()), 2),
                    "win_5d": round(float(h["win_5d"].mean() * 100), 1),
                    "win_20d": round(float(h["win_20d"].mean() * 100), 1),
                }
            )
    return pd.DataFrame(rows)


def group_sync_spike_count(panel: pd.DataFrame) -> pd.Series:
    """Same stock_group had a +10% day within prior 5 sessions."""
    if "stock_group" not in panel.columns or panel["stock_group"].eq("").all():
        return pd.Series(0, index=panel.index)
    out = []
    for sym, g in panel.groupby("yahoo_symbol"):
        grp = g["stock_group"].iloc[0] if len(g) else ""
        if not grp:
            out.append(pd.Series(0, index=g.index))
            continue
        peers = panel[(panel["stock_group"] == grp) & (panel["yahoo_symbol"] != sym)]
        if peers.empty:
            out.append(pd.Series(0, index=g.index))
            continue
        peer_spike_dates = peers.loc[peers["return_1d"] >= 0.10, "date"].unique()
        peer_spike_set = set(pd.to_datetime(peer_spike_dates))
        counts = []
        for d in g["date"]:
            d = pd.Timestamp(d)
            window = {d - pd.Timedelta(days=i) for i in range(1, 8)}
            counts.append(len(peer_spike_set & window))
        out.append(pd.Series(counts, index=g.index))
    return pd.concat(out).sort_index()


def episode_reward_summary(df: pd.DataFrame, *, group: str = "episode_state") -> pd.DataFrame:
    """Mean reward / win rate by group."""
    g = df.groupby(group, dropna=False)
    out = g.agg(
        n=("reward_20d_pct", "count"),
        mean_5d=("reward_5d_pct", "mean"),
        mean_20d=("reward_20d_pct", "mean"),
        win_5d=("win_5d", "mean"),
        win_20d=("win_20d", "mean"),
    )
    return out.reset_index().sort_values("mean_20d", ascending=False)


def action_policy_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Reward when following suggested_action (fires only)."""
    sub = df[df["suggested_action"] != "flat"].copy()
    if sub.empty:
        return pd.DataFrame()
    return episode_reward_summary(sub, group="suggested_action")


def fit_simple_behavioral_scores(
    df: pd.DataFrame,
    *,
    oos_frac: float = 0.25,
) -> dict[str, Any]:
    """Per episode_state: empirical mean 20d reward on train, score OOS.

    OOS = last ``oos_frac`` of calendar time in the panel (default 25%).
    No magic calendar year — the price panel only starts 2022 anyway.
    """
    if df.empty:
        return {"error": "empty_df"}
    dates = pd.to_datetime(df["date"]).sort_values()
    cut = dates.quantile(1.0 - oos_frac)
    train = df[df["date"] < cut]
    test = df[df["date"] >= cut]
    if train.empty or test.empty:
        return {"error": "insufficient_train_test"}

    train_stats = episode_reward_summary(train)
    score_map = dict(zip(train_stats["episode_state"], train_stats["mean_20d"]))

    test = test.copy()
    test["pred_score"] = test["episode_state"].map(score_map).fillna(0.0)
    test["model_action"] = np.where(
        (test["pred_score"] > 0) & (~test["episode_state"].isin(["chase_trap", "fry_idle"])),
        "model_long",
        "flat",
    )
    fires = test[test["model_action"] == "model_long"]
    return {
        "oos_frac": oos_frac,
        "train_end": str(pd.Timestamp(cut).date()),
        "oos_start": str(pd.Timestamp(cut).date()),
        "train_rows": int(len(train)),
        "oos_rows": int(len(test)),
        "train_states": len(score_map),
        "oos_fires": len(fires),
        "oos_mean_20d_when_fired": round(float(fires["reward_20d_pct"].mean()), 3) if len(fires) else None,
        "oos_win_20d_when_fired": round(float(fires["win_20d"].mean() * 100), 1) if len(fires) else None,
        "oos_bench_mean_20d": round(float(test["reward_20d_pct"].mean()), 3),
        "top_train_states": train_stats.head(8).to_dict(orient="records"),
        "score_map": {k: round(v, 3) for k, v in sorted(score_map.items(), key=lambda x: -x[1])[:12]},
    }
