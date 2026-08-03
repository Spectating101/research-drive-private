#!/usr/bin/env python3
"""Post-mortem explainer for IDX daily spike days (+10% / ARA limits).

Combines: yfinance OHLCV, peer-group sync, index-event calendar, optional GDELT entity
mentions, optional DeepSeek one-paragraph synthesis.

Not predictive — explains likely drivers after the move.

Examples:
  python scripts/idn_spike_explainer.py --symbol BREN.JK --date 2026-05-29
  python scripts/idn_spike_explainer.py --scan --min-pct 10 --days 21
  python scripts/idn_spike_explainer.py --symbol TPIA.JK --date 2026-06-08 --llm deepseek
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from idn_bandar_collector import broker_context_for_spike
from idn_bandar_lite import bandar_lite_features, bandar_lite_hypotheses

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

OUT = REPO / "backtests/outputs/idn_spike_explainer"
GROUPS_CFG = REPO / "config/markets/indonesia_stock_groups.json"
EVENTS_CFG = REPO / "config/markets/indonesia_index_events.json"
UNIVERSE_CFG = REPO / "config/markets/asia_yfinance_universes.json"
ENTITY_PANEL = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/daily_ticker_entity_shock_panel.csv"

ARA_BANDS = [(0.245, "25% ARA (upper auto-rejection)"), (0.195, "20% ARA"), (0.095, "10% ARA")]


def load_universe() -> list[str]:
    cfg = json.loads(UNIVERSE_CFG.read_text(encoding="utf-8"))
    for u in cfg.get("universes", []):
        if u.get("id") == "indonesia_liquid_core":
            return list(u["tickers"])
    raise SystemExit("indonesia_liquid_core not found")


def load_groups() -> dict[str, dict]:
    if not GROUPS_CFG.exists():
        return {}
    return json.loads(GROUPS_CFG.read_text(encoding="utf-8")).get("groups", {})


def load_index_events() -> list[dict]:
    if not EVENTS_CFG.exists():
        return []
    return json.loads(EVENTS_CFG.read_text(encoding="utf-8")).get("events", [])


def fetch_history(
    symbols: list[str],
    start: str,
    end: str,
    *,
    timeout_sec: float = 45.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download OHLCV via yfinance with a hard timeout (default 45s)."""
    import yfinance as yf
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    def _download():
        return yf.download(symbols, start=start, end=end, progress=False, auto_adjust=True)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            raw = pool.submit(_download).result(timeout=timeout_sec)
    except FuturesTimeout:
        raise TimeoutError(
            f"yfinance download timed out after {timeout_sec:.0f}s for {len(symbols)} symbols"
        ) from None
    if raw is None or raw.empty:
        return pd.DataFrame(), pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"].copy()
        vol = raw["Volume"].copy()
    else:
        close = raw[["Close"]].rename(columns={"Close": symbols[0]})
        vol = raw[["Volume"]].rename(columns={"Volume": symbols[0]})
    close.index = pd.to_datetime(close.index).tz_localize(None)
    vol.index = pd.to_datetime(vol.index).tz_localize(None)
    return close.sort_index(), vol.sort_index()


def classify_ara(ret: float) -> str | None:
    for thr, label in ARA_BANDS:
        if ret >= thr - 0.005:
            return label
    return None


def volume_ratio(vol_today: float, vol_hist: pd.Series) -> float:
    h = pd.to_numeric(vol_hist, errors="coerce").dropna()
    if len(h) < 5 or not np.isfinite(vol_today):
        return float("nan")
    mu = float(h.mean())
    return float(vol_today / mu) if mu > 0 else float("nan")


def gdelt_entity_day(symbol: str, date: pd.Timestamp) -> dict[str, Any]:
    if not ENTITY_PANEL.exists():
        return {"available": False}
    usecols = lambda c: c in {"date", "yahoo_symbol", "entity_mention_rows", "mean_tone_avg"} or c.endswith("_rows")
    ent = pd.read_csv(ENTITY_PANEL, parse_dates=["date"], usecols=usecols)
    row = ent[(ent["yahoo_symbol"] == symbol) & (ent["date"].dt.normalize() == date.normalize())]
    if row.empty:
        return {"available": True, "matched": False, "entity_mention_rows": 0}
    r = row.iloc[0]
    shocks = {c: float(r[c]) for c in row.index if c.endswith("_rows") and pd.notna(r[c]) and float(r[c]) > 0}
    return {
        "available": True,
        "matched": True,
        "entity_mention_rows": int(r.get("entity_mention_rows", 0) or 0),
        "mean_tone_avg": float(r["mean_tone_avg"]) if pd.notna(r.get("mean_tone_avg")) else None,
        "shock_rows": shocks,
    }


