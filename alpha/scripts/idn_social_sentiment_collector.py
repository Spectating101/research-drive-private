#!/usr/bin/env python3
"""Collect IDX public / retail sentiment from social-ish APIs.

Sources (best-effort, fail-loud per provider):
  - RapidAPI Indonesia Stock Exchange trending (IDX app retail attention)
  - Reddit IDX communities (OAuth if set, else public JSON with cache fallback)
  - StockTwits macro mood (SPY/BTC/EWJ — global retail risk tone)
  - GDELT entity mention pulse (news attention proxy per ticker)

Outputs:
  data_lake/sentiment/idn_public_sentiment_latest.json
  data_lake/sentiment/idn_public_sentiment_panel.parquet
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
CFG_PATH = REPO / "config/markets/indonesia_social_sentiment.json"

TICKER_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{3,5})(?:\.JK)?(?![A-Za-z0-9])")


def load_config() -> dict[str, Any]:
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


def load_env() -> None:
    for p in [REPO / ".env.local", REPO / ".env", REPO.parent / ".env.local", REPO.parent / ".env"]:
        if p.exists():
            load_dotenv(p, override=False)


def load_liquid() -> list[str]:
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    from run_idn_invest_trial import load_liquid_universe

    return load_liquid_universe()


def _to_jk(sym: str) -> str:
    s = sym.strip().upper()
    if not s:
        return s
    return s if s.endswith(".JK") else f"{s}.JK"


def _alias_map(liquid: list[str], cfg: dict[str, Any]) -> dict[str, str]:
    m: dict[str, str] = {}
    for t in liquid:
        base = t.replace(".JK", "")
        m[base] = t
        m[t] = t
    alias_file = REPO / cfg.get("ticker_aliases_file", "config/ticker_entity_aliases_v2.json")
    if alias_file.exists():
        raw = json.loads(alias_file.read_text(encoding="utf-8"))
        for ent in raw.get("entries", []):
            sym = str(ent.get("yahoo_symbol", ""))
            if not sym.endswith(".JK"):
                continue
            for a in ent.get("aliases", []):
                m[str(a).lower()] = sym
    return m


def _lexicon_score(text: str, cfg: dict[str, Any]) -> dict[str, Any]:
    lex = cfg.get("retail_lexicon", {})
    bull = lex.get("bullish", [])
    bear = lex.get("bearish", [])
    t = text.lower()
    b = sum(1 for w in bull if w in t)
    s = sum(1 for w in bear if w in t)
    total = b + s
    if total == 0:
        label = "neutral"
        score = 0.0
    else:
        score = (b - s) / total
        label = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "mixed"
    return {"bull_hits": b, "bear_hits": s, "sentiment_score": round(score, 3), "sentiment_label": label}


def _extract_tickers(text: str, alias_map: dict[str, str], liquid_set: set[str]) -> list[str]:
    found: set[str] = set()
    for m in TICKER_TOKEN_RE.finditer(text.upper()):
        base = m.group(1)
        if base in alias_map:
            found.add(alias_map[base])
    low = text.lower()
    for alias, sym in alias_map.items():
        if len(alias) >= 3 and alias.isalpha() and alias in low and sym in liquid_set:
            found.add(sym)
    return sorted(found)


def fetch_rapidapi_trending(cfg: dict[str, Any]) -> dict[str, Any]:
    from idn_rapidapi_idx import get

    rap = cfg.get("rapidapi", {})
    if not rap.get("enabled", True):
        return {"ok": False, "reason": "disabled"}
    path = rap.get("endpoints", {}).get("trending", "/api/main/trending")
    r = get(path, cache_ttl_sec=1800)
    if not r.get("ok"):
        return r
    payload = r.get("data") or {}
    items = payload.get("data", {}).get("data", payload.get("data", []))
    if isinstance(items, dict):
        items = items.get("data", [])
    rows = []
    for i, row in enumerate(items or []):
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or row.get("symbol_2") or "")
        rows.append(
            {
                "rank": i + 1,
                "symbol": sym,
                "yahoo_symbol": _to_jk(sym),
                "name": row.get("name"),
                "percent_change": row.get("percent"),
                "last": row.get("last"),
            }
        )
    return {"ok": True, "source": "rapidapi_idx_trending", "count": len(rows), "items": rows[:30], "from_cache": r.get("from_cache")}


def fetch_rapidapi_market_flow(cfg: dict[str, Any]) -> dict[str, Any]:
    from idn_rapidapi_idx import get

    rap = cfg.get("rapidapi", {})
    ep = rap.get("endpoints", {})
    params = {"marketType": "MARKET_TYPE_ALL", "period": "TB_PERIOD_LAST_1_DAY"}
    broker = get(ep.get("top_broker", "/api/market-detector/top-broker"), params, cache_ttl_sec=3600)
    stock = get(ep.get("top_stock", "/api/market-detector/top-stock"), params, cache_ttl_sec=3600)
    return {
        "ok": broker.get("ok") or stock.get("ok"),
        "top_broker": broker,
        "top_stock": stock,
    }


def fetch_rapidapi_symbol_intel(cfg: dict[str, Any], symbols: list[str]) -> dict[str, Any]:
    """Deep dive: technical, bandarmology, retail-vs-bandar per symbol (rate-limited)."""
    from idn_rapidapi_idx import (
        get,
        slim_bandarmology,
        slim_emiten_info,
        slim_sentiment_divergence,
        slim_technical,
    )

    rap = cfg.get("rapidapi", {})
    ep = rap.get("endpoints", {})
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for sym in symbols:
        base = sym.replace(".JK", "").upper()
        if not base:
            continue
        row: dict[str, Any] = {"symbol": base, "yahoo_symbol": _to_jk(base)}
        info = get(ep.get("emiten_info", "/api/emiten/{symbol}/info").format(symbol=base), cache_ttl_sec=3600)
        tech = get(ep.get("technical", "/api/analysis/technical/{symbol}").format(symbol=base), cache_ttl_sec=3600)
        accum = get(ep.get("accumulation", "/api/bandarmology/accumulation-detector/{symbol}").format(symbol=base), cache_ttl_sec=7200)
        dist = get(ep.get("distribution", "/api/bandarmology/distribution-detector/{symbol}").format(symbol=base), cache_ttl_sec=7200)
        sent = get(ep.get("retail_bandar", "/api/sentiment/retail-bandar-divergence/{symbol}").format(symbol=base), cache_ttl_sec=7200)
        row["emiten"] = slim_emiten_info(info)
        row["technical"] = slim_technical(tech)
        # Premium-tier endpoints — skip silently on BASIC if 404
        for key, resp, slim_fn in [
            ("accumulation", accum, slim_bandarmology),
            ("distribution", dist, slim_bandarmology),
            ("retail_vs_bandar", sent, slim_sentiment_divergence),
        ]:
            if resp.get("ok"):
                row[key] = slim_fn(resp)
            elif resp.get("reason") not in ("http_404",):
                errors.append(f"{base}/{key}:{resp.get('reason')}")
        rows.append(row)
    return {"ok": bool(rows), "symbols": rows, "errors": errors[:20]}


def _reddit_oauth_token(cfg: dict[str, Any]) -> str | None:
    load_env()
    oauth_keys = cfg.get("reddit", {}).get("oauth_env", [])
    cid = os.getenv("REDDIT_CLIENT_ID", "").strip()
    secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
    ua = os.getenv("REDDIT_USER_AGENT", cfg.get("reddit", {}).get("user_agent", "bot"))
    if not cid or not secret:
        return None
    auth = requests.auth.HTTPBasicAuth(cid, secret)
    data = {"grant_type": "client_credentials"}
    r = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=auth,
        data=data,
        headers={"User-Agent": ua},
        timeout=30,
    )
    if r.status_code != 200:
        return None
    return r.json().get("access_token")


def fetch_reddit_idx(cfg: dict[str, Any], *, liquid: list[str], alias_map: dict[str, str]) -> dict[str, Any]:
    rd = cfg.get("reddit", {})
    if not rd.get("enabled", True):
        return {"ok": False, "reason": "disabled"}
    liquid_set = set(liquid)
    ua = os.getenv("REDDIT_USER_AGENT", rd.get("user_agent", "bot"))
    token = _reddit_oauth_token(cfg)
    headers = {"User-Agent": ua}
    if token:
        headers["Authorization"] = f"bearer {token}"
    base = "https://oauth.reddit.com" if token else "https://www.reddit.com"

    posts: list[dict[str, Any]] = []
    errors: list[str] = []
    for sub in rd.get("subreddits", []):
        for sort in rd.get("sort_modes", ["new"]):
            sort_path = sort
            if sort.startswith("top"):
                sort_path = "top"
            url = f"{base}/r/{sub}/{sort_path}.json"
            params: dict[str, Any] = {"limit": 50}
            if sort_path == "top":
                params["t"] = rd.get("top_time", "week")
            try:
                r = requests.get(url, params=params, headers=headers, timeout=30)
                if r.status_code != 200:
                    errors.append(f"{sub}/{sort}:http_{r.status_code}")
                    continue
                children = r.json().get("data", {}).get("children", [])
                for ch in children:
                    d = ch.get("data", {})
                    title = str(d.get("title", ""))
                    body = str(d.get("selftext", ""))
                    text = f"{title}\n{body}"
                    tickers = _extract_tickers(text, alias_map, liquid_set)
                    posts.append(
                        {
                            "id": d.get("id"),
                            "subreddit": sub,
                            "created_utc": d.get("created_utc"),
                            "title": title[:300],
                            "score": d.get("score"),
                            "num_comments": d.get("num_comments"),
                            "tickers": tickers,
                            "permalink": d.get("permalink"),
                            **_lexicon_score(text, cfg),
                        }
                    )
            except Exception as exc:
                errors.append(f"{sub}/{sort}:{exc}")
            time.sleep(float(rd.get("sleep_seconds", 1.5)))

    cache_dir = REPO / rd.get("raw_cache_dir", "data_lake/sentiment/reddit_idx/raw")
    if posts:
        cache_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        out = cache_dir / f"{day}_posts.jsonl"
        with out.open("a", encoding="utf-8") as f:
            for p in posts:
                f.write(json.dumps(p, default=str) + "\n")

    if not posts:
        # fallback: read recent cache
        cached: list[dict] = []
        if cache_dir.exists():
            for p in sorted(cache_dir.glob("*_posts.jsonl"), reverse=True)[:3]:
                for line in p.read_text(encoding="utf-8").splitlines():
                    try:
                        cached.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        if cached:
            return {
                "ok": True,
                "source": "reddit_idx_cache",
                "live_fetch": False,
                "errors": errors,
                "post_count": len(cached),
                "posts": cached[:40],
            }
        return {"ok": False, "reason": "no_posts", "errors": errors, "hint": "Set REDDIT_CLIENT_ID/SECRET for OAuth"}

    return {
        "ok": True,
        "source": "reddit_idx_live" if token else "reddit_idx_public",
        "live_fetch": True,
        "errors": errors,
        "post_count": len(posts),
        "posts": posts[:40],
    }


def fetch_stocktwits_macro(cfg: dict[str, Any]) -> dict[str, Any]:
    st = cfg.get("stocktwits_macro", {})
    if not st.get("enabled", True):
        return {"ok": False, "reason": "disabled"}
    rows = []
    for sym in st.get("symbols", ["SPY"]):
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{sym}.json"
        try:
            r = requests.get(url, timeout=20)
            if r.status_code != 200:
                rows.append({"symbol": sym, "ok": False, "reason": f"http_{r.status_code}"})
                continue
            msgs = r.json().get("messages", [])
            bull = bear = neu = 0
            for m in msgs:
                label = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
                if label == "Bullish":
                    bull += 1
                elif label == "Bearish":
                    bear += 1
                else:
                    neu += 1
            total = bull + bear + neu
            rows.append(
                {
                    "symbol": sym,
                    "ok": True,
                    "messages": len(msgs),
                    "bullish": bull,
                    "bearish": bear,
                    "neutral": neu,
                    "bull_ratio": round(bull / total, 3) if total else None,
                    "sample": (msgs[0].get("body", "")[:160] if msgs else None),
                }
            )
        except Exception as exc:
            rows.append({"symbol": sym, "ok": False, "reason": str(exc)})
        time.sleep(float(st.get("sleep_seconds", 0.8)))
    return {"ok": True, "source": "stocktwits_macro", "symbols": rows}


def fetch_entity_mention_pulse(liquid: list[str]) -> dict[str, Any]:
    path = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/ticker_week_entity_market_panel.parquet"
    if not path.exists():
        return {"ok": False, "reason": "entity_panel_missing"}
    e = pd.read_parquet(path)
    e["week_end"] = pd.to_datetime(e["week_end"])
    e = e[(e["country_iso3"] == "IDN") & (e["yahoo_symbol"].isin(liquid))]
    if e.empty:
        return {"ok": False, "reason": "no_rows"}
    wk = e["week_end"].max()
    snap = e[e["week_end"] == wk].copy()
    snap["mention_rank_pct"] = snap["entity_mention_rows"].rank(pct=True, ascending=False)
    rows = []
    for _, r in snap.nlargest(15, "entity_mention_rows").iterrows():
        rows.append(
            {
                "yahoo_symbol": r["yahoo_symbol"],
                "entity_mention_rows": float(r["entity_mention_rows"]) if pd.notna(r["entity_mention_rows"]) else None,
                "mention_rank_pct": float(r["mention_rank_pct"]) if pd.notna(r["mention_rank_pct"]) else None,
                "mean_tone_avg": float(r["mean_tone_avg"]) if pd.notna(r.get("mean_tone_avg")) else None,
                "return_1w": float(r["return_1w"]) if pd.notna(r.get("return_1w")) else None,
            }
        )
    return {
        "ok": True,
        "source": "gdelt_entity_pulse",
        "week_end": str(wk.date()),
        "top_mention": rows,
    }


def build_ticker_pulse(
    *,
    liquid: list[str],
    cfg: dict[str, Any],
    providers: dict[str, Any],
) -> list[dict[str, Any]]:
    liquid_set = set(liquid)
    alias_map = _alias_map(liquid, cfg)
    pulse: dict[str, dict[str, Any]] = {t: {"yahoo_symbol": t, "sources": [], "snippets": []} for t in liquid}

    trending = providers.get("rapidapi_trending", {})
    if trending.get("ok"):
        for item in trending.get("items", []):
            sym = item.get("yahoo_symbol")
            if sym not in liquid_set:
                continue
            row = pulse[sym]
            row["sources"].append("rapidapi_trending")
            row["trending_rank"] = item.get("rank")
            row["trending_pct"] = item.get("percent_change")
            row["attention_score"] = max(row.get("attention_score", 0), 1.0 - (item.get("rank", 30) / 30))

    reddit = providers.get("reddit_idx", {})
    if reddit.get("ok"):
        for post in reddit.get("posts", []):
            for sym in post.get("tickers", []):
                if sym not in pulse:
                    continue
                row = pulse[sym]
                row["sources"].append("reddit_idx")
                row["reddit_mentions"] = row.get("reddit_mentions", 0) + 1
                row["reddit_score_sum"] = row.get("reddit_score_sum", 0) + int(post.get("score") or 0)
                if len(row["snippets"]) < 2:
                    row["snippets"].append(post.get("title", "")[:200])
                lex = _lexicon_score(f"{post.get('title','')}", cfg)
                row["reddit_sentiment_score"] = row.get("reddit_sentiment_score", 0) + lex["sentiment_score"]

    entity = providers.get("entity_mention_pulse", {})
    if entity.get("ok"):
        for item in entity.get("top_mention", []):
            sym = item.get("yahoo_symbol")
            if sym not in pulse:
                continue
            row = pulse[sym]
            row["sources"].append("gdelt_entity")
            row["entity_mention_rows"] = item.get("entity_mention_rows")
            row["mention_rank_pct"] = item.get("mention_rank_pct")
            row["news_tone_avg"] = item.get("mean_tone_avg")

    intel = providers.get("rapidapi_symbol_intel", {})
    for item in intel.get("symbols", []):
        sym = item.get("yahoo_symbol")
        if sym not in pulse:
            continue
        row = pulse[sym]
        row["sources"].append("rapidapi_intel")
        emiten = item.get("emiten") or {}
        if emiten.get("followers"):
            row["app_followers"] = emiten.get("followers")
        tech = item.get("technical") or {}
        if tech.get("rsi") is not None:
            row["api_rsi"] = tech.get("rsi")
        if tech.get("overall_signal") or tech.get("rsi_signal"):
            row["api_technical_signal"] = tech.get("overall_signal") or tech.get("rsi_signal")
        rvb = item.get("retail_vs_bandar") or {}
        if rvb.get("divergence") or rvb.get("risk_level"):
            row["retail_bandar_divergence"] = rvb
        accum = item.get("accumulation") or {}
        dist = item.get("distribution") or {}
        if accum.get("signal"):
            row["bandar_accumulation"] = accum
        if dist.get("signal"):
            row["bandar_distribution"] = dist
        if tech.get("overall_signal"):
            row["api_technical_signal"] = tech["overall_signal"]

    out = []
    for sym, row in pulse.items():
        if len(row.get("sources", [])) == 0:
            continue
        srcs = sorted(set(row.get("sources", [])))
        att = float(row.get("attention_score", 0))
        if row.get("reddit_mentions"):
            att += min(1.0, row["reddit_mentions"] / 5)
        if row.get("mention_rank_pct"):
            att += float(row["mention_rank_pct"])
        if row.get("app_followers"):
            att += min(0.4, float(row["app_followers"]) / 10_000_000)
        if row.get("retail_bandar_divergence"):
            att += 0.3
        rs = row.get("reddit_sentiment_score")
        if rs is not None:
            label = "bullish" if rs > 0 else "bearish" if rs < 0 else "mixed"
        elif row.get("trending_pct"):
            try:
                label = "bullish" if float(str(row["trending_pct"]).replace("+", "")) > 0 else "bearish"
            except ValueError:
                label = "mixed"
        else:
            label = "attention_only"
        out.append(
            {
                "yahoo_symbol": sym,
                "attention_score": round(att, 3),
                "sentiment_label": label,
                "sources": srcs,
                "trending_rank": row.get("trending_rank"),
                "reddit_mentions": row.get("reddit_mentions"),
                "entity_mention_rows": row.get("entity_mention_rows"),
                "app_followers": row.get("app_followers"),
                "api_rsi": row.get("api_rsi"),
                "retail_bandar_divergence": row.get("retail_bandar_divergence"),
                "bandar_accumulation": row.get("bandar_accumulation"),
                "api_technical_signal": row.get("api_technical_signal"),
                "snippets": row.get("snippets", [])[:2],
            }
        )
    return sorted(out, key=lambda x: -x["attention_score"])[:25]


def collect(*, liquid: list[str] | None = None, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    liquid = liquid or load_liquid()
    load_env()

    providers: dict[str, Any] = {}
    providers["rapidapi_trending"] = fetch_rapidapi_trending(cfg)
    providers["rapidapi_market_flow"] = fetch_rapidapi_market_flow(cfg)

    deep_n = int(cfg.get("rapidapi", {}).get("deep_dive_top_n", 8))
    trending_syms = [
        x.get("yahoo_symbol")
        for x in providers.get("rapidapi_trending", {}).get("items", [])[:deep_n]
        if x.get("yahoo_symbol")
    ]
    # Always include core banks if in liquid set
    for s in ("BBCA.JK", "BBRI.JK", "BMRI.JK"):
        if s in liquid and s not in trending_syms:
            trending_syms.append(s)
    providers["rapidapi_symbol_intel"] = fetch_rapidapi_symbol_intel(cfg, trending_syms[:deep_n + 3])

    providers["reddit_idx"] = fetch_reddit_idx(cfg, liquid=liquid, alias_map=_alias_map(liquid, cfg))
    providers["stocktwits_macro"] = fetch_stocktwits_macro(cfg)
    providers["entity_mention_pulse"] = fetch_entity_mention_pulse(liquid)

    ticker_pulse = build_ticker_pulse(liquid=liquid, cfg=cfg, providers=providers)

    return {
        "collected_at_utc": datetime.now(UTC).isoformat(),
        "providers": providers,
        "ticker_pulse": ticker_pulse,
        "retail_mood_macro": providers.get("stocktwits_macro"),
        "notes": (
            "IDX retail attention: RapidAPI trending + retail-vs-bandar divergence + bandarmology + "
            "market flow (top broker/stock). Reddit IDX optional (OAuth). Instagram not available via API — "
            "IDX app trending is the closest retail-attention proxy."
        ),
    }


def append_trending_history(trending: dict[str, Any]) -> Path | None:
    items = trending.get("items") or []
    if not trending.get("ok") or not items:
        return None
    day = datetime.now(UTC).date().isoformat()
    rows = [
        {
            "snapshot_date": day,
            "yahoo_symbol": it.get("yahoo_symbol"),
            "trending_rank": it.get("rank"),
            "percent_change": it.get("percent_change"),
            "last": it.get("last"),
            "name": it.get("name"),
        }
        for it in items
    ]
    path = REPO / "data_lake/sentiment/idn_rapidapi_trending_history.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    if path.exists():
        old = pd.read_parquet(path)
        old = old[old["snapshot_date"] != day]
        df = pd.concat([old, df], ignore_index=True)
    df.to_parquet(path, index=False)
    return path


def write_outputs(payload: dict[str, Any], cfg: dict[str, Any] | None = None) -> tuple[Path, Path]:
    cfg = cfg or load_config()
    jpath = REPO / cfg.get("output_json", "data_lake/sentiment/idn_public_sentiment_latest.json")
    ppath = REPO / cfg.get("output_parquet", "data_lake/sentiment/idn_public_sentiment_panel.parquet")
    jpath.parent.mkdir(parents=True, exist_ok=True)
    jpath.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    append_trending_history(payload.get("providers", {}).get("rapidapi_trending", {}))

    rows = payload.get("ticker_pulse", [])
    if rows:
        df = pd.DataFrame(rows)
        df["collected_at_utc"] = payload.get("collected_at_utc")
        if ppath.exists():
            old = pd.read_parquet(ppath)
            df = pd.concat([old, df], ignore_index=True)
        df.to_parquet(ppath, index=False)
    return jpath, ppath


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--print", action="store_true", help="Print summary JSON to stdout.")
    args = ap.parse_args()
    payload = collect()
    jpath, ppath = write_outputs(payload)
    summary = {
        "json": str(jpath),
        "parquet": str(ppath),
        "ticker_pulse_n": len(payload.get("ticker_pulse", [])),
        "rapidapi_ok": payload.get("providers", {}).get("rapidapi_trending", {}).get("ok"),
        "reddit_ok": payload.get("providers", {}).get("reddit_idx", {}).get("ok"),
    }
    print(json.dumps(summary, indent=2))
    if args.print:
        print(json.dumps(payload, indent=2, default=str)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
