"""Fry signal backtest — classification accuracy vs random + strategy P&L paths.

Answers:
  - If we guess pop using our rules, how accurate vs random baselines?
  - If we trade trigger/pop paths, what P&L vs random fry controls?
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
FRY_DIR = REPO / "data_lake/research_panels/idn_fry_episode"
TURNAROUND = REPO / "data_lake/research_panels/idn_turnaround/daily_features.parquet"
OUT_DIR = REPO / "backtests/outputs/idn_fry_backtest"

OOS_START = pd.Timestamp("2024-01-01")
POP_RET_MIN = 0.08
SINK_RET_MIN = -0.08
HORIZON = 30
N_PERM = 2000
N_RANDOM_TRIALS = 500
TX_COST_BPS = 15  # round-trip IDX microcap friction proxy


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    return (max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom))


def _cls_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    y_true = y_true.astype(bool)
    y_pred = y_pred.astype(bool)
    n = int(len(y_true))
    if n == 0:
        return {"n": 0}
    tp = int((y_true & y_pred).sum())
    fp = int((~y_true & y_pred).sum())
    fn = int((y_true & ~y_pred).sum())
    tn = int((~y_true & ~y_pred).sum())
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    acc = (tp + tn) / n
    base = float(y_true.mean())
    lo, hi = wilson_ci(tp, tp + fp) if (tp + fp) else (0.0, 0.0)
    return {
        "n": n,
        "n_predicted_positive": int(y_pred.sum()),
        "base_rate_pct": round(base * 100, 2),
        "accuracy_pct": round(acc * 100, 2),
        "precision_pct": round(prec * 100, 2),
        "recall_pct": round(rec * 100, 2),
        "f1": round(f1, 3),
        "precision_wilson_ci": [round(lo * 100, 2), round(hi * 100, 2)],
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def load_research_frame() -> pd.DataFrame:
    from idn_fry_frame_lib import load_fry_research_frame

    return load_fry_research_frame(with_broker=True)


def signal_rules() -> dict[str, Callable[[pd.DataFrame], pd.Series]]:
    from idn_fry_frame_lib import structural_signal_rules

    rules: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
        "always_guess_pop": lambda d: pd.Series(True, index=d.index),
        "never_guess": lambda d: pd.Series(False, index=d.index),
        "random_base_rate_ins": lambda d: _random_base_rate_mask(d, era="ins"),
        "T0_any_trigger": lambda d: pd.Series(True, index=d.index),
        "T1_deep_dd_vol": lambda d: (d["return_5d"] <= -0.08) & (d["vol_ratio_20d"] >= 1.6),
        "T2_deep_dd_12": lambda d: d["return_5d"] <= -0.12,
        "T3_hot_prior": lambda d: (d["return_5d"] <= -0.08)
        & (d["vol_ratio_20d"] >= 1.6)
        & (d["sym_prior_wf"] >= 0.25),
        "T4_exclude_dead": lambda d: (d["return_5d"] <= -0.08)
        & (d["vol_ratio_20d"] >= 1.6)
        & (~d["is_dead_name_wf"]),
        "anti_quiet_only": lambda d: d.get("trigger_cause", pd.Series(dtype=str)) != "quiet_accumulation",
        "T1_not_quiet_only": lambda d: (d["return_5d"] <= -0.08)
        & (d["vol_ratio_20d"] >= 1.6)
        & (d.get("trigger_cause", pd.Series(dtype=str)) != "quiet_accumulation"),
        "predict_sink_bad": lambda d: (d["return_5d"] <= -0.12)
        | (d.get("trigger_cause", pd.Series(dtype=str)) == "quiet_accumulation"),
    }
    rules.update(structural_signal_rules())
    return rules


def _random_base_rate_mask(df: pd.DataFrame, era: str = "ins") -> pd.Series:
    """Bernoulli guess at in-sample pop rate (leaky if used on ins — for oos use oos base)."""
    ins = df[df["era"] == era]
    p = float(ins["label_pop_30d"].mean()) if len(ins) else 0.22
    rng = np.random.default_rng(42)
    return pd.Series(rng.random(len(df)) < p, index=df.index)


def random_matched_guess(df: pd.DataFrame, rule_mask: pd.Series, label_col: str, seed: int = 0) -> np.ndarray:
    """Pick same # positives as rule, random rows — Monte Carlo guess."""
    n_pos = int(rule_mask.sum())
    if n_pos == 0:
        return np.zeros(len(df), dtype=bool)
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(df), size=n_pos, replace=False)
    pred = np.zeros(len(df), dtype=bool)
    pred[idx] = True
    return pred


