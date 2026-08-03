"""Fry episode research — day-by-day movement sorting, not ticker hold returns.

Unit of analysis:
  - calendar day × cross-sectional move rank (who moved most *today*)
  - fry episode windows (trigger → pop → fade) walked day-by-day per symbol
  - path outcomes after trigger (max pop, days-to-10%, giveback) — not mean hold 5d
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
OUT_DIR = REPO / "data_lake/research_panels/idn_fry_episode"
TURNAROUND_PANEL = REPO / "data_lake/research_panels/idn_turnaround/daily_features.parquet"

# Episode FSM thresholds
TRIGGER_VOL_MIN = 1.6
TRIGGER_DD_5D_MAX = -0.04
POP_RET_MIN = 0.08
POP_RET_STRONG = 0.10
ARA_RET_MIN = 0.24
EPISODE_MAX_DAYS = 12
COOLDOWN_DAYS = 5


def load_daily_moves(panel_path: Path | None = None, *, extend_from: str | None = None) -> pd.DataFrame:
    """Load day-level panel with returns + fry labels.

    extend_from: if set (e.g. 2019-07-01), build multi-year panel via big-winner extended merge.
    """
    if extend_from:
        return load_extended_daily_moves(extend_from=extend_from)

    path = panel_path or TURNAROUND_PANEL
    if not path.exists():
        from idn_panel_lib import load_merged_long_panel
        from idn_name_type_lib import ensure_full_universe_snapshot, name_type_map

        long = load_merged_long_panel()
        close = long["close"].unstack("symbol").sort_index()
        rets = close.pct_change()
        snap = ensure_full_universe_snapshot()
        nt = name_type_map(snap)
        rows = []
        for sym in close.columns:
            for dt, c in close[sym].dropna().items():
                r = rets.at[dt, sym] if dt in rets.index else np.nan
                rows.append(
                    {
                        "date": pd.Timestamp(dt),
                        "yahoo_symbol": sym,
                        "close": float(c),
                        "return_1d": float(r) if pd.notna(r) else np.nan,
                        "name_type": nt.get(sym, "standard"),
                    }
                )
        df = pd.DataFrame(rows)
    else:
        cols = [
            "date",
            "yahoo_symbol",
            "return_1d",
            "return_5d",
            "name_type",
            "vol_ratio_20d",
            "bandar_lite_label",
            "close",
            "consecutive_ara_days",
            "pos_52w_range",
        ]
        avail = pd.read_parquet(path, columns=None).columns.tolist()
        use = [c for c in cols if c in avail]
        df = pd.read_parquet(path, columns=use)

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["yahoo_symbol", "date"]).reset_index(drop=True)
    return _add_path_columns(df)


def load_extended_daily_moves(*, extend_from: str = "2019-07-01") -> pd.DataFrame:
    """Full multi-year daily panel (idx_all + turnaround features) for fry episode research."""
    from idn_big_winner_reverse_lib import build_extended_panel

    panel = build_extended_panel(min_date=extend_from)
    if panel.empty:
        return panel
    keep = [
        "date",
        "yahoo_symbol",
        "return_1d",
        "return_5d",
        "name_type",
        "vol_ratio_20d",
        "bandar_lite_label",
        "close",
        "consecutive_ara_days",
        "pos_52w_range",
        "rsi14",
        "dd_60d",
        "quiet_acc_score_5d",
        "chase_score_5d",
        "ihsg_regime",
        "near_support_40d",
        "near_support_60d",
        "is_ara_day",
        "panel_tier",
    ]
    use = [c for c in keep if c in panel.columns]
    df = panel[use].copy()
    if "close" not in df.columns and "return_1d" in df.columns:
        # reconstruct pseudo close for path stats within symbol
        parts: list[pd.DataFrame] = []
        for sym, g in df.groupby("yahoo_symbol", sort=False):
            g = g.sort_values("date").copy()
            g["close"] = (1 + g["return_1d"].fillna(0)).cumprod() * 100.0
            parts.append(g)
        df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["yahoo_symbol", "date"]).reset_index(drop=True)
    return _add_path_columns(df)


def _add_path_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Forward path stats computed day-by-day within each symbol."""
    parts: list[pd.DataFrame] = []
    for sym, g in df.groupby("yahoo_symbol", sort=False):
        g = g.sort_values("date").copy()
        c = g["close"] if "close" in g.columns else (1 + g["return_1d"].fillna(0)).cumprod()
        r = g["return_1d"]
        for h in range(1, 6):
            g[f"fwd_{h}d"] = c.shift(-h) / c - 1.0
        g["fwd_max_5d"] = g[[f"fwd_{h}d" for h in range(1, 6)]].max(axis=1)
        for h in (1, 2, 3):
            g[f"fwd_max_{h}d"] = g[[f"fwd_{j}d" for j in range(1, h + 1)]].max(axis=1)
        hits: list[float] = []
        rvals = r.to_numpy()
        for i in range(len(g)):
            window = rvals[i + 1 : i + 6]
            hit = np.where(window >= POP_RET_STRONG)[0]
            hits.append(float(hit[0] + 1) if len(hit) else np.nan)
        g["days_to_10pct"] = hits
        peak = c.shift(-1).rolling(5, min_periods=1).max()
        end5 = c.shift(-5)
        g["giveback_from_5d_peak"] = end5 / peak - 1.0
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def add_daily_cross_section_ranks(df: pd.DataFrame) -> pd.DataFrame:
    """Per calendar day: rank every symbol's move — sort the market, not the ticker book."""
    out = df.copy()
    out["return_1d_pct"] = out["return_1d"] * 100
    out["n_symbols_that_day"] = out.groupby("date")["return_1d"].transform("count")

    valid = out["return_1d"].notna()
    out["cs_move_pct_rank"] = np.nan
    out.loc[valid, "cs_move_pct_rank"] = out.loc[valid].groupby("date")["return_1d"].rank(pct=True, method="average")

    out["cs_move_decile"] = np.nan
    for dt, idx in out.loc[valid].groupby("date").groups.items():
        n = len(idx)
        if n < 5:
            continue
        ranks = out.loc[idx, "return_1d"].rank(method="first")
        out.loc[idx, "cs_move_decile"] = pd.qcut(ranks, q=min(10, n), labels=False, duplicates="drop")

    out["cs_move_top10"] = (out["cs_move_pct_rank"] >= 0.90).fillna(False).astype(int)
    out["cs_move_top5"] = (out["cs_move_pct_rank"] >= 0.95).fillna(False).astype(int)
    out["cs_move_bottom10"] = (out["cs_move_pct_rank"] <= 0.10).fillna(False).astype(int)
    return out


