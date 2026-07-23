#!/usr/bin/env python3
"""IDX broker-summary collector — file cache + optional RapidAPI.

Spectator/CDP lane: run Molina-Optiplex/scripts/spectator_idx_broker_probe.sh
when the Spectator host is online; this module reads the JSON output.

Examples:
  python scripts/idn_bandar_collector.py probe --symbol BBCA --date 2024-06-10
  python scripts/idn_bandar_collector.py fetch --provider file
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
PROBE_JSON = REPO / "data_lake/markets/idx_broker_summary/_probe/latest.json"
OUT_DIR = REPO / "data_lake/markets/idx_broker_summary"
CACHE_DIR = OUT_DIR / "cache"
CFG = REPO / "config/markets/indonesia_bandar_sources.json"

RAPIDAPI_HOST = "indonesia-stock-exchange-idx.p.rapidapi.com"
# RapidAPI paths (Market Detector group) — see playground getBrokerSummary / getBrokerActivity
RAPIDAPI_BROKER_SUMMARY = "/api/market-detector/broker-summary/{symbol}"
RAPIDAPI_BROKER_ACTIVITY = "/api/market-detector/broker-activity/{broker_code}"
RAPIDAPI_DEFAULT_PARAMS = {
    "limit": "25",
    "marketBoard": "MARKET_BOARD_ALL",
    "transactionType": "TRANSACTION_TYPE_NET",
    "investorType": "INVESTOR_TYPE_ALL",
}


def load_config() -> dict:
    if CFG.exists():
        return json.loads(CFG.read_text(encoding="utf-8"))
    return {"providers": {"file": {"enabled": True}, "rapidapi": {"enabled": False}}}


def load_probe_file() -> dict[str, Any]:
    if not PROBE_JSON.exists():
        return {"available": False, "reason": f"missing {PROBE_JSON}"}
    data = json.loads(PROBE_JSON.read_text(encoding="utf-8"))
    return {"available": True, "source": "spectator_probe", "probe": data}


def rapidapi_get(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    from dotenv import load_dotenv

    for p in [REPO / ".env.local", REPO / ".env", REPO.parent / ".env.local", REPO.parent / ".env"]:
        if p.exists():
            load_dotenv(p, override=False)
    key = os.getenv("RAPIDAPI_KEY", "").strip()
    if not key:
        return {"available": False, "reason": "RAPIDAPI_KEY unset"}

    q = ""
    if params:
        q = "?" + "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params.items())

    url = f"https://{RAPIDAPI_HOST}{path}{q}"
    req = urllib.request.Request(
        url,
        headers={
            "x-rapidapi-key": key,
            "x-rapidapi-host": RAPIDAPI_HOST,
            "Accept": "application/json",
            "User-Agent": "Sharpe-Renaissance/1.0 (IDX research; +https://rapidapi.com)",
        },
        method="GET",
    )
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode()
            parsed = json.loads(body)
            return {"available": True, "source": "rapidapi", "path": path, "data": parsed}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()[:500]
            if e.code == 429 and attempt < 3:
                time.sleep(2.0 * attempt)
                continue
            return {"available": False, "reason": f"http_{e.code}", "body": err_body}
        except Exception as e:
            return {"available": False, "reason": str(e)}
    return {"available": False, "reason": "http_429_retries_exhausted"}


def _cache_path(symbol: str, date: str) -> Path:
    sym = symbol.replace(".JK", "").upper()
    return CACHE_DIR / f"{sym}_{date}.json"


def fetch_broker_summary_rapidapi(symbol: str, date: str, *, use_cache: bool = True) -> dict[str, Any]:
    sym = symbol.replace(".JK", "").upper()
    cache = _cache_path(sym, date)
    if use_cache and cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if cached.get("available"):
                cached["from_cache"] = True
                return cached
        except json.JSONDecodeError:
            pass
    path = RAPIDAPI_BROKER_SUMMARY.format(symbol=sym)
    params = {**RAPIDAPI_DEFAULT_PARAMS, "from": date, "to": date}
    result = rapidapi_get(path, params)
    if result.get("available") and (result.get("data") or {}).get("success"):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def summarize_broker_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract row counts and bandar detector headline from RapidAPI response."""
    root = payload.get("data", {})
    if isinstance(root, dict) and "data" in root:
        root = root["data"]
    bs = (root or {}).get("broker_summary") or {}
    buys = bs.get("brokers_buy") or []
    sells = bs.get("brokers_sell") or []
    det = (root or {}).get("bandar_detector") or {}
    return {
        "n_buy_brokers": len(buys),
        "n_sell_brokers": len(sells),
        "bandar_accdist": det.get("broker_accdist"),
        "total_value": det.get("value"),
        "top_broker_buy": buys[0].get("netbs_broker_code") if buys else None,
        "top_broker_sell": sells[0].get("netbs_broker_code") if sells else None,
    }


