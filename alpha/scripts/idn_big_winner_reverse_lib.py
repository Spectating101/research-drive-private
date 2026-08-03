"""Winner-first reverse engineering — start from big gains, mine pre-entry patterns."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from idn_eval_splits import ERA_OOS, ERA_TRAIN, slice_era, split_meta, time_cutoff

TURNAROUND_PANEL = None  # set at import from repo bootstrap in caller

BIG_WIN_PCT = 20.0
HUGE_WIN_PCT = 30.0
TOP_DECILE_PCT = 90.0
EPISODE_GAP_DAYS = 20
MIN_PATTERN_FIRES = 25

CATEGORICAL_FEATURES = (
    "name_type",
    "ihsg_regime",
    "bandar_lite_label",
    "moon_phase_bucket",
)

BINARY_FEATURES = (
    "near_support_40d",
    "near_support_60d",
    "in_index_event_window",
    "is_ara_day",
)

NUMERIC_BUCKET_SPECS: tuple[tuple[str, tuple[float, ...]], ...] = (
    ("rsi14", (30.0, 40.0, 50.0)),
    ("dd_60d", (-0.20, -0.10, 0.0)),
    ("vol_ratio_20d", (1.0, 1.5, 2.5)),
    ("pos_52w_range", (0.25, 0.5, 0.75)),
    ("return_5d", (-0.10, -0.05, 0.0, 0.05)),
    ("quiet_acc_score_5d", (2.0, 3.0)),
    ("chase_score_5d", (1.0, 2.0)),
)


def _bucket_label(col: str, val: float, edges: tuple[float, ...]) -> str:
    if not np.isfinite(val):
        return f"{col}=na"
    if val < edges[0]:
        return f"{col}:x<{edges[0]:g}"
    for i in range(len(edges) - 1):
        if edges[i] <= val < edges[i + 1]:
            return f"{col}:{edges[i]:g}<=x<{edges[i + 1]:g}"
    return f"{col}:x>={edges[-1]:g}"


def label_big_winners(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    r = out["reward_20d_pct"]
    out["big_win_20"] = (r >= BIG_WIN_PCT).astype(int)
    out["huge_win_20"] = (r >= HUGE_WIN_PCT).astype(int)
    thr = float(r.quantile(TOP_DECILE_PCT / 100.0))
    out["top_decile_20"] = (r >= thr).astype(int)
    out["top_decile_threshold_pct"] = thr
    return out


def dedupe_winner_entries(df: pd.DataFrame, *, flag_col: str = "big_win_20") -> pd.DataFrame:
    """First day of each non-overlapping 20d winner run per symbol."""
    hits = df[df[flag_col] == 1].sort_values(["yahoo_symbol", "date"]).copy()
    if hits.empty:
        return hits
    keep: list[int] = []
    last_by_sym: dict[str, pd.Timestamp] = {}
    for idx, row in hits.iterrows():
        sym = str(row["yahoo_symbol"])
        dt = pd.Timestamp(row["date"])
        prev = last_by_sym.get(sym)
        if prev is None or (dt - prev).days >= EPISODE_GAP_DAYS:
            keep.append(idx)
            last_by_sym[sym] = dt
    return hits.loc[keep].copy()


def _pattern_rows(df: pd.DataFrame, *, target: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = float(df[target].mean()) if len(df) else 0.0
    n = len(df)

    for col in CATEGORICAL_FEATURES:
        if col not in df.columns:
            continue
        for val, grp in df.groupby(col, dropna=False):
            if len(grp) < MIN_PATTERN_FIRES:
                continue
            rate = float(grp[target].mean())
            rows.append(
                {
                    "pattern": f"{col}={val}",
                    "feature": col,
                    "value": str(val),
                    "n": int(len(grp)),
                    "big_win_rate_pct": round(rate * 100, 2),
                    "baseline_rate_pct": round(base * 100, 2),
                    "lift": round(rate / base, 3) if base > 0 else None,
                    "mean_reward_20d_pct": round(float(grp["reward_20d_pct"].mean()), 3),
                }
            )

    for col in BINARY_FEATURES:
        if col not in df.columns:
            continue
        for val in (1, 0):
            grp = df[df[col] == val]
            if len(grp) < MIN_PATTERN_FIRES:
                continue
            rate = float(grp[target].mean())
            rows.append(
                {
                    "pattern": f"{col}=={val}",
                    "feature": col,
                    "value": val,
                    "n": int(len(grp)),
                    "big_win_rate_pct": round(rate * 100, 2),
                    "baseline_rate_pct": round(base * 100, 2),
                    "lift": round(rate / base, 3) if base > 0 else None,
                    "mean_reward_20d_pct": round(float(grp["reward_20d_pct"].mean()), 3),
                }
            )

    for col, edges in NUMERIC_BUCKET_SPECS:
        if col not in df.columns:
            continue
        buckets = df[col].map(lambda x, c=col, e=edges: _bucket_label(c, float(x) if pd.notna(x) else float("nan"), e))
        for bval, grp in df.assign(_bucket=buckets).groupby("_bucket"):
            if len(grp) < MIN_PATTERN_FIRES:
                continue
            rate = float(grp[target].mean())
            rows.append(
                {
                    "pattern": str(bval),
                    "feature": col,
                    "value": str(bval),
                    "n": int(len(grp)),
                    "big_win_rate_pct": round(rate * 100, 2),
                    "baseline_rate_pct": round(base * 100, 2),
                    "lift": round(rate / base, 3) if base > 0 else None,
                    "mean_reward_20d_pct": round(float(grp["reward_20d_pct"].mean()), 3),
                }
            )

    rows.sort(key=lambda r: (-(r.get("lift") or 0), -r["n"]))
    return rows


def mine_patterns(df: pd.DataFrame, *, target: str = "big_win_20") -> dict[str, Any]:
    train = slice_era(df, ERA_TRAIN, time_col="date")
    oos = slice_era(df, ERA_OOS, time_col="date")
    train_rows = _pattern_rows(train, target=target)
    oos_rows = _pattern_rows(oos, target=target)
    oos_map = {r["pattern"]: r for r in oos_rows}

    merged: list[dict[str, Any]] = []
    for tr in train_rows[:80]:
        oo = oos_map.get(tr["pattern"], {})
        merged.append(
            {
                **tr,
                "oos_n": oo.get("n"),
                "oos_big_win_rate_pct": oo.get("big_win_rate_pct"),
                "oos_lift": oo.get("lift"),
                "oos_mean_reward_20d_pct": oo.get("mean_reward_20d_pct"),
                "stable": bool(
                    oo.get("lift") is not None
                    and tr.get("lift") is not None
                    and oo["lift"] >= 1.1
                    and tr["lift"] >= 1.1
                ),
            }
        )
    merged.sort(key=lambda r: (-(r.get("oos_lift") or r.get("lift") or 0), -r["n"]))
    return {
        "target": target,
        "train_patterns": train_rows[:40],
        "oos_patterns": oos_rows[:40],
        "ranked_stable": [r for r in merged if r.get("stable")][:25],
        "ranked_all": merged[:40],
    }


def winner_vs_control_summary(df: pd.DataFrame, entries: pd.DataFrame) -> list[dict[str, Any]]:
    """Same-day controls: symbols that did NOT big-win in next 20d."""
    if entries.empty:
        return []
    rows: list[dict[str, Any]] = []
    compare_cols = [
        "rsi14",
        "dd_60d",
        "vol_ratio_20d",
        "pos_52w_range",
        "return_5d",
        "quiet_acc_score_5d",
        "chase_score_5d",
    ]
    for dt, grp in entries.groupby("date"):
        day = df[df["date"] == dt]
        if len(day) < 30:
            continue
        winners = set(grp["yahoo_symbol"])
        ctrl = day[~day["yahoo_symbol"].isin(winners) & (day["big_win_20"] == 0)]
        win = day[day["yahoo_symbol"].isin(winners)]
        if len(ctrl) < 20 or win.empty:
            continue
        for col in compare_cols:
            if col not in day.columns:
                continue
            wmean = float(win[col].mean())
            cmean = float(ctrl[col].mean())
            rows.append(
                {
                    "date": str(pd.Timestamp(dt).date()),
                    "feature": col,
                    "winner_mean": round(wmean, 4),
                    "control_mean": round(cmean, 4),
                    "delta": round(wmean - cmean, 4),
                }
            )
    if not rows:
        return []
    out = pd.DataFrame(rows).groupby("feature", as_index=False).agg(
        mean_delta=("delta", "mean"),
        median_delta=("delta", "median"),
        n_days=("date", "nunique"),
    )
    out = out.sort_values("mean_delta", key=abs, ascending=False)
    return out.to_dict(orient="records")


def top_winner_episodes(entries: pd.DataFrame, *, n: int = 30) -> list[dict[str, Any]]:
    if entries.empty:
        return []
    cols = [
        "date",
        "yahoo_symbol",
        "name_type",
        "reward_20d_pct",
        "reward_5d_pct",
        "rsi14",
        "dd_60d",
        "bandar_lite_label",
        "ihsg_regime",
        "near_support_60d",
        "vol_ratio_20d",
        "quiet_acc_score_5d",
    ]
    use = [c for c in cols if c in entries.columns]
    top = entries.nlargest(n, "reward_20d_pct")[use]
    recs = []
    for row in top.to_dict(orient="records"):
        rec = {k: (str(v.date()) if k == "date" else v) for k, v in row.items()}
        recs.append(rec)
    return recs


def mechanism_hypotheses(patterns: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate top stable patterns into plain-language mechanisms."""
    hyps: list[dict[str, Any]] = []
    for p in patterns.get("ranked_stable", [])[:12]:
        pat = p["pattern"]
        text = pat
        if "rsi14" in pat and ("x<30" in pat or "<30" in pat):
            text = "Oversold RSI — mean-reversion entry before 20d squeeze"
        elif "dd_60d" in pat and ("x<-0.2" in pat or "<-0.2" in pat):
            text = "Deep 60d drawdown — capitulation washout then rebound"
        elif "bandar_lite_label=squeeze_from_drawdown" in pat:
            text = "Bandar-lite squeeze from drawdown — vol up after prior dump"
        elif "bandar_lite_label=quiet_volume_build" in pat:
            text = "Quiet volume build — flat price, rising volume (accumulation proxy)"
        elif "ihsg_regime=washout" in pat:
            text = "Index washout regime — beta bounce in oversold names"
        elif "near_support_60d==1" in pat:
            text = "At 60d support — retail support playbook"
        elif "name_type=fry" in pat:
            text = "Fry microcap — higher variance; size down, event-day timing"
        elif "name_type=compounder" in pat:
            text = "Compounder quality — support+RSI on liquid names"
        hyps.append(
            {
                "pattern": pat,
                "mechanism": text,
                "train_lift": p.get("lift"),
                "oos_lift": p.get("oos_lift"),
                "oos_mean_reward_20d_pct": p.get("oos_mean_reward_20d_pct"),
                "n_train": p.get("n"),
                "n_oos": p.get("oos_n"),
            }
        )
    return hyps