def _is_trigger_row(row: pd.Series) -> bool:
    if row.get("name_type") != "fry":
        return False
    if pd.notna(row.get("return_1d")) and row["return_1d"] >= POP_RET_MIN:
        return False
    label = str(row.get("bandar_lite_label") or "")
    if label == "quiet_volume_build":
        return True
    vol = row.get("vol_ratio_20d")
    r5 = row.get("return_5d")
    if pd.notna(vol) and pd.notna(r5):
        if float(vol) >= TRIGGER_VOL_MIN and float(r5) <= TRIGGER_DD_5D_MAX:
            return True
    return False


def _is_pop_row(row: pd.Series) -> bool:
    r = row.get("return_1d")
    if pd.isna(r):
        return False
    r = float(r)
    if r >= POP_RET_STRONG:
        return True
    if r >= ARA_RET_MIN:
        return True
    if r >= POP_RET_MIN and str(row.get("bandar_lite_label") or "") == "chase_into_spike":
        return True
    return False


def detect_fry_episodes(df: pd.DataFrame) -> pd.DataFrame:
    """Walk each fry symbol day-by-day; label episode phase and episode_id."""
    fry = df[df["name_type"] == "fry"].copy()
    rows: list[dict[str, Any]] = []
    ep_counter = 0

    for sym, g in fry.groupby("yahoo_symbol", sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        in_ep = False
        ep_id: int | None = None
        ep_start: pd.Timestamp | None = None
        trigger_dt: pd.Timestamp | None = None
        pop_dt: pd.Timestamp | None = None
        days_in_ep = 0
        cooldown = 0
        ep_high = np.nan

        for i, row in g.iterrows():
            dt = row["date"]
            phase = "fry_idle"
            if cooldown > 0:
                cooldown -= 1
                phase = "cooldown"
            elif not in_ep:
                if _is_trigger_row(row):
                    in_ep = True
                    ep_counter += 1
                    ep_id = ep_counter
                    ep_start = dt
                    trigger_dt = dt
                    pop_dt = None
                    days_in_ep = 0
                    ep_high = float(row["close"]) if "close" in row and pd.notna(row["close"]) else np.nan
                    phase = "trigger"
                else:
                    phase = "fry_idle"
            else:
                days_in_ep += 1
                if "close" in row and pd.notna(row["close"]):
                    ep_high = max(ep_high, float(row["close"])) if pd.notna(ep_high) else float(row["close"])
                if pop_dt is None and _is_pop_row(row):
                    pop_dt = dt
                    phase = "pop_day"
                elif pop_dt is not None:
                    phase = "pop_aftershock"
                else:
                    phase = "post_trigger_wait"

                end = False
                if days_in_ep >= EPISODE_MAX_DAYS:
                    end = True
                if pop_dt is not None and days_in_ep >= 3:
                    r = row.get("return_1d")
                    if pd.notna(r) and float(r) <= -0.06:
                        end = True
                if end:
                    in_ep = False
                    cooldown = COOLDOWN_DAYS
                    phase = "episode_end"

            rows.append(
                {
                    "date": dt,
                    "yahoo_symbol": sym,
                    "episode_id": ep_id,
                    "episode_phase": phase,
                    "episode_day": days_in_ep if in_ep or phase == "episode_end" else 0,
                    "trigger_date": trigger_dt,
                    "pop_date": pop_dt,
                    "return_1d_pct": round(float(row["return_1d"]) * 100, 3) if pd.notna(row.get("return_1d")) else None,
                    "cs_move_pct_rank": row.get("cs_move_pct_rank"),
                    "cs_move_decile": row.get("cs_move_decile"),
                    "vol_ratio_20d": row.get("vol_ratio_20d"),
                    "bandar_lite_label": row.get("bandar_lite_label"),
                    "fwd_max_5d_pct": round(float(row["fwd_max_5d"]) * 100, 3)
                    if pd.notna(row.get("fwd_max_5d"))
                    else None,
                    "days_to_10pct": row.get("days_to_10pct"),
                    "giveback_from_5d_peak_pct": round(float(row["giveback_from_5d_peak"]) * 100, 3)
                    if pd.notna(row.get("giveback_from_5d_peak"))
                    else None,
                }
            )

    return pd.DataFrame(rows)


def summarize_episode_table(ep_days: pd.DataFrame) -> pd.DataFrame:
    """One row per episode with duration, trigger→pop lag, pop size."""
    if ep_days.empty or "episode_id" not in ep_days.columns:
        return pd.DataFrame()
    triggers = ep_days[ep_days["episode_phase"] == "trigger"].copy()
    if triggers.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for (sym, eid), g in ep_days[ep_days["episode_id"].notna()].groupby(["yahoo_symbol", "episode_id"]):
        g = g.sort_values("date")
        trig = g[g["episode_phase"] == "trigger"]
        if trig.empty:
            continue
        t0 = trig.iloc[0]
        pop_rows = g[g["episode_phase"] == "pop_day"]
        pop_dt = pop_rows.iloc[0]["date"] if not pop_rows.empty else None
        lag = (pop_dt - t0["date"]).days if pop_dt is not None else None
        pop_ret = float(pop_rows.iloc[0]["return_1d_pct"]) if not pop_rows.empty else None
        rows.append(
            {
                "yahoo_symbol": sym,
                "episode_id": int(eid),
                "trigger_date": str(t0["date"].date()),
                "pop_date": str(pop_dt.date()) if pop_dt is not None else None,
                "trigger_to_pop_days": lag,
                "trigger_cs_rank": t0.get("cs_move_pct_rank"),
                "pop_return_1d_pct": pop_ret,
                "episode_days": int(len(g)),
                "max_fwd_5d_from_trigger_pct": t0.get("fwd_max_5d_pct"),
                "days_to_10pct_from_trigger": t0.get("days_to_10pct"),
                "hit_10pct_within_5d": int(t0.get("days_to_10pct") == t0.get("days_to_10pct") and (t0.get("days_to_10pct") or 99) <= 5),
            }
        )
    return pd.DataFrame(rows)


def movement_sort_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Sort all daily moves — distribution by name_type and by cross-section bucket."""
    sub = df[df["return_1d"].notna()].copy()
    out: dict[str, Any] = {"method": "daily_cross_section_move_sort", "n_obs": int(len(sub))}

    pctiles = [50, 75, 90, 95, 99]
    for nt in ("fry", "compounder", "standard"):
        r = sub.loc[sub["name_type"] == nt, "return_1d_pct"]
        if r.empty:
            continue
        out[f"pctiles_{nt}"] = {f"p{p}": round(float(np.percentile(r, p)), 3) for p in pctiles}

    # On each day, fry share of top-decile movers
    top = sub[sub["cs_move_top10"] == 1]
    if not top.empty:
        fry_share = float((top["name_type"] == "fry").mean())
        out["fry_share_of_daily_top10_movers"] = round(fry_share, 3)
        out["n_daily_top10_obs"] = int(len(top))

    # Forward pop after being top5 mover that day (path, not hold)
    top5 = sub[sub["cs_move_top5"] == 1]
    for nt in ("fry", "standard"):
        g = top5[top5["name_type"] == nt]
        if g.empty:
            continue
        out[f"top5_mover_{nt}"] = {
            "n": int(len(g)),
            "mean_fwd_max_5d_pct": round(float(g["fwd_max_5d"].mean() * 100), 3),
            "median_days_to_10pct": float(np.nanmedian(g["days_to_10pct"])),
            "pct_hit_10_within_5d": round(float((g["days_to_10pct"] <= 5).mean() * 100), 1),
        }
    return out


def trigger_pop_summary(episodes: pd.DataFrame) -> dict[str, Any]:
    if episodes.empty:
        return {"n_episodes": 0}
    pop_rate = float(episodes["pop_date"].notna().mean())
    return {
        "n_episodes": int(len(episodes)),
        "pct_with_pop": round(pop_rate * 100, 1),
        "median_trigger_to_pop_days": float(episodes["trigger_to_pop_days"].dropna().median())
        if episodes["trigger_to_pop_days"].notna().any()
        else None,
        "median_max_fwd_5d_from_trigger_pct": float(episodes["max_fwd_5d_from_trigger_pct"].median())
        if episodes["max_fwd_5d_from_trigger_pct"].notna().any()
        else None,
        "pct_hit_10_within_5d_from_trigger": round(float(episodes["hit_10pct_within_5d"].mean() * 100), 1),
        "by_trigger_cs_rank_bucket": _bucket_trigger_ranks(episodes),
    }


def _bucket_trigger_ranks(ep: pd.DataFrame) -> dict[str, Any]:
    g = ep[ep["trigger_cs_rank"].notna()].copy()
    if g.empty:
        return {}
    g["bucket"] = pd.cut(
        g["trigger_cs_rank"],
        bins=[0, 0.5, 0.8, 0.95, 1.0],
        labels=["low_move_day", "mid", "high", "top5pct_day"],
    )
    rows = []
    for b, grp in g.groupby("bucket", observed=True):
        rows.append(
            {
                "bucket": str(b),
                "n": int(len(grp)),
                "pct_pop": round(float(grp["pop_date"].notna().mean() * 100), 1),
                "median_fwd_5d_max": float(grp["max_fwd_5d_from_trigger_pct"].median()),
            }
        )
    return {"rows": rows}


def daily_calendar_heat(df: pd.DataFrame) -> pd.DataFrame:
    """Per calendar day: fry breadth among top movers."""

    def _day(g: pd.DataFrame) -> pd.Series:
        n_top10 = int(g["cs_move_top10"].sum())
        n_fry_top10 = int(((g["name_type"] == "fry") & (g["cs_move_top10"] == 1)).sum())
        return pd.Series(
            {
                "n_symbols": int(len(g)),
                "n_fry": int((g["name_type"] == "fry").sum()),
                "n_top10": n_top10,
                "n_fry_top10": n_fry_top10,
                "fry_top10_share": round(n_fry_top10 / n_top10, 3) if n_top10 else 0.0,
                "median_move_pct": float(g["return_1d_pct"].median()),
                "p90_move_pct": float(np.percentile(g["return_1d_pct"].dropna(), 90))
                if g["return_1d_pct"].notna().any()
                else np.nan,
            }
        )

    return df.groupby("date").apply(_day).reset_index()


def build_fry_episode_research(panel_path: Path | None = None, *, extend_from: str | None = None) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_daily_moves(panel_path, extend_from=extend_from)
    df = add_daily_cross_section_ranks(df)
    ep_days = detect_fry_episodes(df)
    ep_table = summarize_episode_table(ep_days)
    cal = daily_calendar_heat(df)

    df.to_parquet(OUT_DIR / "daily_cross_section.parquet", index=False)
    ep_days.to_parquet(OUT_DIR / "fry_episode_days.parquet", index=False)
    if not ep_table.empty:
        ep_table.to_parquet(OUT_DIR / "fry_episodes.parquet", index=False)
    cal.to_parquet(OUT_DIR / "daily_calendar_heat.parquet", index=False)

    summary = {
        "panel_rows": int(len(df)),
        "symbols": int(df["yahoo_symbol"].nunique()),
        "date_min": str(df["date"].min().date()),
        "date_max": str(df["date"].max().date()),
        "extend_from": extend_from,
        "panel_tiers": (
            df.groupby("panel_tier").size().to_dict() if "panel_tier" in df.columns else {}
        ),
        "movement_sort": movement_sort_summary(df),
        "trigger_pop": trigger_pop_summary(ep_table),
        "n_fry_episode_days": int(len(ep_days)),
        "n_episodes": int(len(ep_table)),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