def broker_context_for_spike(symbol: str, date: str) -> dict[str, Any]:
    """Best-effort broker context for spike explainer (RapidAPI, then file probe)."""
    sym = symbol.replace(".JK", "").upper()

    rap = fetch_broker_summary_rapidapi(sym, date)
    if rap.get("available"):
        data = rap.get("data") or {}
        if data.get("success"):
            meta = summarize_broker_payload(data)
            if meta["n_buy_brokers"] or meta["n_sell_brokers"]:
                return {
                    "available": True,
                    "symbol": sym,
                    "date": date,
                    "source": "rapidapi",
                    "summary_text": (
                        f"Broker summary: {meta['n_buy_brokers']} buyers, {meta['n_sell_brokers']} sellers; "
                        f"bandar={meta.get('bandar_accdist')}; "
                        f"top buy={meta.get('top_broker_buy')}, top sell={meta.get('top_broker_sell')}."
                    ),
                    **meta,
                }

    probe = load_probe_file()
    if not probe.get("available"):
        return {"available": False, "reason": "no_rapidapi_or_file_probe", "symbol": sym, "date": date}

    endpoints = probe.get("probe", {}).get("endpoints", {})
    stock_ep = endpoints.get("stock_broker_summary_guess_a") or endpoints.get("stock_broker_summary_guess_b")
    market_ep = endpoints.get("broker_summary_market")

    lines: list[str] = []
    if stock_ep and stock_ep.get("ok") and not stock_ep.get("looksLikeHtml"):
        rows = stock_ep.get("rowCount")
        lines.append(f"Per-stock broker rows available ({rows} sample rows in probe).")
    elif market_ep and market_ep.get("ok"):
        lines.append("Only market-wide broker summary confirmed via IDX probe (not per-ticker bandar).")

    if not lines:
        return {"available": False, "reason": "probe_has_no_broker_rows", "symbol": sym, "date": date}

    return {
        "available": True,
        "symbol": sym,
        "date": date,
        "source": "spectator_probe",
        "summary_text": " ".join(lines),
        "probe_path": str(PROBE_JSON),
    }


def cmd_probe(args: argparse.Namespace) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"symbol": args.symbol, "date": args.date, "providers": {}}

    result["providers"]["file"] = load_probe_file()
    if args.provider in {"rapidapi", "all"}:
        sym = args.symbol.replace(".JK", "").upper()
        r = fetch_broker_summary_rapidapi(sym, args.date)
        key = f"rapidapi:{RAPIDAPI_BROKER_SUMMARY.format(symbol=sym)}"
        if r.get("available") and (r.get("data") or {}).get("success"):
            meta = summarize_broker_payload(r["data"])
            r["meta"] = meta
            r["pass"] = bool(meta["n_buy_brokers"] or meta["n_sell_brokers"])
        result["providers"][key] = r

    out = OUT_DIR / f"probe_{args.symbol}_{args.date}.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2)[:4000])
    print(f"\nWrote {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_probe = sub.add_parser("probe", help="Try configured providers for one symbol/date")
    p_probe.add_argument("--symbol", default="BBCA")
    p_probe.add_argument("--date", default="2024-06-10")
    p_probe.add_argument("--provider", choices=["file", "rapidapi", "all"], default="all")
    p_probe.set_defaults(func=cmd_probe)

    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
