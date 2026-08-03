"""IDX shock / turnaround research — influencer methods decomposed into testable features.

Outputs feed run_idn_turnaround_research.py (parquet + JSON only).
"""

from __future__ import annotations

import json
import math
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
REGISTRY = REPO / "config/markets/idn_turnaround_registry.json"
DAILY_PANEL = REPO / "data_lake/markets/yfinance_asia/idn_idx_all_daily_panel.parquet"
LIQUID_PANEL = REPO / "data_lake/markets/yfinance_asia/idn_liquid_daily_panel.parquet"
IHSG_REGIME = REPO / "data_lake/markets/yfinance_asia/ihsg_regime_daily.parquet"
EVENTS_CFG = REPO / "config/markets/indonesia_index_events.json"
OUT_DIR = REPO / "data_lake/research_panels/idn_turnaround"

BANKS = frozenset({"BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK"})
LUNAR_CYCLE_DAYS = 29.530588853
KNOWN_NEW_MOON = pd.Timestamp("2000-01-06")


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def ara_limit_pct(price: float) -> float:
    """BEI daily upper limit (ARA) by price band."""
    if price < 200:
        return 0.35
    if price <= 5000:
        return 0.25
    return 0.20


def classify_ara_return(ret: float, price: float) -> str | None:
    lim = ara_limit_pct(price)
    if ret >= lim - 0.005:
        return f"ara_{int(lim * 100)}pct"
    if ret <= -lim + 0.005:
        return f"arb_{int(lim * 100)}pct"
    return None