def permutation_p_value(rule_prec: float, y_true: np.ndarray, rule_mask: np.ndarray, n_perm: int = N_PERM) -> float:
    """How often random matched-guess precision >= rule precision."""
    if rule_mask.sum() == 0:
        return 1.0
    beats = 0
    for i in range(n_perm):
        pred = random_matched_guess(
            pd.DataFrame(index=range(len(y_true))),
            pd.Series(rule_mask),
            "",
            seed=i,
        )
        tp = (y_true & pred).sum()
        prec = tp / pred.sum() if pred.sum() else 0
        if prec >= rule_prec:
            beats += 1
    return beats / n_perm


def classification_backtest(df: pd.DataFrame) -> dict[str, Any]:
    rules = signal_rules()
    label_cols = {
        "pop_12d_fsm": "label_pop_12d",
        "pop_30d": "label_pop_30d",
        "pop_first_path": "label_pop_first",
        "bad_down_sink_grind": "label_bad_down",
    }
    rows: list[dict[str, Any]] = []
    random_rows: list[dict[str, Any]] = []

    for era in ("all", "ins", "oos"):
        sub = df if era == "all" else df[df["era"] == era]
        if sub.empty:
            continue
        base_pop30 = float(sub["label_pop_30d"].mean())

        for rule_id, fn in rules.items():
            if rule_id.startswith("random"):
                continue
            mask = fn(sub).fillna(False)
            for label_name, label_col in label_cols.items():
                y = sub[label_col].to_numpy(dtype=bool)
                m = _cls_metrics(y, mask.to_numpy())
                m.update({"rule_id": rule_id, "label": label_name, "era": era})
                if m["n_predicted_positive"] > 0:
                    m["lift_vs_base_rate"] = round(m["precision_pct"] / max(base_pop30 * 100, 0.01), 3)
                    m["perm_p_value_precision"] = round(
                        permutation_p_value(m["precision_pct"] / 100, y, mask.to_numpy()), 4
                    )
                rows.append(m)

        # Random baselines for pop_30d OOS
        y30 = sub["label_pop_30d"].to_numpy(dtype=bool)
        n = len(sub)
        rng = np.random.default_rng(99)

        # Bernoulli at base rate
        bern_precs = []
        for _ in range(N_RANDOM_TRIALS):
            pred = rng.random(n) < base_pop30
            tp = (y30 & pred).sum()
            bern_precs.append(tp / pred.sum() if pred.sum() else 0)
        random_rows.append(
            {
                "baseline": "bernoulli_base_rate",
                "era": era,
                "label": "pop_30d",
                "base_rate_pct": round(base_pop30 * 100, 2),
                "mean_precision_pct": round(float(np.mean(bern_precs)) * 100, 2),
                "p95_precision_pct": round(float(np.percentile(bern_precs, 95)) * 100, 2),
            }
        )

        # Matched-n to T1
        t1_mask = rules["T1_deep_dd_vol"](sub).fillna(False)
        matched_precs = []
        for i in range(N_RANDOM_TRIALS):
            pred = random_matched_guess(sub, t1_mask, "label_pop_30d", seed=i)
            tp = (y30 & pred).sum()
            matched_precs.append(tp / pred.sum() if pred.sum() else 0)
        t1_row = next((r for r in rows if r.get("rule_id") == "T1_deep_dd_vol" and r.get("label") == "pop_30d" and r.get("era") == era), None)
        random_rows.append(
            {
                "baseline": "random_matched_n_t1",
                "era": era,
                "label": "pop_30d",
                "n_signals": int(t1_mask.sum()),
                "mean_precision_pct": round(float(np.mean(matched_precs)) * 100, 2),
                "p95_precision_pct": round(float(np.percentile(matched_precs, 95)) * 100, 2),
                "t1_rule_precision_pct": t1_row.get("precision_pct") if t1_row else None,
                "t1_beats_random_pct_trials": round(
                    float(np.mean([1 if t1_row and p <= (t1_row.get("precision_pct", 0) / 100) else 0 for p in matched_precs])) * 100, 1
                )
                if t1_row
                else None,
            }
        )

    return {"rule_metrics": rows, "random_baselines": random_rows}


