"""Parse RapidAPI IDX broker-summary cache into features + pattern tags."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
CACHE_DIR = REPO / "data_lake/markets/idx_broker_summary/cache"


def cache_path(symbol: str, date: str) -> Path:
    sym = symbol.replace(".JK", "").upper()
    return CACHE_DIR / f"{sym}_{date}.json"


def _inner_data(payload: dict) -> dict:
    d = payload.get("data") or {}
    if d.get("success"):
        inner = d.get("data") or {}
        if isinstance(inner, dict) and "data" in inner:
            return inner["data"] or {}
    return {}


def _hhi(shares: np.ndarray) -> float:
    s = shares[shares > 0]
    if s.size == 0:
        return float("nan")
    s = s / s.sum()
    return float((s**2).sum())


def _type_share(rows: list[dict], val_key: str, typ: str) -> float:
    vals = [abs(float(r.get(val_key) or 0)) for r in rows if r.get("type") == typ]
    total = sum(abs(float(r.get(val_key) or 0)) for r in rows)
    return float(sum(vals) / total) if total > 0 else 0.0


def extract_broker_features(cache_path: Path) -> dict[str, Any] | None:
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    if not raw.get("available"):
        return None
    root = _inner_data(raw)
    det = root.get("bandar_detector") or {}
    bs = root.get("broker_summary") or {}
    buys = bs.get("brokers_buy") or []
    sells = bs.get("brokers_sell") or []

    sym, date = cache_path.stem.split("_", 1)
    symbol = f"{sym}.JK"

    buy_vals = np.array([abs(float(b.get("bval") or 0)) for b in buys], dtype=float)
    sell_vals = np.array([abs(float(s.get("sval") or 0)) for s in sells], dtype=float)
    total_buy = float(buy_vals.sum())
    total_sell = float(sell_vals.sum())

    def top_share(vals: np.ndarray, k: int) -> float:
        if vals.size == 0 or total_buy <= 0:
            return float("nan")
        top = np.sort(vals)[::-1][:k]
        return float(top.sum() / total_buy) if total_buy > 0 else float("nan")

    def top_sell_share(vals: np.ndarray, k: int) -> float:
        if vals.size == 0 or total_sell <= 0:
            return float("nan")
        top = np.sort(vals)[::-1][:k]
        return float(top.sum() / total_sell) if total_sell > 0 else float("nan")

    top1 = det.get("top1") or {}
    top3 = det.get("top3") or {}
    top5 = det.get("top5") or {}
    avg = det.get("avg") or {}
    avg5 = det.get("avg5") or {}

    tb = int(det.get("total_buyer") or 0)
    ts = int(det.get("total_seller") or 0)

    return {
        "yahoo_symbol": symbol,
        "symbol": symbol,
        "date": date,
        "broker_accdist": det.get("broker_accdist"),
        "number_broker_buysell": det.get("number_broker_buysell"),
        "total_buyer_brokers": tb,
        "total_seller_brokers": ts,
        "buyer_seller_broker_ratio": tb / ts if ts > 0 else float("nan"),
        "bandar_value": det.get("value"),
        "bandar_volume": det.get("volume"),
        "top1_flow_pct": top1.get("percent"),
        "top3_flow_pct": top3.get("percent"),
        "top5_flow_pct": top5.get("percent"),
        "top1_flow_label": top1.get("accdist"),
        "avg_flow_pct": avg.get("percent"),
        "avg5_flow_pct": avg5.get("percent"),
        "n_buy_rows": len(buys),
        "n_sell_rows": len(sells),
        "buy_hhi": _hhi(buy_vals),
        "sell_hhi": _hhi(sell_vals),
        "top1_buy_share": top_share(buy_vals, 1),
        "top3_buy_share": top_share(buy_vals, 3),
        "top5_buy_share": top_share(buy_vals, 5),
        "top1_sell_share": top_sell_share(sell_vals, 1),
        "top3_sell_share": top_sell_share(sell_vals, 3),
        "net_value_ratio": (total_buy - total_sell) / (total_buy + total_sell) if (total_buy + total_sell) > 0 else float("nan"),
        "foreign_buy_share": _type_share(buys, "bval", "Asing"),
        "foreign_sell_share": _type_share(sells, "sval", "Asing"),
        "local_buy_share": _type_share(buys, "bval", "Lokal"),
        "govt_buy_share": _type_share(buys, "bval", "Pemerintah"),
        "top_buy_broker": buys[0].get("netbs_broker_code") if buys else None,
        "top_sell_broker": sells[0].get("netbs_broker_code") if sells else None,
    }


def pattern_tags(row: dict) -> list[str]:
    tags: list[str] = []
    if row.get("broker_accdist") == "Acc":
        tags.append("bandar_acc")
    elif row.get("broker_accdist") == "Dist":
        tags.append("bandar_dist")

    t1 = row.get("top1_flow_pct")
    if t1 is not None and t1 > 10:
        tags.append("top1_flow_gt_10pct")
    if t1 is not None and t1 > 0:
        tags.append("top1_flow_positive")
    elif t1 is not None and t1 < 0:
        tags.append("top1_flow_negative")

    t3 = row.get("top3_flow_pct")
    if t3 is not None and t3 > 5:
        tags.append("top3_flow_gt_5pct")
    if t3 is not None and t3 < -5:
        tags.append("top3_flow_lt_neg5pct")

    if row.get("top3_buy_share") and row["top3_buy_share"] > 0.55:
        tags.append("buy_concentrated_top3")
    if row.get("buy_hhi") and row["buy_hhi"] > 0.25:
        tags.append("buy_hhi_high")

    if row.get("foreign_buy_share") and row["foreign_buy_share"] > 0.35:
        tags.append("foreign_buy_heavy")
    if row.get("foreign_sell_share") and row["foreign_sell_share"] > 0.35:
        tags.append("foreign_sell_heavy")

    nbs = row.get("number_broker_buysell")
    if nbs is not None and nbs < -15:
        tags.append("more_selling_brokers")
    elif nbs is not None and nbs > 5:
        tags.append("more_buying_brokers")

    if row.get("net_value_ratio") and row["net_value_ratio"] > 0.1:
        tags.append("net_buy_value")
    elif row.get("net_value_ratio") and row["net_value_ratio"] < -0.1:
        tags.append("net_sell_value")

    if row.get("buyer_seller_broker_ratio") and row["buyer_seller_broker_ratio"] < 0.6:
        tags.append("few_buyers_vs_sellers")

    return tags


def load_features_for_session(symbol: str, date: str) -> dict[str, Any] | None:
    path = cache_path(symbol, date)
    if not path.exists():
        return None
    return extract_broker_features(path)


def load_all_cached_features() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not CACHE_DIR.exists():
        return rows
    for path in sorted(CACHE_DIR.glob("*.json")):
        feat = extract_broker_features(path)
        if feat:
            feat["broker_tags"] = pattern_tags(feat)
            rows.append(feat)
    return rows
