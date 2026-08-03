#!/usr/bin/env python3
"""Broker flow pattern study — concentration, positioning, investor type vs fwd returns.

Parses cached RapidAPI broker-summary JSON, engineers features from bandar_detector
and per-broker rows, joins spike-day outcomes, tests whether broker patterns add
predictive power beyond group_sync.

Output: backtests/outputs/idn_broker_pattern_alpha/latest.json
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
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
sys.path.insert(0, str(REPO / "scripts"))

from run_idn_spike_pattern_mining import START, MIN_PCT, classify_spike_row  # noqa: E402
from run_idn_spike_pattern_mining import fetch_history, load_universe  # noqa: E402

from idn_broker_features_lib import CACHE_DIR, extract_broker_features, pattern_tags  # noqa: E402

OUT = REPO / "backtests/outputs/idn_broker_pattern_alpha"


def bucket_stats(df: pd.DataFrame, mask: pd.Series, label: str) -> dict:
    sub = df[mask]
    fwd = sub["fwd_5d_return_pct"].dropna()
    return {
        "bucket": label,
        "n": int(len(sub)),
        "n_fwd": int(len(fwd)),
        "mean_fwd_5d_pct": round(float(fwd.mean()), 2) if len(fwd) else None,
        "hit_rate_pct": round(float((fwd > 0).mean() * 100), 1) if len(fwd) else None,
    }


def spearman_table(df: pd.DataFrame, features: list[str]) -> list[dict]:
    rows = []
    fwd = df["fwd_5d_return_pct"]
    for f in features:
        x = pd.to_numeric(df[f], errors="coerce")
        pair = pd.concat([x, fwd], axis=1).dropna()
        if len(pair) < 5:
            rows.append({"feature": f, "n": len(pair), "spearman": None, "p_approx": None})
            continue
        corr = pair.iloc[:, 0].corr(pair.iloc[:, 1], method="spearman")
        rows.append({"feature": f, "n": len(pair), "spearman": round(float(corr), 3)})
    return sorted(rows, key=lambda r: abs(r.get("spearman") or 0), reverse=True)


def incremental_r2(df: pd.DataFrame) -> dict:
    """OLS fwd ~ group_sync + broker features (tiny sample — illustrative only)."""
    sub = df.dropna(subset=["fwd_5d_return_pct"]).copy()
    if len(sub) < 8:
        return {"available": False, "reason": f"n={len(sub)} too small"}

    y = sub["fwd_5d_return_pct"].astype(float).values
    base = sub["group_sync_2plus"].astype(float).values.reshape(-1, 1)

    broker_cols = [
        "top3_flow_pct",
        "top1_buy_share",
        "buy_hhi",
        "foreign_buy_share",
        "number_broker_buysell",
        "net_value_ratio",
    ]
    Xb = sub[broker_cols].apply(pd.to_numeric, errors="coerce").fillna(0).values
    full = np.column_stack([base, Xb])

    def r2(X: np.ndarray) -> float:
        Xd = np.column_stack([np.ones(len(X)), X])
        beta, _, _, _ = np.linalg.lstsq(Xd, y, rcond=None)
        pred = Xd @ beta
        ss_res = float(((y - pred) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        return 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    r2_base = r2(base)
    r2_full = r2(full)
    return {
        "available": True,
        "n": len(sub),
        "r2_group_sync_only": round(r2_base, 3),
        "r2_group_sync_plus_broker": round(r2_full, 3),
        "delta_r2": round(r2_full - r2_base, 3),
    }


def main() -> int:
    spike_rows: dict[tuple[str, str], dict] = {}
    universe = load_universe()
    px, vol_px = fetch_history(universe, START, datetime.now(UTC).strftime("%Y-%m-%d"))
    for sym in universe:
        if sym not in px.columns:
            continue
        for dt, r in px[sym].pct_change().dropna().items():
            if r * 100 < MIN_PCT:
                continue
            row = classify_spike_row(sym, pd.Timestamp(dt), float(r), px, vol_px)
            spike_rows[(sym, row["date"])] = row

    feats: list[dict] = []
    for path in sorted(CACHE_DIR.glob("*.json")):
        f = extract_broker_features(path)
        if not f:
            continue
        spike = spike_rows.get((f["symbol"], f["date"]), {})
        f["fwd_5d_return_pct"] = spike.get("fwd_5d_return_pct")
        f["spike_return_pct"] = spike.get("return_pct")
        f["group_sync_2plus"] = "group_sync_2plus" in spike.get("tags", [])
        f["group_sync_1plus"] = "group_sync_1plus" in spike.get("tags", [])
        f["sector_group"] = spike.get("sector_group")
        f["broker_tags"] = pattern_tags(f)
        feats.append(f)

    df = pd.DataFrame(feats)
    if df.empty:
        raise SystemExit("no cached broker files")

    numeric_features = [
        "top1_flow_pct",
        "top3_flow_pct",
        "top5_flow_pct",
        "avg_flow_pct",
        "avg5_flow_pct",
        "number_broker_buysell",
        "buyer_seller_broker_ratio",
        "buy_hhi",
        "sell_hhi",
        "top1_buy_share",
        "top3_buy_share",
        "top5_buy_share",
        "top1_sell_share",
        "top3_sell_share",
        "net_value_ratio",
        "foreign_buy_share",
        "foreign_sell_share",
        "local_buy_share",
        "govt_buy_share",
    ]

    tag_stats = []
    all_tags = sorted({t for tags in df["broker_tags"] for t in tags})
    for tag in all_tags:
        mask = df["broker_tags"].apply(lambda xs, t=tag: t in xs)
        tag_stats.append(bucket_stats(df, mask, tag))

    # Combined: group_sync + broker pattern
    combo_stats = [
        bucket_stats(df, df["group_sync_2plus"], "group_sync_2plus"),
        bucket_stats(df, df["group_sync_2plus"] & df["broker_tags"].apply(lambda x: "top3_flow_gt_5pct" in x), "sync2_top3_flow_gt_5"),
        bucket_stats(df, df["group_sync_2plus"] & df["broker_tags"].apply(lambda x: "buy_concentrated_top3" in x), "sync2_buy_concentrated"),
        bucket_stats(df, df["group_sync_2plus"] & df["broker_tags"].apply(lambda x: "foreign_buy_heavy" in x), "sync2_foreign_buy_heavy"),
        bucket_stats(df, df["group_sync_2plus"] & df["broker_tags"].apply(lambda x: "bandar_acc" in x), "sync2_bandar_acc"),
        bucket_stats(df, df["group_sync_2plus"] & df["broker_tags"].apply(lambda x: "more_selling_brokers" in x), "sync2_more_selling_brokers"),
        bucket_stats(df, df["group_sync_2plus"] & df["broker_tags"].apply(lambda x: "top1_flow_positive" in x), "sync2_top1_flow_positive"),
    ]

    corr = spearman_table(df.dropna(subset=["fwd_5d_return_pct"]), numeric_features)
    r2 = incremental_r2(df)

    # Verdict
    verdict = "no_broker_alpha"
    best_tag = max((t for t in tag_stats if t["n_fwd"] and t["n_fwd"] >= 3), key=lambda x: x.get("mean_fwd_5d_pct") or -999, default=None)
    sync2_fwd = df.loc[df["group_sync_2plus"], "fwd_5d_return_pct"].dropna()
    if r2.get("available") and (r2.get("delta_r2") or 0) > 0.15:
        verdict = "broker_features_add_explained_variance"
    elif best_tag and sync2_fwd.size and (best_tag.get("mean_fwd_5d_pct") or 0) > float(sync2_fwd.mean()) + 3:
        verdict = f"pattern_{best_tag['bucket']}_beats_sync2_mean"

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "n_broker_sessions": len(df),
        "n_with_fwd_5d": int(df["fwd_5d_return_pct"].notna().sum()),
        "sessions": df.to_dict(orient="records"),
        "broker_tag_stats": sorted(tag_stats, key=lambda x: x.get("mean_fwd_5d_pct") or -999, reverse=True),
        "combo_with_group_sync": combo_stats,
        "spearman_vs_fwd5d": corr,
        "incremental_r2": r2,
        "verdict": verdict,
        "caveat": "n<=23 broker sessions; fwd labels sparse for 2026 dates — not investment-grade.",
    }

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "latest.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"Broker pattern study: {len(df)} sessions, {report['n_with_fwd_5d']} with fwd 5d label\n")
    print("=== Broker pattern tags vs fwd 5d ===")
    print(f"{'tag':28} | {'n':>3} | {'fwd':>3} | {'mean%':>7} | {'hit%':>5}")
    for t in report["broker_tag_stats"][:15]:
        print(
            f"{t['bucket']:28} | {t['n']:3} | {t['n_fwd']:3} | "
            f"{t.get('mean_fwd_5d_pct') or 0:6.1f}% | {t.get('hit_rate_pct') or 0:5.1f}%"
        )
    print("\n=== group_sync + broker combo ===")
    for t in combo_stats:
        print(
            f"{t['bucket']:32} | n={t['n']} fwd={t['n_fwd']} "
            f"mean={t.get('mean_fwd_5d_pct')}% hit={t.get('hit_rate_pct')}%"
        )
    print("\n=== Spearman vs fwd 5d (top features) ===")
    for c in corr[:8]:
        print(f"  {c['feature']:24} rho={c.get('spearman')} n={c['n']}")
    print(f"\nIncremental R²: {r2}")
    print(f"\nVerdict: {verdict}")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
