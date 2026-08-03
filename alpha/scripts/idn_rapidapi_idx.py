"""Shared RapidAPI client for Indonesia Stock Exchange (IDX) API.

Docs: https://rapidapi.com/yasimpratama88/api/indonesia-stock-exchange-idx
Rate limit: 1 req/sec on BASIC — enforced here + disk cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
HOST = "indonesia-stock-exchange-idx.p.rapidapi.com"
CACHE_DIR = REPO / "data_lake/markets/rapidapi_idx_cache"
CAPABILITY_OUT = REPO / "backtests/outputs/platform/idn_rapidapi_capability/latest.json"

_LAST_CALL = 0.0
_MIN_INTERVAL = 1.15


def load_env() -> None:
    for p in [REPO / ".env.local", REPO / ".env", REPO.parent / ".env.local", REPO.parent / ".env"]:
        if p.exists():
            load_dotenv(p, override=False)


def _api_key() -> str:
    load_env()
    return os.getenv("RAPIDAPI_KEY", "").strip()


def _throttle() -> None:
    global _LAST_CALL
    now = time.monotonic()
    wait = _MIN_INTERVAL - (now - _LAST_CALL)
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL = time.monotonic()


def _cache_key(path: str, params: dict[str, str] | None) -> str:
    raw = json.dumps({"path": path, "params": params or {}}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def get(
    path: str,
    params: dict[str, str] | None = None,
    *,
    use_cache: bool = True,
    cache_only: bool = False,
    cache_ttl_sec: int = 3600,
) -> dict[str, Any]:
    """GET with rate limit + optional disk cache."""
    key = _api_key()
    if not key:
        return {"ok": False, "reason": "RAPIDAPI_KEY unset", "path": path}

    ck = _cache_key(path, params)
    cache_file = CACHE_DIR / f"{ck}.json"
    if use_cache and cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < cache_ttl_sec:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            cached["from_cache"] = True
            cached["cache_age_sec"] = int(age)
            return cached

    if cache_only:
        return {"ok": False, "reason": "cache_miss", "path": path}

    _throttle()
    url = f"https://{HOST}{path}"
    try:
        r = requests.get(
            url,
            params=params or {},
            headers={"x-rapidapi-key": key, "x-rapidapi-host": HOST},
            timeout=45,
        )
        if r.status_code != 200:
            return {"ok": False, "reason": f"http_{r.status_code}", "path": path, "body": r.text[:500]}
        payload = r.json()
        out = {"ok": True, "path": path, "params": params, "fetched_at_utc": datetime.now(UTC).isoformat(), "data": payload}
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(out, default=str), encoding="utf-8")
        return out
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "path": path}


def _parse_pct(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace("%", "").replace(",", "")
    if not s or s in {"-", "N/A", "n/a"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def slim_emiten_profile(data: dict) -> dict[str, Any] | None:
    if not data.get("ok"):
        return None
    root = (data.get("data") or {}).get("data") or {}
    hist = root.get("history") or {}
    board = str(hist.get("board") or "")
    board_norm = board.lower()
    return {
        "yahoo_symbol": None,
        "listing_board": board or None,
        "is_watchlist_board": "pemantauan" in board_norm or "watchlist" in board_norm,
        "is_acceleration_board": "akselerasi" in board_norm or "acceleration" in board_norm,
        "free_float_pct": _parse_pct(hist.get("free_float")),
        "ipo_shares": hist.get("shares"),
        "ipo_date": hist.get("date"),
        "ipo_price": hist.get("price"),
        "sector": root.get("sector"),
        "sub_sector": root.get("sub_sector"),
    }


def slim_emiten_insider(data: dict) -> dict[str, Any] | None:
    if not data.get("ok"):
        return None
    root = (data.get("data") or {}).get("data") or {}
    moves = root.get("movement") or []
    top_holder_pct: float | None = None
    top_holder_name: str | None = None
    latest_action: str | None = None
    latest_pct_change: float | None = None
    foreign_controller = False
    recent_controller_buy = False
    insider_broker_code: str | None = None
    if moves:
        m0 = moves[0]
        cur = m0.get("current") or {}
        top_holder_pct = _parse_pct(cur.get("percentage"))
        top_holder_name = m0.get("name")
        latest_action = m0.get("action_type")
        nat = str(m0.get("nationality") or "")
        foreign_controller = "FOREIGN" in nat.upper()
        recent_controller_buy = "BUY" in str(latest_action or "").upper()
        latest_pct_change = _parse_pct((m0.get("changes") or {}).get("percentage"))
        insider_broker_code = (m0.get("broker_detail") or {}).get("code") or None
    return {
        "top_holder_pct": top_holder_pct,
        "top_holder_name": top_holder_name,
        "latest_insider_action": latest_action,
        "insider_move_count": len(moves),
        "has_insider_data": bool(moves),
        "controller_is_foreign": foreign_controller,
        "latest_insider_buy": recent_controller_buy,
        "latest_holder_pct_change": latest_pct_change,
        "insider_broker_code": insider_broker_code,
    }


def _index_flags(indexes: Any) -> dict[str, Any]:
    if not isinstance(indexes, list):
        return {
            "idx_memberships": None,
            "is_trading_limit": False,
            "is_daytrade": False,
            "is_idx_liquid": False,
        }
    idx_set = {str(x).strip().upper() for x in indexes if x}
    liquid = bool(idx_set & {"IDX30", "LQ45", "IDX80", "KOMPAS100", "JII"})
    return {
        "idx_memberships": ",".join(sorted(idx_set)) if idx_set else None,
        "is_trading_limit": "TRADINGLIMIT" in idx_set,
        "is_daytrade": "DAYTRADE" in idx_set,
        "is_idx_liquid": liquid,
    }


def slim_emiten_info(data: dict) -> dict[str, Any] | None:
    if not data.get("ok"):
        return None
    d = (data.get("data") or {}).get("data") or {}
    if not d:
        return None
    row = {
        "symbol": d.get("symbol") or d.get("code"),
        "name": d.get("name"),
        "change": d.get("change"),
        "percent": d.get("percent") or d.get("percent_change"),
        "last": d.get("last") or d.get("price"),
        "volume": d.get("volume"),
        "value": d.get("value"),
        "sector": d.get("sector"),
        "followers": d.get("followers"),
        "followed": d.get("followed"),
        "exchange": d.get("exchange"),
    }
    row.update(_index_flags(d.get("indexes")))
    return row


def slim_technical(data: dict) -> dict[str, Any] | None:
    ext = slim_technical_extended(data)
    if not ext:
        return None
    return {
        "symbol": ext.get("symbol"),
        "last_price": ext.get("last_price"),
        "rsi": ext.get("rsi"),
        "rsi_signal": ext.get("rsi_signal"),
        "macd_signal": ext.get("macd_signal"),
        "overall_signal": ext.get("overall_signal"),
        "summary": ext.get("summary"),
    }


def slim_technical_extended(data: dict) -> dict[str, Any] | None:
    if not data.get("ok"):
        return None
    d = (data.get("data") or {}).get("data") or {}
    if not d:
        return None
    indicators = d.get("indicators") or {}
    rsi_block = indicators.get("rsi") or {}
    macd_block = indicators.get("macd") or {}
    bb_block = indicators.get("bollingerBands") or {}
    vwap_block = indicators.get("vwap") or {}
    signals = d.get("signal") or d.get("signals") or d.get("trading_signals") or {}
    trend = d.get("trend") or {}
    sr = d.get("supportResistance") or {}
    summary = d.get("summary") or (data.get("data") or {}).get("message")
    rec = None
    if isinstance(summary, dict):
        rec = summary.get("recommendation")
    elif isinstance(summary, str):
        rec = summary

    rsi_val = rsi_block.get("value") if isinstance(rsi_block, dict) else rsi_block
    try:
        rsi_f = float(rsi_val) if rsi_val is not None else None
    except (TypeError, ValueError):
        rsi_f = None

    last_price = d.get("lastPrice")
    nearest_support: float | None = None
    support_distance_pct: float | None = None
    supports = sr.get("supports") or []
    if supports and last_price is not None:
        try:
            lp = float(last_price)
            levels = [float(s["level"]) for s in supports if s.get("level") is not None]
            below = [lv for lv in levels if lv <= lp]
            if below:
                nearest_support = max(below)
                support_distance_pct = round((lp - nearest_support) / lp * 100, 2)
        except (TypeError, ValueError):
            pass

    return {
        "symbol": d.get("symbol"),
        "last_price": last_price,
        "last_update": d.get("lastUpdate"),
        "rsi": rsi_f,
        "rsi_signal": rsi_block.get("signal") if isinstance(rsi_block, dict) else None,
        "macd_signal": macd_block.get("signal") if isinstance(macd_block, dict) else None,
        "overall_signal": signals.get("action") or signals.get("overall") or signals.get("recommendation") or rec,
        "overall_trend": trend.get("overallTrend") or trend.get("shortTerm"),
        "trend_strength": trend.get("trendStrength"),
        "rsi_oversold": bool(rsi_f is not None and rsi_f < 30),
        "rsi_deep_oversold": bool(rsi_f is not None and rsi_f < 15),
        "nearest_support": nearest_support,
        "support_distance_pct": support_distance_pct,
        "bb_signal": bb_block.get("signal") if isinstance(bb_block, dict) else None,
        "below_vwap": str(vwap_block.get("signal") or "").upper() == "BELOW",
        "summary": summary,
    }


def slim_bandarmology(data: dict) -> dict[str, Any] | None:
    if not data.get("ok"):
        return None
    root = data.get("data") or {}
    d = root.get("data") if isinstance(root, dict) else root
    if isinstance(d, dict) and "data" in d:
        d = d["data"]
    if not isinstance(d, dict):
        return {"raw": str(root)[:300]}
    return {
        "signal": d.get("signal") or d.get("status") or d.get("verdict"),
        "score": d.get("score") or d.get("confidence"),
        "label": d.get("label") or d.get("detection"),
        "summary": d.get("message") or d.get("summary"),
    }


def slim_sentiment_divergence(data: dict) -> dict[str, Any] | None:
    if not data.get("ok"):
        return None
    root = data.get("data") or {}
    d = root.get("data") if isinstance(root, dict) else root
    if not isinstance(d, dict):
        return {"raw": str(root)[:300]}
    return {
        "retail_sentiment": d.get("retail_sentiment") or d.get("retail"),
        "bandar_sentiment": d.get("bandar_sentiment") or d.get("bandar") or d.get("institutional"),
        "divergence": d.get("divergence") or d.get("divergence_status"),
        "risk_level": d.get("risk_level") or d.get("risk"),
        "summary": d.get("message") or d.get("summary"),
    }


def probe_capabilities(*, focus_symbols: list[str] | None = None) -> dict[str, Any]:
    """Discover working endpoints; write latest.json."""
    focus = focus_symbols or ["BBCA", "BUMI", "TPIA"]
    catalog: list[dict[str, Any]] = []

    def _probe(name: str, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        r = get(path, params, use_cache=True)
        entry = {"name": name, "path": path, "params": params, "ok": r.get("ok"), "reason": r.get("reason")}
        if r.get("ok"):
            entry["preview"] = json.dumps(r.get("data"), default=str)[:400]
        catalog.append(entry)
        return r

    _probe("trending", "/api/main/trending")
    _probe("top_broker_1d", "/api/market-detector/top-broker", {"marketType": "MARKET_TYPE_ALL", "period": "TB_PERIOD_LAST_1_DAY"})
    _probe("top_stock_1d", "/api/market-detector/top-stock", {"marketType": "MARKET_TYPE_ALL", "period": "TB_PERIOD_LAST_1_DAY"})
    for sym in focus:
        _probe(f"emiten_info_{sym}", f"/api/emiten/{sym}/info")
        _probe(f"technical_{sym}", f"/api/analysis/technical/{sym}")
        _probe(f"accumulation_{sym}", f"/api/bandarmology/accumulation-detector/{sym}")
        _probe(f"distribution_{sym}", f"/api/bandarmology/distribution-detector/{sym}")
        _probe(f"smart_money_{sym}", f"/api/bandarmology/smart-money-flow/{sym}")
        _probe(f"retail_bandar_{sym}", f"/api/sentiment/retail-bandar-divergence/{sym}")

    out = {
        "probed_at_utc": datetime.now(UTC).isoformat(),
        "host": HOST,
        "catalog": catalog,
        "working": [c["name"] for c in catalog if c.get("ok")],
        "failed": [{"name": c["name"], "reason": c.get("reason")} for c in catalog if not c.get("ok")],
    }
    CAPABILITY_OUT.parent.mkdir(parents=True, exist_ok=True)
    CAPABILITY_OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out
