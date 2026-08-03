#!/usr/bin/env python3
"""Spike-day broker validation: RapidAPI broker summary vs group_sync fwd-5d.

Fetches broker data for priority spike sessions (cached), runs event-study buckets,
writes dossiers for top repeat spikers.

Output: backtests/outputs/idn_broker_spike_validation/latest.json
"""

from __future__ import annotations

import json
import sys
import time
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

from idn_bandar_collector import (  # noqa: E402
    fetch_broker_summary_rapidapi,
    summarize_broker_payload,
)
from idn_spike_explainer import explain_spike  # noqa: E402
from run_idn_spike_pattern_mining import START, MIN_PCT, classify_spike_row  # noqa: E402
from run_idn_spike_pattern_mining import fetch_history, load_groups, load_universe  # noqa: E402

OUT = REPO / "backtests/outputs/idn_broker_spike_validation"
EXPLAINER_OUT = REPO / "backtests/outputs/idn_spike_explainer"
FETCH_DELAY_SEC = 3.5
TOP_REPEATERS = ["TPIA.JK", "BREN.JK", "INCO.JK", "MDKA.JK", "HRUM.JK"]


def load_spike_rows() -> list[dict]:
    universe = load_universe()
    groups = load_groups()
    extra = sorted({t for g in groups.values() for t in g.get("tickers", [])})
    syms = sorted(set(universe + extra))
    px, vol_px = fetch_history(syms, START, datetime.now(UTC).strftime("%Y-%m-%d"))
    rows: list[dict] = []
    for sym in universe:
        if sym not in px.columns:
            continue
        for dt, r in px[sym].pct_change().dropna().items():
            if r * 100 < MIN_PCT:
                continue
            rows.append(classify_spike_row(sym, pd.Timestamp(dt), float(r), px, vol_px))
    return rows


def fetch_broker_meta(symbol: str, date: str) -> dict[str, Any]:
    rap = fetch_broker_summary_rapidapi(symbol, date)
    if not rap.get("available") or not (rap.get("data") or {}).get("success"):
        return {
            "available": False,
            "reason": rap.get("reason") or "api_failed",
            "symbol": symbol,
            "date": date,
        }
    meta = summarize_broker_payload(rap["data"])
    det = (rap.get("data") or {}).get("data", {}).get("data", {}).get("bandar_detector") or {}
    if not det and isinstance(rap.get("data"), dict):
        inner = rap["data"].get("data", {})
        if isinstance(inner, dict):
            det = inner.get("bandar_detector") or (inner.get("data") or {}).get("bandar_detector") or {}
    return {
        "available": True,
        "symbol": symbol,
        "date": date,
        "from_cache": rap.get("from_cache", False),
        **meta,
        "total_buyers": det.get("total_buyer"),
        "total_sellers": det.get("total_seller"),
        "broker_buysell_net": det.get("number_broker_buysell"),
    }


def bucket_stats(rows: list[dict], label: str) -> dict[str, Any]:
    fwd = pd.Series([r["fwd_5d_return_pct"] for r in rows], dtype=float).dropna()
    return {
        "bucket": label,
        "n": len(rows),
        "n_with_fwd": int(len(fwd)),
        "mean_fwd_5d_pct": round(float(fwd.mean()), 2) if len(fwd) else None,
        "hit_rate_5d_pct": round(float((fwd > 0).mean() * 100), 1) if len(fwd) else None,
    }