def index_events_for(symbol: str, date: pd.Timestamp) -> list[dict]:
    hits = []
    d = date.strftime("%Y-%m-%d")
    for ev in load_index_events():
        eff = ev.get("effective_date", "")
        window_start = (pd.Timestamp(eff) - timedelta(days=5)).strftime("%Y-%m-%d") if eff else ""
        window_end = (pd.Timestamp(eff) + timedelta(days=3)).strftime("%Y-%m-%d") if eff else ""
        if not (window_start <= d <= window_end):
            continue
        removed = ev.get("removed_msci_global_standard", []) + ev.get("removed_msci_global_small", [])
        if symbol in removed or not removed:
            hits.append(
                {
                    "id": ev.get("id"),
                    "type": ev.get("type"),
                    "title": ev.get("title"),
                    "effective_date": eff,
                    "symbol_listed_in_event": symbol in removed,
                    "narrative": ev.get("narrative"),
                }
            )
    return hits


def peer_moves(symbol: str, date: pd.Timestamp, prices: pd.DataFrame, min_pct: float = 0.08) -> list[dict]:
    groups = load_groups()
    peers: list[str] = []
    labels: list[str] = []
    for g in groups.values():
        if symbol in g.get("tickers", []):
            peers.extend([t for t in g["tickers"] if t != symbol])
            labels.append(g.get("label", ""))
    peers = sorted(set(peers))
    if not peers or date not in prices.index:
        return []

    idx = prices.index.get_loc(date)
    if idx == 0:
        return []
    prev = prices.index[idx - 1]
    rows = []
    for p in peers:
        if p not in prices.columns:
            continue
        r = float(prices.loc[date, p] / prices.loc[prev, p] - 1.0)
        if r >= min_pct:
            rows.append({"symbol": p, "return_pct": round(r * 100, 2)})
    rows.sort(key=lambda x: x["return_pct"], reverse=True)
    return [{"group": labels[0] if labels else "", "peers_up": rows}]


def rule_hypotheses(facts: dict) -> list[dict]:
    hyps: list[dict] = []
    ret = facts["return_pct"] / 100.0
    ara = facts.get("ara_label")

    if ara:
        hyps.append(
            {
                "id": "ara_limit",
                "confidence": 0.85,
                "text": f"Hit {ara} — price locked at exchange upper band; often flow-driven (aggressive domestic buying or short squeeze), not a slow fundamental drift.",
            }
        )

    p5 = facts.get("prior_5d_return_pct")
    if p5 is not None and p5 < -10:
        hyps.append(
            {
                "id": "drawdown_bounce",
                "confidence": 0.7,
                "text": f"Sharp bounce after {facts['prior_5d_return_pct']:+.1f}% 5-day drawdown — classic IDX mean-reversion / squeeze on a beaten-down name.",
            }
        )

    vr = facts.get("volume_ratio_20d")
    if vr is not None and vr >= 2.5:
        hyps.append(
            {
                "id": "volume_surge",
                "confidence": 0.75,
                "text": f"Volume ~{vr:.1f}× 20-day average — organized accumulation or index/foreign-flow adjustment, not thin retail noise.",
            }
        )

    peers = facts.get("peer_sync", [])
    if peers and peers[0].get("peers_up") and len(peers[0]["peers_up"]) >= 2:
        names = ", ".join(p["symbol"] for p in peers[0]["peers_up"][:4])
        hyps.append(
            {
                "id": "group_move",
                "confidence": 0.8,
                "text": f"Synchronized move with group peers ({names}) — likely shared catalyst (ownership group, sector, or index event), not idiosyncratic single-name news.",
            }
        )

    for ev in facts.get("index_events", []):
        if ev.get("symbol_listed_in_event"):
            hyps.append(
                {
                    "id": "index_rebalance",
                    "confidence": 0.9,
                    "text": (
                        f"Within window of {ev.get('title')} — removals often imply foreign passive selling, "
                        "but May 2026 pattern was domestic buyers absorbing at ARA (counter-intuitive rally)."
                    ),
                }
            )

    gd = facts.get("gdelt_entity", {})
    if gd.get("matched") and gd.get("entity_mention_rows", 0) > 0:
        hyps.append(
            {
                "id": "gdelt_entity",
                "confidence": 0.55,
                "text": f"GDELT captured {gd['entity_mention_rows']} entity-linked mentions that day — partial headline support (coverage often lags IDX-local disclosures).",
            }
        )
    elif gd.get("available"):
        hyps.append(
            {
                "id": "gdelt_silent",
                "confidence": 0.65,
                "text": "No ticker-level GDELT entity mentions that day — catalyst is likely local (BEI filing, broker flow, index rebalance) rather than global headline news.",
            }
        )

    hyps.extend(bandar_lite_hypotheses(facts))

    bb = facts.get("bandar_broker") or {}
    if bb.get("available"):
        hyps.append(
            {
                "id": "broker_flow",
                "confidence": 0.72,
                "text": bb.get("summary_text", "Broker summary available for spike day."),
            }
        )

    if not hyps:
        hyps.append(
            {
                "id": "unknown",
                "confidence": 0.3,
                "text": "No strong automated hypothesis — manual check IDX disclosures and local financial press required.",
            }
        )

    return sorted(hyps, key=lambda x: x["confidence"], reverse=True)