def _load_price_panel() -> pd.DataFrame:
    cols = ["date", "yahoo_symbol", "close", "return_1d"]
    df = pd.read_parquet(TURNAROUND, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _trade_return(close: pd.Series, entry_i: int, exit_i: int, cost: float = TX_COST_BPS / 10000) -> float | None:
    if entry_i < 0 or exit_i >= len(close) or entry_i >= exit_i:
        return None
    c0 = close.iloc[entry_i]
    c1 = close.iloc[exit_i]
    if pd.isna(c0) or pd.isna(c1) or c0 <= 0:
        return None
    return float(c1 / c0 - 1.0 - cost)


def strategy_backtest(df: pd.DataFrame, panel: pd.DataFrame) -> dict[str, Any]:
    """P&L paths on T1-filtered episodes vs random fry controls."""
    rules = signal_rules()
    t1 = df[rules["T1_deep_dd_vol"](df).fillna(False)].copy()
    trades: dict[str, list[float]] = {
        "S1_hold_5d_from_trigger": [],
        "S2_hold_30d_from_trigger": [],
        "S3_exit_on_pop_or_30d": [],
        "S4_oracle_buy_pop_day_hold_1d": [],
        "S5_oracle_buy_pop_day_hold_5d": [],
        "S6_stop_loss_10pct_30d_cap": [],
        "S7_oracle_enter_prior_close_exit_pop_close": [],
        "RANDOM_fry_trigger_matched_n": [],
    }

    panel_idx = panel.set_index(["yahoo_symbol", "date"]).sort_index()

    def episode_path(sym: str, t0: pd.Timestamp) -> pd.DataFrame | None:
        try:
            g = panel_idx.loc[sym].reset_index()
        except KeyError:
            return None
        g = g[g["date"] >= t0].head(HORIZON + 1)
        return g if len(g) >= 2 else None

    for _, row in t1.iterrows():
        sym = row["yahoo_symbol"]
        t0 = pd.Timestamp(row["date"])
        g = episode_path(sym, t0)
        if g is None:
            continue
        close = g["close"].reset_index(drop=True)
        rets = g["return_1d"].reset_index(drop=True)

        r5 = _trade_return(close, 0, min(5, len(close) - 1))
        if r5 is not None:
            trades["S1_hold_5d_from_trigger"].append(r5)
        r30 = _trade_return(close, 0, min(HORIZON, len(close) - 1))
        if r30 is not None:
            trades["S2_hold_30d_from_trigger"].append(r30)

        pop_idx = np.where(rets.iloc[1:].to_numpy() >= POP_RET_MIN)[0]
        exit_i = min(HORIZON, len(close) - 1)
        if len(pop_idx):
            exit_i = int(pop_idx[0]) + 1
        r_pop = _trade_return(close, 0, exit_i)
        if r_pop is not None:
            trades["S3_exit_on_pop_or_30d"].append(r_pop)

        if len(pop_idx):
            pi = int(pop_idx[0]) + 1
            r1 = _trade_return(close, pi, min(pi + 1, len(close) - 1))
            r5p = _trade_return(close, pi, min(pi + 5, len(close) - 1))
            r_pop_capture = _trade_return(close, pi - 1, pi) if pi >= 1 else None
            if r1 is not None:
                trades["S4_oracle_buy_pop_day_hold_1d"].append(r1)
            if r5p is not None:
                trades["S5_oracle_buy_pop_day_hold_5d"].append(r5p)
            if r_pop_capture is not None:
                trades["S7_oracle_enter_prior_close_exit_pop_close"].append(r_pop_capture)

        # stop -10% cum from entry
        cum = (1 + rets.iloc[1:]).cumprod() - 1
        stop_hit = np.where(cum.to_numpy() <= -0.10)[0]
        exit_i = int(stop_hit[0]) + 1 if len(stop_hit) else min(HORIZON, len(close) - 1)
        rs = _trade_return(close, 0, exit_i)
        if rs is not None:
            trades["S6_stop_loss_10pct_30d_cap"].append(rs)

    # Random control: same n as T1, random fry triggers
    all_trig = df.copy()
    rng = np.random.default_rng(7)
    n_t1 = len(t1)
    if n_t1 > 0 and len(all_trig) > n_t1:
        rand_idx = rng.choice(len(all_trig), size=n_t1, replace=False)
        for _, row in all_trig.iloc[rand_idx].iterrows():
            sym = row["yahoo_symbol"]
            t0 = pd.Timestamp(row["date"])
            g = episode_path(sym, t0)
            if g is None:
                continue
            close = g["close"].reset_index(drop=True)
            r5 = _trade_return(close, 0, min(5, len(close) - 1))
            if r5 is not None:
                trades["RANDOM_fry_trigger_matched_n"].append(r5)

    def summarize(name: str, rets: list[float]) -> dict[str, Any]:
        if not rets:
            return {"strategy": name, "n": 0}
        a = np.array(rets)
        sharpe = float(a.mean() / a.std() * np.sqrt(252 / 5)) if a.std() > 0 else 0.0
        return {
            "strategy": name,
            "n": int(len(a)),
            "mean_return_pct": round(float(a.mean()) * 100, 3),
            "median_return_pct": round(float(np.median(a)) * 100, 3),
            "win_rate_pct": round(float((a > 0).mean()) * 100, 2),
            "p05_return_pct": round(float(np.percentile(a, 5)) * 100, 2),
            "p95_return_pct": round(float(np.percentile(a, 95)) * 100, 2),
            "sharpe_ann_proxy": round(sharpe, 3),
            "total_compound_pct": round(float((1 + a).prod() - 1) * 100, 2),
        }

    strat_rows = [summarize(k, v) for k, v in trades.items()]
    return {
        "assumptions": {
            "tx_cost_bps_round_trip": TX_COST_BPS,
            "t1_filter": "return_5d<=-8% & vol>=1.6",
            "horizon_days": HORIZON,
            "note": "S4/S5 are ORACLE ceilings (need pop-day timing). S1-S3 are trigger-day entry.",
        },
        "strategies": strat_rows,
    }


def yearly_walkforward(df: pd.DataFrame) -> list[dict[str, Any]]:
    rules = signal_rules()
    rows = []
    for yr in sorted(df["year"].unique()):
        sub = df[df["year"] == yr]
        if len(sub) < 50:
            continue
        for rule_id in ("T1_deep_dd_vol", "T3_hot_prior", "T1_not_quiet_only"):
            mask = rules[rule_id](sub).fillna(False)
            y = sub["label_pop_30d"].to_numpy(dtype=bool)
            m = _cls_metrics(y, mask.to_numpy())
            rows.append(
                {
                    "year": int(yr),
                    "rule_id": rule_id,
                    **{k: m[k] for k in ("n", "n_predicted_positive", "precision_pct", "recall_pct", "base_rate_pct")},
                }
            )
    return rows


def build_fry_backtest_report() -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_research_frame()
    cls = classification_backtest(df)
    panel = _load_price_panel()
    strat = strategy_backtest(df, panel)
    yearly = yearly_walkforward(df)

    # Headline synthesis
    oos_t1 = next(
        (r for r in cls["rule_metrics"] if r.get("rule_id") == "T1_deep_dd_vol" and r.get("label") == "pop_30d" and r.get("era") == "oos"),
        {},
    )
    oos_rand = next(
        (r for r in cls["random_baselines"] if r.get("baseline") == "random_matched_n_t1" and r.get("era") == "oos"),
        {},
    )
    s1 = next((s for s in strat["strategies"] if s.get("strategy") == "S1_hold_5d_from_trigger"), {})
    s4 = next((s for s in strat["strategies"] if s.get("strategy") == "S4_oracle_buy_pop_day_hold_1d"), {})
    s7 = next((s for s in strat["strategies"] if s.get("strategy") == "S7_oracle_enter_prior_close_exit_pop_close"), {})
    s_rand = next((s for s in strat["strategies"] if s.get("strategy") == "RANDOM_fry_trigger_matched_n"), {})

    report = {
        "meta": {
            "n_triggers": int(len(df)),
            "oos_start": str(OOS_START.date()),
            "n_perm": N_PERM,
            "n_random_trials": N_RANDOM_TRIALS,
        },
        "classification": cls,
        "strategy_pnl": strat,
        "yearly_walkforward": yearly,
        "headline": {
            "guess_accuracy_oos_t1_pop30d": {
                "rule_precision_pct": oos_t1.get("precision_pct"),
                "base_rate_pct": oos_t1.get("base_rate_pct"),
                "lift_vs_base": oos_t1.get("lift_vs_base_rate"),
                "perm_p_value": oos_t1.get("perm_p_value_precision"),
                "random_matched_mean_precision_pct": oos_rand.get("mean_precision_pct"),
                "random_matched_p95_precision_pct": oos_rand.get("p95_precision_pct"),
            },
            "strategy_vs_random_hold5d": {
                "t1_hold_5d_mean_pct": s1.get("mean_return_pct"),
                "random_fry_hold_5d_mean_pct": s_rand.get("mean_return_pct"),
                "oracle_pop_day_next_day_mean_pct": s4.get("mean_return_pct"),
                "oracle_capture_pop_day_move_pct": s7.get("mean_return_pct"),
            },
            "interpretation": _headline_interpretation(oos_t1, oos_rand, s1, s4, s7, s_rand),
        },
        "how_to_use_for_testing": {
            "step_1": "Classification backtest: precision/recall vs random baselines on pop_30d label",
            "step_2": "Permutation p-value: is rule precision better than random matched-n?",
            "step_3": "Strategy P&L: trigger-entry paths vs random fry controls (includes costs)",
            "step_4": "Oracle S4/S5 = ceiling if you nail pop-day timing (watchlist goal)",
            "step_5": "Yearly walkforward: check non-stationarity before live use",
        },
    }
    (OUT_DIR / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _headline_interpretation(oos_t1: dict, oos_rand: dict, s1: dict, s4: dict, s7: dict, s_rand: dict) -> list[str]:
    lines = []
    if oos_t1.get("precision_pct") and oos_rand.get("mean_precision_pct"):
        lines.append(
            f"OOS T1 pop-30d precision {oos_t1['precision_pct']}% vs random matched-n mean {oos_rand['mean_precision_pct']}% "
            f"(random p95 {oos_rand.get('p95_precision_pct')}%)."
        )
    if oos_t1.get("perm_p_value_precision") is not None:
        lines.append(f"Permutation p-value (precision vs random matched-n): {oos_t1['perm_p_value_precision']}.")
    if s1.get("mean_return_pct") is not None and s_rand.get("mean_return_pct") is not None:
        lines.append(
            f"T1 hold-5d from trigger: {s1['mean_return_pct']}% mean vs random fry {s_rand['mean_return_pct']}% — "
            "trigger entry is not the play."
        )
    if s7.get("mean_return_pct") is not None:
        lines.append(
            f"Oracle capture pop-day move (prior close → pop close): {s7['mean_return_pct']}% mean — "
            "theoretical ceiling if you enter before the spike."
        )
    if s4.get("mean_return_pct") is not None:
        lines.append(
            f"Buy at pop-day close + hold 1d: {s4['mean_return_pct']}% — move already happened; fade dominates."
        )
    lines.append("Watchlist signal = classification filter; P&L requires pop-day execution, not trigger-day buy.")
    return lines