def build_extended_panel(min_date: str = "2019-07-01") -> pd.DataFrame:
    """Rich turnaround panel (2022+) plus price-derived features back to min_date."""
    import importlib.util as _ilu
    from pathlib import Path as _Path

    _bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
    _bmod = _ilu.module_from_spec(_bspec)
    _bspec.loader.exec_module(_bmod)
    repo = _bmod.repo_root_from_file(__file__)
    feat_path = repo / "data_lake/research_panels/idn_turnaround/daily_features.parquet"

    if feat_path.exists():
        rich = pd.read_parquet(feat_path)
        rich["date"] = pd.to_datetime(rich["date"])
        rich["panel_tier"] = "turnaround_full"
    else:
        rich = pd.DataFrame()

    from idn_episode_reward_lib import resolve_episode_universe
    from idn_name_type_lib import name_type_map, ensure_full_universe_snapshot
    from idn_panel_lib import load_idx_close_volume
    from idn_turnaround_lib import build_symbol_features, IHSG_REGIME

    snap = ensure_full_universe_snapshot()
    nt_map = name_type_map(snap)
    syms = resolve_episode_universe()
    close_all, vol_all = load_idx_close_volume(syms, min_date=min_date)

    if IHSG_REGIME.exists():
        tape = pd.read_parquet(IHSG_REGIME)
        tape.index = pd.to_datetime(tape.index)
    else:
        from idn_regime_lib import fetch_and_cache

        tape, _ = fetch_and_cache()
    ihsg = tape.rename(columns=lambda c: f"ihsg_{c}" if c != "label" else "ihsg_regime")

    rich_min = pd.Timestamp(rich["date"].min()) if not rich.empty else pd.Timestamp("2022-01-01")
    ext_start = pd.Timestamp(min_date)
    if ext_start >= rich_min:
        panel = rich
    else:
        parts: list[pd.DataFrame] = []
        use = [s for s in syms if s in close_all.columns]
        for sym in use:
            raw_close = close_all[sym]
            raw_vol = vol_all[sym]
            feat = build_symbol_features(raw_close, raw_vol, ihsg)
            feat = feat[(feat.index >= ext_start) & (feat.index < rich_min)]
            if feat.empty:
                continue
            for h in (5, 20):
                feat[f"reward_{h}d"] = raw_close.shift(-h) / raw_close - 1.0
            feat = feat.reset_index(names="date")
            feat["yahoo_symbol"] = sym
            feat["name_type"] = nt_map.get(sym, "standard")
            feat["reward_5d_pct"] = feat["reward_5d"] * 100
            feat["reward_20d_pct"] = feat["reward_20d"] * 100
            feat["panel_tier"] = "extended_price"
            parts.append(feat)
        extended = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        panel = pd.concat([extended, rich], ignore_index=True) if not extended.empty else rich

    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel.dropna(subset=["reward_20d_pct"])
    return panel.sort_values(["date", "yahoo_symbol"]).reset_index(drop=True)


def run_reverse_engineer(
  panel: pd.DataFrame,
  *,
  target: str = "big_win_20",
) -> dict[str, Any]:
    panel = label_big_winners(panel)
    entries = dedupe_winner_entries(panel, flag_col=target)
    split = split_meta(panel.groupby("date", as_index=False).first(), time_col="date", oos_frac=0.25)
    patterns = mine_patterns(panel, target=target)
    return {
        "split_meta": split,
        "panel_rows": int(len(panel)),
        "symbols": int(panel["yahoo_symbol"].nunique()),
        "date_min": str(panel["date"].min().date()),
        "date_max": str(panel["date"].max().date()),
        "panel_tiers": panel.get("panel_tier", pd.Series(["unknown"] * len(panel))).value_counts().to_dict(),
        "baseline_big_win_rate_pct": round(float(panel[target].mean() * 100), 2),
        "n_big_win_rows": int(panel[target].sum()),
        "n_deduped_episodes": int(len(entries)),
        "top_episodes": top_winner_episodes(entries, n=25),
        "winner_vs_control": winner_vs_control_summary(panel, entries),
        "patterns": patterns,
        "mechanisms": mechanism_hypotheses(patterns),
        "big_win_threshold_pct": BIG_WIN_PCT,
    }