def synthesize_paragraph(facts: dict, hypotheses: list[dict], backend: str) -> str:
    if backend == "skip":
        top = hypotheses[:3]
        lines = [f"{h['text']} (conf {h['confidence']:.0%})" for h in top]
        return "Likely drivers:\n" + "\n".join(f"- {x}" for x in lines)

    from dotenv import load_dotenv

    for p in [REPO / ".env.local", REPO.parent / ".env.local"]:
        if p.exists():
            load_dotenv(p, override=False)

    system = (
        "You write short IDX post-mortem notes for traders. Use ONLY the JSON facts. "
        "One paragraph, plain English, mention ARA/index/flow/group if present. "
        "Say explicitly if GDELT did not capture the catalyst. No hype."
    )
    user = json.dumps({"facts": facts, "hypotheses": hypotheses}, indent=2, default=str)
    if backend in {"auto", "deepseek"} and os.getenv("DEEPSEEK_API_KEY"):
        body = json.dumps(
            {
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                "temperature": 0.2,
                "max_tokens": 400,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            }
        ).encode()
        req = urllib.request.Request(
            os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions"),
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            payload = json.loads(resp.read().decode())
        return payload["choices"][0]["message"]["content"]

    return synthesize_paragraph(facts, hypotheses, "skip")


def explain_spike(symbol: str, date: str, llm: str = "skip") -> dict:
    symbol = symbol.upper() if ".JK" in symbol.upper() else f"{symbol.upper()}.JK"
    dt = pd.Timestamp(date).normalize()
    start = (dt - timedelta(days=90)).strftime("%Y-%m-%d")
    end = (dt + timedelta(days=5)).strftime("%Y-%m-%d")

    universe = load_universe()
    groups = load_groups()
    extra_peers: list[str] = []
    for g in groups.values():
        if symbol in g.get("tickers", []):
            extra_peers.extend(g["tickers"])
    scan_syms = sorted(set(universe + [symbol] + extra_peers))
    px, vol_px = fetch_history(scan_syms, start, end)
    if symbol not in px.columns or dt not in px.index:
        raise SystemExit(f"No price for {symbol} on {dt.date()} (have cols={symbol in px.columns}, dates through {px.index.max()})")

    loc = px.index.get_loc(dt)
    if loc == 0:
        raise SystemExit("Need prior day for return")
    prev = px.index[loc - 1]
    ret = float(px.loc[dt, symbol] / px.loc[prev, symbol] - 1.0)

    hist = px[symbol].iloc[max(0, loc - 20) : loc]
    mom5 = float(px.loc[dt, symbol] / px.loc[px.index[max(0, loc - 5)], symbol] - 1.0) if loc >= 5 else float("nan")
    mom20 = float(px.loc[dt, symbol] / px.loc[px.index[max(0, loc - 20)], symbol] - 1.0) if loc >= 20 else float("nan")

    vol_today = float(vol_px.loc[dt, symbol]) if symbol in vol_px.columns else float("nan")
    vol_hist = vol_px[symbol].iloc[max(0, loc - 20) : loc] if symbol in vol_px.columns else pd.Series(dtype=float)

    facts: dict[str, Any] = {
        "symbol": symbol,
        "date": str(dt.date()),
        "prior_date": str(prev.date()),
        "close": float(px.loc[dt, symbol]),
        "prior_close": float(px.loc[prev, symbol]),
        "return_pct": round(ret * 100, 2),
        "ara_label": classify_ara(ret),
        "prior_1d_return_pct": round(float(px.loc[prev, symbol] / px.loc[px.index[max(0, loc - 2)], symbol] - 1.0) * 100, 2)
        if loc >= 2
        else None,
        "prior_5d_return_pct": round(mom5 * 100, 2) if np.isfinite(mom5) else None,
        "prior_20d_return_pct": round(mom20 * 100, 2) if np.isfinite(mom20) else None,
        "volume_ratio_20d": round(volume_ratio(vol_today, vol_hist), 2) if len(vol_hist) else None,
        "index_events": index_events_for(symbol, dt),
        "peer_sync": peer_moves(symbol, dt, px),
        "gdelt_entity": gdelt_entity_day(symbol, dt),
        "bandar_lite": bandar_lite_features(px[symbol], vol_px[symbol] if symbol in vol_px.columns else pd.Series(dtype=float), dt),
        "bandar_broker": broker_context_for_spike(symbol, str(dt.date())),
    }

    hypotheses = rule_hypotheses(facts)
    narrative = synthesize_paragraph(facts, hypotheses, llm)

    return {
        "facts": facts,
        "hypotheses": hypotheses,
        "narrative": narrative,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }


def scan_spikes(min_pct: float, days: int) -> list[dict]:
    universe = load_universe()
    end = datetime.now(UTC).date()
    start = (datetime.now(UTC) - timedelta(days=days + 5)).date()
    px, _ = fetch_history(universe, str(start), str(end + timedelta(days=1)))
    rows = []
    for sym in universe:
        if sym not in px.columns:
            continue
        s = px[sym].pct_change().dropna()
        for dt, r in s.items():
            if r * 100 >= min_pct:
                rows.append({"symbol": sym, "date": str(pd.Timestamp(dt).date()), "return_pct": round(float(r) * 100, 2)})
    rows.sort(key=lambda x: x["return_pct"], reverse=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", help="Yahoo symbol e.g. BREN.JK")
    ap.add_argument("--date", help="Spike session date YYYY-MM-DD")
    ap.add_argument("--scan", action="store_true", help="Scan liquid universe for recent spikes")
    ap.add_argument("--min-pct", type=float, default=10.0)
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--llm", choices=["skip", "auto", "deepseek"], default="auto")
    ap.add_argument("--explain-top", type=int, default=3, help="With --scan, explain top N spikes")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)

    if args.scan:
        spikes = scan_spikes(args.min_pct, args.days)
        print(f"Found {len(spikes)} sessions >= {args.min_pct}% in last {args.days}d")
        for row in spikes[:15]:
            print(f"  {row['date']} {row['symbol']:10} {row['return_pct']:+.1f}%")
        (OUT / "scan_latest.json").write_text(json.dumps(spikes, indent=2), encoding="utf-8")

        for row in spikes[: args.explain_top]:
            print("\n" + "=" * 72)
            rep = explain_spike(row["symbol"], row["date"], args.llm)
            slug = f"{row['symbol'].replace('.','_')}_{row['date']}"
            (OUT / f"{slug}.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
            (OUT / f"{slug}.md").write_text(f"# {row['symbol']} {row['date']} (+{row['return_pct']}%)\n\n{rep['narrative']}\n", encoding="utf-8")
            print(rep["narrative"])
        return 0

    if not args.symbol or not args.date:
        ap.error("Provide --symbol and --date, or use --scan")

    rep = explain_spike(args.symbol, args.date, args.llm)
    slug = f"{args.symbol.replace('.','_')}_{args.date}"
    (OUT / f"{slug}.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    (OUT / f"{slug}.md").write_text(
        f"# {args.symbol} {args.date} ({rep['facts']['return_pct']:+.1f}%)\n\n{rep['narrative']}\n",
        encoding="utf-8",
    )

    print(json.dumps(rep["facts"], indent=2, default=str))
    print("\n--- Hypotheses ---")
    for h in rep["hypotheses"][:5]:
        print(f"  [{h['confidence']:.0%}] {h['id']}: {h['text']}")
    print("\n--- Narrative ---\n")
    print(rep["narrative"])
    print(f"\nWrote {OUT / slug}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