def lunar_features(dt: pd.Timestamp) -> dict[str, float | int]:
    """Calendar moon features (testable; not causal astrology claim)."""
    age = (pd.Timestamp(dt).normalize() - KNOWN_NEW_MOON).days % LUNAR_CYCLE_DAYS
    days_since_new = int(round(age))
    days_since_full = int(round(abs(age - LUNAR_CYCLE_DAYS / 2)))
    days_to_new = int(round(min(age, LUNAR_CYCLE_DAYS - age)))
    phase = age / LUNAR_CYCLE_DAYS
    bucket = "new_moon" if phase < 0.07 or phase > 0.93 else "full_moon" if 0.43 < phase < 0.57 else "mid_cycle"
    return {
        "lunar_age_days": days_since_new,
        "days_since_new_moon": days_since_new,
        "days_since_full_moon": days_since_full,
        "days_to_new_moon": days_to_new,
        "moon_phase_bucket": bucket,
    }


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _support_resistance_proximity(close: pd.Series, lookback: int) -> pd.DataFrame:
    low = close.rolling(lookback, min_periods=max(10, lookback // 3)).min()
    high = close.rolling(lookback, min_periods=max(10, lookback // 3)).max()
    dist_sup = close / low - 1.0
    dist_res = high / close - 1.0
    return pd.DataFrame(
        {
            f"dist_support_{lookback}d": dist_sup,
            f"dist_resistance_{lookback}d": dist_res,
            f"near_support_{lookback}d": (dist_sup <= 0.02).astype(int),
            f"near_resistance_{lookback}d": (dist_res <= 0.02).astype(int),
            f"low_{lookback}d": low,
            f"high_{lookback}d": high,
        },
        index=close.index,
    )


def _pos_in_52w_range(close: pd.Series) -> pd.Series:
    lo = close.rolling(252, min_periods=60).min()
    hi = close.rolling(252, min_periods=60).max()
    span = (hi - lo).replace(0, np.nan)
    return (close - lo) / span


def _consecutive_ara(rets: pd.Series, prices: pd.Series) -> pd.Series:
    out = []
    streak = 0
    for r, p in zip(rets, prices, strict=True):
        if pd.isna(r) or pd.isna(p):
            out.append(0)
            streak = 0
            continue
        if classify_ara_return(float(r), float(p)) and str(classify_ara_return(float(r), float(p))).startswith("ara"):
            streak += 1
        else:
            streak = 0
        out.append(streak)
    return pd.Series(out, index=rets.index)


def load_index_events() -> list[dict]:
    if not EVENTS_CFG.exists():
        return []
    return json.loads(EVENTS_CFG.read_text(encoding="utf-8")).get("events", [])


def event_window_flags(dates: pd.Series) -> pd.DataFrame:
    events = load_index_events()
    in_window = pd.Series(False, index=dates.index)
    event_ids: list[str | None] = []
    days_since: list[int | None] = []
    for d in dates:
        hit = False
        eid = None
        ds = None
        for ev in events:
            eff = ev.get("effective_date")
            if not eff:
                continue
            eff_ts = pd.Timestamp(eff)
            start = eff_ts - pd.Timedelta(days=7)
            end = eff_ts + pd.Timedelta(days=5)
            if start <= pd.Timestamp(d) <= end:
                hit = True
                eid = ev.get("id")
                ds = int((pd.Timestamp(d) - eff_ts).days)
                break
        in_window.loc[d] = hit
        event_ids.append(eid)
        days_since.append(ds)
    return pd.DataFrame(
        {"in_index_event_window": in_window.astype(int), "index_event_id": event_ids, "days_from_event_effective": days_since},
        index=dates.index,
    )


def build_symbol_features(close: pd.Series, volume: pd.Series, ihsg: pd.DataFrame) -> pd.DataFrame:
    """Daily feature panel for one symbol."""
    c = close.dropna()
    v = volume.reindex(c.index)
    r = c.pct_change()
    df = pd.DataFrame(index=c.index)
    df["close"] = c
    df["return_1d"] = r
    df["return_5d"] = c.pct_change(5)
    df["rsi14"] = _rsi(c, 14)
    df["dd_60d"] = c / c.rolling(60, min_periods=20).max() - 1.0
    df["pos_52w_range"] = _pos_in_52w_range(c)
    df["vol_ratio_20d"] = v / v.rolling(20, min_periods=5).mean()
    up = r > 0
    down = r < 0
    vol_up = v.where(up).rolling(5, min_periods=2).sum()
    vol_down = v.where(down).rolling(5, min_periods=2).sum()
    df["vol_ratio_up_down_5d"] = vol_up / vol_down.replace(0, np.nan)

    for lb in (40, 60):
        df = df.join(_support_resistance_proximity(c, lb))

    df["consecutive_ara_days"] = _consecutive_ara(r, c)
    df["is_ara_day"] = [
        1 if classify_ara_return(float(x), float(p)) and str(classify_ara_return(float(x), float(p))).startswith("ara") else 0
        for x, p in zip(r, c, strict=True)
    ]

    lunar = pd.DataFrame([lunar_features(d) for d in c.index], index=c.index)
    # moon_phase_bucket as string — keep numeric cols only in main df
    df["days_since_new_moon"] = lunar["days_since_new_moon"]
    df["days_to_new_moon"] = lunar["days_to_new_moon"]
    df["moon_phase_bucket"] = lunar["moon_phase_bucket"]

    ev = event_window_flags(pd.Series(c.index, index=c.index))
    df = df.join(ev)
    df = df.join(ihsg, how="left")

    # bandar_lite on spike-candidate days only (expensive); label quiet/chase on all days via simplified proxy
    quiet = ((df["vol_ratio_20d"] >= 1.25) & (r.abs() <= 0.03)).astype(int)
    chase = ((df["vol_ratio_20d"] >= 1.5) & (r > 0.03)).astype(int)
    df["quiet_acc_score_5d"] = quiet.rolling(5, min_periods=3).sum()
    df["chase_score_5d"] = chase.rolling(5, min_periods=3).sum()
    prior_5d = c.pct_change(5)
    labels = []
    for q, ch, p5 in zip(df["quiet_acc_score_5d"], df["chase_score_5d"], prior_5d, strict=True):
        if q >= 3 and (pd.isna(p5) or p5 < 0.08):
            labels.append("quiet_volume_build")
        elif ch >= 2 and (not pd.isna(p5) and p5 >= 0.12):
            labels.append("chase_into_spike")
        elif not pd.isna(p5) and p5 >= 0.15:
            labels.append("momentum_chase")
        elif not pd.isna(p5) and p5 <= -0.08:
            labels.append("squeeze_from_drawdown")
        else:
            labels.append("unclear")
    df["bandar_lite_label"] = labels

    for h in (5, 20):
        df[f"reward_{h}d"] = c.shift(-h) / c - 1.0
        df[f"reward_{h}d_pct"] = df[f"reward_{h}d"] * 100

    return df


def detect_turn_events(feat: pd.DataFrame, *, name_type: str = "standard") -> pd.DataFrame:
    """Label floor/ceiling candidate days from structure + shocks."""
    r = feat["return_1d"]
    rows: list[dict[str, Any]] = []

    for i in range(5, len(feat) - 5):
        dt = feat.index[i]
        window = feat.iloc[i - 5 : i + 6]
        ret_1d = float(r.iloc[i]) if pd.notna(r.iloc[i]) else 0.0
        local_min = float(window["close"].iloc[:6].min()) == float(feat["close"].iloc[i])
        local_max = float(window["close"].iloc[:6].max()) == float(feat["close"].iloc[i])
        fwd5 = float(feat["reward_5d"].iloc[i]) if pd.notna(feat["reward_5d"].iloc[i]) else np.nan

        shock_tags: list[str] = []
        if ret_1d <= -0.05:
            shock_tags.append("shock_down")
        if ret_1d >= 0.08:
            shock_tags.append("shock_up")
        ara = classify_ara_return(ret_1d, float(feat["close"].iloc[i]))
        if ara:
            shock_tags.append(ara)

        turn_type = None
        if local_min and (feat.get("near_support_60d", pd.Series(0)).iloc[i] == 1 or feat["rsi14"].iloc[i] < 38):
            turn_type = "floor_candidate"
        elif local_max and (
            feat.get("near_resistance_60d", pd.Series(0)).iloc[i] == 1
            or int(feat.get("consecutive_ara_days", pd.Series(0)).iloc[i]) >= 2
        ):
            turn_type = "ceiling_candidate"
        elif shock_tags and abs(ret_1d) >= 0.08:
            turn_type = "shock"

        if turn_type is None:
            continue

        row = {
            "date": dt,
            "turn_type": turn_type,
            "shock_tags": shock_tags,
            "return_1d_pct": round(ret_1d * 100, 2),
            "reward_5d_pct": round(fwd5 * 100, 2) if np.isfinite(fwd5) else None,
            "name_type": name_type,
        }
        for col in (
            "rsi14",
            "dd_60d",
            "pos_52w_range",
            "near_support_60d",
            "near_resistance_60d",
            "ihsg_regime",
            "in_index_event_window",
            "consecutive_ara_days",
            "bandar_lite_label",
            "days_since_new_moon",
        ):
            if col in feat.columns:
                val = feat[col].iloc[i]
                row[col] = None if pd.isna(val) else (float(val) if isinstance(val, (float, np.floating)) else val)
        rows.append(row)

    return pd.DataFrame(rows)


def _match_conditions(
    row: pd.Series,
    cond: dict[str, Any],
    symbol: str,
    *,
    liquid_core: frozenset[str],
) -> bool:
    if "symbol_scope" in cond:
        scope = cond["symbol_scope"]
        if scope == "banks" and symbol not in liquid_core:
            return False
        if scope == "compounders" and row.get("name_type") != "compounder":
            return False
    if "name_type" in cond and row.get("name_type") != cond["name_type"]:
        return False
    if cond.get("near_support_60d") and not row.get("near_support_60d"):
        return False
    if cond.get("near_support_40d") and not row.get("near_support_40d"):
        return False
    if cond.get("near_resistance_60d") and not row.get("near_resistance_60d"):
        return False
    if "rsi14_max" in cond and (row.get("rsi14") is None or row["rsi14"] > cond["rsi14_max"]):
        return False
    if "return_1d_min" in cond and (row.get("return_1d") is None or row["return_1d"] < cond["return_1d_min"]):
        return False
    if "return_5d_min" in cond and (row.get("return_5d") is None or row["return_5d"] < cond["return_5d_min"]):
        return False
    if "pos_52w_range_max" in cond and (row.get("pos_52w_range") is None or row["pos_52w_range"] > cond["pos_52w_range_max"]):
        return False
    if "vol_ratio_20d_min" in cond and (row.get("vol_ratio_20d") is None or row["vol_ratio_20d"] < cond["vol_ratio_20d_min"]):
        return False
    if "dd_60d_max" in cond and (row.get("dd_60d") is None or row["dd_60d"] > cond["dd_60d_max"]):
        return False
    if "consecutive_ara_days_min" in cond:
        if (row.get("consecutive_ara_days") or 0) < cond["consecutive_ara_days_min"]:
            return False
    if "in_index_event_window" in cond and bool(cond["in_index_event_window"]) != bool(row.get("in_index_event_window")):
        return False
    if "ihsg_regime_in" in cond:
        if row.get("ihsg_regime") not in cond["ihsg_regime_in"]:
            return False
    if "days_since_new_moon_max" in cond:
        d = row.get("days_since_new_moon")
        if d is None or d > cond["days_since_new_moon_max"]:
            return False
    if "bandar_lite_label_in" in cond:
        if row.get("bandar_lite_label") not in cond["bandar_lite_label_in"]:
            return False
    if "bandar_lite_label_not_in" in cond:
        if row.get("bandar_lite_label") in cond["bandar_lite_label_not_in"]:
            return False
    if "vol_ratio_up_down_lt" in cond:
        v = row.get("vol_ratio_up_down_5d")
        if v is None or not (v < cond["vol_ratio_up_down_lt"]):
            return False
    return True


def _liquid_core_for_panel(panel: pd.DataFrame) -> frozenset[str]:
    if panel.attrs.get("liquid_core"):
        return frozenset(panel.attrs["liquid_core"])
    snap_path = REPO / "data_lake/research_panels/idn_name_types/latest.json"
    if snap_path.exists():
        data = json.loads(snap_path.read_text(encoding="utf-8"))
        core = data.get("liquid_core_symbols") or []
        if core:
            return frozenset(core)
    comps = panel.loc[panel["name_type"] == "compounder", "yahoo_symbol"].dropna().unique()
    return frozenset(comps[:3])


def apply_signal_rules(panel: pd.DataFrame, registry: dict[str, Any] | None = None) -> pd.DataFrame:
    """Tag each row with which signal_rules fire."""
    reg = registry or load_registry()
    rules = reg.get("signal_rules", [])
    liquid_core = _liquid_core_for_panel(panel)
    out = panel.copy()
    for rule in rules:
        rid = rule["id"]
        nt_filter = rule.get("name_type_filter")
        hits = []
        for _, row in panel.iterrows():
            sym = str(row["yahoo_symbol"])
            if nt_filter and row.get("name_type") not in nt_filter:
                hits.append(0)
                continue
            hits.append(
                1
                if _match_conditions(row, rule.get("conditions", {}), sym, liquid_core=liquid_core)
                else 0
            )
        out[f"sig_{rid}"] = hits
    out.attrs["liquid_core"] = list(liquid_core)
    return out


def evaluate_signals(panel: pd.DataFrame, registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    from idn_eval_splits import ERA_OOS, slice_era, split_meta
    from idn_signal_stats import benjamini_hochberg, mean_return_inference, verdict_from_stats

    reg = registry or load_registry()
    if "week_end" not in panel.columns:
        panel = panel.copy()
        panel["week_end"] = pd.to_datetime(panel["date"]).dt.to_period("W-FRI").dt.to_timestamp("W-FRI")

    oos = slice_era(panel, ERA_OOS, time_col="date")

    results: list[dict[str, Any]] = []
    oos_p_floor: list[tuple[str, float]] = []

    for rule in reg.get("signal_rules", []):
        rid = rule["id"]
        col = f"sig_{rid}"
        if col not in panel.columns:
            continue
        for era_name, sub in [("full", panel), ("oos_holdout", oos)]:
            fired = sub[sub[col] == 1]
            if len(fired) < 3:
                results.append(
                    {
                        "signal_id": rid,
                        "era": era_name,
                        "n_fires": int(len(fired)),
                        "verdict": "insufficient",
                        "school_ids": rule.get("school_ids"),
                        "turn_type": rule.get("turn_type"),
                    }
                )
                continue
            r5 = fired["reward_5d_pct"].dropna()
            r20 = fired["reward_20d_pct"].dropna()
            stats5 = mean_return_inference(r5)
            stats20 = mean_return_inference(r20)
            mean5 = stats5.get("mean_pct") if stats5.get("sufficient") else None
            mean20 = stats20.get("mean_pct") if stats20.get("sufficient") else None
            win5 = float((r5 > 0).mean()) if len(r5) else None
            verdict = verdict_from_stats(
                turn_type=str(rule.get("turn_type", "")),
                mean5=mean5,
                win5=win5,
                stats5=stats5,
                era=era_name,
            )
            row: dict[str, Any] = {
                "signal_id": rid,
                "era": era_name,
                "n_fires": int(len(fired)),
                "n_symbols": int(fired["yahoo_symbol"].nunique()),
                "mean_reward_5d_pct": round(mean5, 3) if mean5 is not None else None,
                "mean_reward_20d_pct": round(mean20, 3) if mean20 is not None else None,
                "win_rate_5d_pct": round(win5 * 100, 1) if win5 is not None else None,
                "stats_5d": stats5,
                "stats_20d": stats20,
                "verdict": verdict,
                "school_ids": rule.get("school_ids"),
                "turn_type": rule.get("turn_type"),
                "hold_days": rule.get("hold_days"),
                "notes": rule.get("notes"),
            }
            if era_name == "oos_holdout" and "name_type" in fired.columns:
                by_nt: dict[str, Any] = {}
                for nt, grp in fired.groupby("name_type"):
                    st = mean_return_inference(grp["reward_5d_pct"])
                    by_nt[str(nt)] = {
                        "n_fires": int(len(grp)),
                        "mean_reward_5d_pct": st.get("mean_pct"),
                        "stats_5d": st,
                    }
                row["by_name_type"] = by_nt
                if rule.get("turn_type") == "floor" and stats5.get("p_value_two_sided") is not None:
                    oos_p_floor.append((rid, float(stats5["p_value_two_sided"])))
            results.append(row)

    if oos_p_floor:
        keys = [k for k, _ in oos_p_floor]
        ps = [p for _, p in oos_p_floor]
        fdr = benjamini_hochberg(keys, ps)
        for row in results:
            if row.get("era") == "oos_holdout" and row.get("signal_id") in fdr:
                row["fdr_q_value"] = fdr[row["signal_id"]]
    return results


def build_turnaround_panel(liquid: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    from idn_name_type_lib import ensure_full_universe_snapshot, liquid_core_from_snapshot, name_type_map
    from idn_episode_reward_lib import resolve_episode_universe

    snap = ensure_full_universe_snapshot()
    nt_map = name_type_map(snap)
    liquid_core = liquid_core_from_snapshot(snap)

    syms = resolve_episode_universe(liquid)
    from idn_panel_lib import load_idx_close_volume, panel_manifest

    close_all, vol_all = load_idx_close_volume(syms)
    use = [s for s in syms if s in close_all.columns]
    panel_info = panel_manifest()

    if IHSG_REGIME.exists():
        tape = pd.read_parquet(IHSG_REGIME)
        tape.index = pd.to_datetime(tape.index)
    else:
        from idn_regime_lib import fetch_and_cache

        tape, _ = fetch_and_cache()
    ihsg = tape.rename(columns=lambda c: f"ihsg_{c}" if c != "label" else "ihsg_regime")

    parts: list[pd.DataFrame] = []
    events: list[pd.DataFrame] = []
    for sym in use:
        feat = build_symbol_features(close_all[sym], vol_all[sym], ihsg)
        feat["yahoo_symbol"] = sym
        feat["name_type"] = nt_map.get(sym, "standard")
        feat = feat.reset_index(names="date")
        parts.append(feat)
        ev = detect_turn_events(feat.set_index("date"), name_type=nt_map.get(sym, "standard"))
        if not ev.empty:
            ev["yahoo_symbol"] = sym
            events.append(ev)

    panel = pd.concat(parts, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    panel.attrs["liquid_core"] = liquid_core
    panel.attrs["panel_manifest"] = panel_info
    turn_events = pd.concat(events, ignore_index=True) if events else pd.DataFrame()
    return panel, turn_events


def build_case_book(panel: pd.DataFrame, registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Enrich annotated_cases from registry with observed features."""
    reg = registry or load_registry()
    cases: list[dict[str, Any]] = []
    for spec in reg.get("annotated_cases", []):
        sym = spec["symbol"]
        sub = panel[panel["yahoo_symbol"] == sym].copy()
        if sub.empty:
            cases.append({**spec, "status": "no_panel_data"})
            continue
        if "date_claimed" in spec:
            row = sub[sub["date"] == pd.Timestamp(spec["date_claimed"])]
        else:
            w0 = pd.Timestamp(spec.get("window_start", sub["date"].min()))
            w1 = pd.Timestamp(spec.get("window_end", sub["date"].max()))
            row = sub[(sub["date"] >= w0) & (sub["date"] <= w1)]
        if row.empty:
            cases.append({**spec, "status": "window_empty"})
            continue
        pivot = row.loc[row["return_1d"].idxmax()] if len(row) > 1 else row.iloc[0]
        cases.append(
            {
                **spec,
                "status": "ok",
                "observed": {
                    "best_rebound_date": str(pivot["date"].date()),
                    "return_1d_pct": round(float(pivot["return_1d"]) * 100, 2),
                    "rsi14": round(float(pivot["rsi14"]), 1) if pd.notna(pivot["rsi14"]) else None,
                    "near_support_60d": int(pivot.get("near_support_60d", 0)),
                    "ihsg_regime": pivot.get("ihsg_regime"),
                    "in_index_event_window": int(pivot.get("in_index_event_window", 0)),
                    "bandar_lite_label": pivot.get("bandar_lite_label"),
                    "days_since_new_moon": int(pivot.get("days_since_new_moon", -1)),
                },
                "window_stats": {
                    "n_days": int(len(row)),
                    "mean_reward_5d_pct": round(float(row["reward_5d_pct"].mean()), 2)
                    if row["reward_5d_pct"].notna().any()
                    else None,
                    "max_return_1d_pct": round(float(row["return_1d"].max()) * 100, 2),
                },
            }
        )
    return cases


def confluence_matrix(panel: pd.DataFrame, turn_events: pd.DataFrame) -> dict[str, Any]:
    """Layer hit-rates on detected turn events (floor vs ceiling)."""
    if turn_events.empty:
        return {"by_turn_type": {}}
    te = turn_events.copy()
    if "near_support_60d" not in te.columns:
        te = te.merge(
            panel[["date", "yahoo_symbol", "near_support_60d", "near_resistance_60d", "rsi14", "ihsg_regime", "in_index_event_window", "bandar_lite_label", "consecutive_ara_days", "pos_52w_range"]],
            on=["date", "yahoo_symbol"],
            how="left",
        )
    merged = te
    out: dict[str, Any] = {}
    for tt in ("floor_candidate", "ceiling_candidate", "shock"):
        sub = merged[merged["turn_type"] == tt]
        if sub.empty:
            continue
        out[tt] = {
            "n": int(len(sub)),
            "mean_reward_5d_pct": round(float(sub["reward_5d_pct"].mean()), 3) if sub["reward_5d_pct"].notna().any() else None,
            "pct_near_support_60d": round(float(sub["near_support_60d"].fillna(0).mean()) * 100, 1),
            "pct_near_resistance_60d": round(float(sub["near_resistance_60d"].fillna(0).mean()) * 100, 1),
            "pct_rsi_oversold": round(float((sub["rsi14"] < 35).mean()) * 100, 1),
            "pct_in_event_window": round(float(sub["in_index_event_window"].fillna(0).mean()) * 100, 1),
            "pct_ara_streak_2plus": round(float((sub["consecutive_ara_days"].fillna(0) >= 2).mean()) * 100, 1),
            "top_regimes": sub["ihsg_regime"].value_counts().head(4).to_dict(),
            "top_bandar_labels": sub["bandar_lite_label"].value_counts().head(4).to_dict(),
        }
    return {"by_turn_type": out}


def signal_follow_guide(eval_results: list[dict[str, Any]], registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Actionable ranking: what to follow on holdout."""
    reg = registry or load_registry()
    oos = [r for r in eval_results if r.get("era") == "oos_holdout" and r.get("n_fires", 0) >= 5]
    follow_floor = sorted(
        [r for r in oos if r.get("turn_type") == "floor" and r.get("verdict") in ("follow", "monitor")],
        key=lambda x: -(x.get("mean_reward_5d_pct") or -999),
    )
    follow_ceiling = sorted(
        [r for r in oos if r.get("turn_type") == "ceiling" and r.get("verdict") in ("follow_fade", "monitor")],
        key=lambda x: (x.get("mean_reward_5d_pct") or 999),
    )
    return {
        "generated_from": "oos_holdout_eval",
        "primary_floor_signals": follow_floor[:5],
        "primary_ceiling_signals": follow_ceiling[:5],
        "schools_catalog": [{k: s[k] for k in ("id", "name", "core_claim", "actionable_for_us")} for s in reg.get("schools", [])],
        "decision_checklist": [
            "1. Classify name: compounder vs fry (different ceiling/floor rules).",
            "2. Check ihsg_regime (washout/recovery vs extended_bounce).",
            "3. Floor: support zone + RSI + event exhaustion + optional moon window.",
            "4. Ceiling: ARA streak / resistance / dist volume divergence / extended bounce.",
            "5. Confirm with flow when available (broker summary > bandar_lite proxy).",
            "6. Size small; evaluate conditional reward on holdout not full-sample Sharpe.",
        ],
        "reject_on_holdout": [r["signal_id"] for r in oos if r.get("verdict") == "reject"],
        "significant_oos_floor": [
            r["signal_id"]
            for r in oos
            if r.get("turn_type") == "floor"
            and (r.get("stats_5d") or {}).get("significant_5pct")
            and (r.get("stats_5d") or {}).get("ci_excludes_zero")
        ],
        "key_findings": [
            "Eval uses full tradable IDX universe (~630+ names), not liquid-50 only.",
            "OOS verdicts require p<0.05, bootstrap CI excluding 0, and n≥30 for follow.",
            "Floor turns cluster at support+RSI (see confluence_matrix).",
            "Split by name_type on each rule — compounder vs fry edges differ sharply.",
            "BH-FDR q-values attached to floor rules on holdout (multiple-testing aware).",
        ],
    }