def main() -> int:
    rows = load_spike_rows()
    print(f"Loaded {len(rows)} spike sessions >= {MIN_PCT}% since {START}")

    # Priority fetch: group_sync_2plus + top repeater best spike each
    sync2 = [r for r in rows if "group_sync_2plus" in r["tags"]]
    dossier_picks: list[dict] = []
    for sym in TOP_REPEATERS:
        sub = [r for r in rows if r["symbol"] == sym]
        if sub:
            dossier_picks.append(max(sub, key=lambda x: x["return_pct"]))

    fetch_keys: list[tuple[str, str]] = []
    for r in sync2 + dossier_picks:
        key = (r["symbol"], r["date"])
        if key not in fetch_keys:
            fetch_keys.append(key)

    print(f"Fetching broker summary for {len(fetch_keys)} unique symbol-dates ({FETCH_DELAY_SEC}s pacing)...")
    broker_by_key: dict[tuple[str, str], dict] = {}
    api_calls = 0
    for i, (sym, date) in enumerate(fetch_keys):
        if i > 0:
            time.sleep(FETCH_DELAY_SEC)
        meta = fetch_broker_meta(sym, date)
        broker_by_key[(sym, date)] = meta
        if meta.get("available"):
            api_calls += 0 if meta.get("from_cache") else 1
            print(f"  OK {date} {sym} accdist={meta.get('bandar_accdist')} buyers={meta.get('n_buy_brokers')}")
        else:
            print(f"  FAIL {date} {sym} {meta.get('reason')}")

    enriched: list[dict] = []
    for r in rows:
        b = broker_by_key.get((r["symbol"], r["date"]), {"available": False})
        enriched.append(
            {
                **r,
                "broker": b,
                "has_broker": b.get("available", False),
                "broker_accdist": b.get("bandar_accdist"),
                "broker_buysell_net": b.get("broker_buysell_net"),
            }
        )

    with_broker = [r for r in enriched if r["has_broker"]]
    sync2_broker = [r for r in with_broker if "group_sync_2plus" in r["tags"]]
    sync2_acc = [r for r in sync2_broker if r.get("broker_accdist") == "Acc"]
    sync2_dist = [r for r in sync2_broker if r.get("broker_accdist") == "Dist"]
    sync2_fetched = {(r["symbol"], r["date"]) for r in sync2_broker}
    sync2_no_broker = [r for r in sync2 if (r["symbol"], r["date"]) not in sync2_fetched]

    event_study = [
        bucket_stats(rows, "all_spikes"),
        bucket_stats(sync2, "group_sync_2plus_all"),
        bucket_stats(sync2_broker, "group_sync_2plus_with_broker"),
        bucket_stats(sync2_acc, "group_sync_2plus_broker_Acc"),
        bucket_stats(sync2_dist, "group_sync_2plus_broker_Dist"),
        bucket_stats(
            [r for r in with_broker if r.get("broker_accdist") == "Acc" and "group_sync_2plus" not in r["tags"]],
            "broker_Acc_not_sync2",
        ),
        bucket_stats(
            [r for r in with_broker if "group_sync_2plus" not in r["tags"]],
            "not_sync2_with_broker",
        ),
    ]

    # Does broker Acc add beyond group_sync?
    sync2_non_acc = [r for r in sync2_broker if r.get("broker_accdist") != "Acc"]
    verdict = "inconclusive"
    acc_fwd = pd.Series([r["fwd_5d_return_pct"] for r in sync2_acc], dtype=float).dropna()
    non_acc_fwd = pd.Series([r["fwd_5d_return_pct"] for r in sync2_non_acc], dtype=float).dropna()
    all_sync_fwd = pd.Series([r["fwd_5d_return_pct"] for r in sync2], dtype=float).dropna()
    if len(acc_fwd) >= 3 and len(non_acc_fwd) >= 3:
        if float(acc_fwd.mean()) > float(non_acc_fwd.mean()) + 2.0:
            verdict = "broker_acc_helps_on_sync2"
        elif float(acc_fwd.mean()) < float(non_acc_fwd.mean()) - 2.0:
            verdict = "broker_acc_hurts_on_sync2"
        else:
            verdict = "broker_acc_neutral_on_sync2"
    elif len(sync2_broker) < 5:
        verdict = "insufficient_broker_coverage"

    dossiers: list[dict] = []
    EXPLAINER_OUT.mkdir(parents=True, exist_ok=True)
    print("\nWriting dossiers for top repeaters (cached broker)...")
    for pick in dossier_picks:
        sym, date = pick["symbol"], pick["date"]
        rep = explain_spike(sym, date, "skip")
        slug = f"{sym.replace('.', '_')}_{date}"
        (EXPLAINER_OUT / f"{slug}.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
        (EXPLAINER_OUT / f"{slug}.md").write_text(
            f"# {sym} {date} ({pick['return_pct']:+.1f}%)\n\n{rep['narrative']}\n",
            encoding="utf-8",
        )
        dossiers.append({"symbol": sym, "date": date, "slug": slug, "return_pct": pick["return_pct"]})
        print(f"  dossier {slug}")

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "n_spike_sessions": len(rows),
        "n_broker_fetches_attempted": len(fetch_keys),
        "n_broker_available": len(with_broker),
        "n_api_calls_live": api_calls,
        "event_study_fwd5d": event_study,
        "verdict": verdict,
        "sync2_without_broker_data": len(sync2_no_broker),
        "broker_fetch_details": [broker_by_key[k] for k in fetch_keys],
        "dossiers": dossiers,
        "comparison": {
            "group_sync_2plus_mean_fwd": round(float(all_sync_fwd.mean()), 2) if len(all_sync_fwd) else None,
            "sync2_broker_Acc_mean_fwd": round(float(acc_fwd.mean()), 2) if len(acc_fwd) else None,
            "sync2_broker_non_Acc_mean_fwd": round(float(non_acc_fwd.mean()), 2) if len(non_acc_fwd) else None,
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "latest.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("\n=== Event study (fwd 5d after spike) ===")
    print(f"{'bucket':40} | {'n':>4} | {'fwd5d%':>7} | {'hit%':>6}")
    print("-" * 65)
    for e in event_study:
        print(
            f"{e['bucket']:40} | {e['n']:4} | {e.get('mean_fwd_5d_pct') or 0:6.1f}% | "
            f"{e.get('hit_rate_5d_pct') or 0:5.1f}%"
        )
    print(f"\nVerdict: {verdict}")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
