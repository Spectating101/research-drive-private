"""Self-serve fry data collection — structural, attention, broker queue.

Lanes (all runnable without paid vendors beyond RapidAPI):
  - structural: free float, board, insider holder %, app followers
  - attention: IDX trending snapshot + fry symbol ranks
  - broker: refresh fry_trigger_broker_queue + optional backfill hook
  - reddit: scan IDX subs for fry ticker mentions (public/OAuth)
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
CFG_PATH = REPO / "config/markets/indonesia_fry_data_collection.json"
FRY_DIR = REPO / "data_lake/research_panels/idn_fry_episode"
TRIGGERS_PATH = FRY_DIR / "trigger_enriched.parquet"

TICKER_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{3,5})(?:\.JK)?(?![A-Za-z0-9])")


def load_config() -> dict[str, Any]:
    if CFG_PATH.exists():
        return json.loads(CFG_PATH.read_text(encoding="utf-8"))
    return {}


def _out_path(key: str) -> Path:
    cfg = load_config()
    rel = (cfg.get("outputs") or {}).get(key, f"data_lake/research_panels/idn_fry_episode/{key}")
    return REPO / rel


def _cache_dir() -> Path:
    cfg = load_config()
    rel = cfg.get("emiten_cache_dir", "data_lake/research_panels/idn_fry_episode/emiten_cache")
    p = REPO / rel
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_fry_symbols() -> list[str]:
    if not TRIGGERS_PATH.exists():
        return []
    df = pd.read_parquet(TRIGGERS_PATH, columns=["yahoo_symbol"])
    return sorted(df["yahoo_symbol"].dropna().unique().tolist())


def load_fry_triggers() -> pd.DataFrame:
    if not TRIGGERS_PATH.exists():
        return pd.DataFrame()
    df = pd.read_parquet(TRIGGERS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _base_symbol(yahoo_symbol: str) -> str:
    return yahoo_symbol.replace(".JK", "").upper()


def _cache_file(symbol: str, lane: str) -> Path:
    return _cache_dir() / f"{_base_symbol(symbol)}_{lane}.json"


def _read_cached(symbol: str, lane: str, ttl_sec: int) -> dict[str, Any] | None:
    path = _cache_file(symbol, lane)
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > ttl_sec:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_cached(symbol: str, lane: str, payload: dict[str, Any]) -> None:
    path = _cache_file(symbol, lane)
    path.write_text(json.dumps(payload, default=str), encoding="utf-8")


def fetch_emiten_lane(
    symbol: str,
    lane: str,
    *,
    use_cache: bool = True,
    cache_ttl_sec: int = 86400,
    live_budget: list[int] | None = None,
) -> dict[str, Any]:
    """Fetch profile | insider | info for one symbol."""
    from idn_rapidapi_idx import get

    cfg = load_config()
    rap = cfg.get("rapidapi", {})
    path_tpl = {
        "profile": rap.get("profile_path", "/api/emiten/{symbol}/profile"),
        "insider": rap.get("insider_path", "/api/emiten/{symbol}/insider"),
        "info": rap.get("info_path", "/api/emiten/{symbol}/info"),
        "technical": rap.get("technical_path", "/api/analysis/technical/{symbol}"),
    }.get(lane)
    if not path_tpl:
        return {"ok": False, "reason": f"unknown_lane_{lane}"}

    if use_cache:
        cached = _read_cached(symbol, lane, cache_ttl_sec)
        if cached is not None:
            cached["from_disk_cache"] = True
            return cached

    base = _base_symbol(symbol)
    path = path_tpl.format(symbol=base)

    allow_live = live_budget is None or live_budget[0] > 0
    if not allow_live:
        result = get(path, use_cache=True, cache_only=True, cache_ttl_sec=cache_ttl_sec)
        result["lane"] = lane
        result["yahoo_symbol"] = f"{base}.JK"
        if result.get("ok"):
            result["from_shared_cache"] = True
            _write_cached(symbol, lane, result)
        else:
            result["reason"] = result.get("reason") or "live_budget_exhausted"
        return result

    if live_budget is not None:
        live_budget[0] -= 1

    result = get(path, use_cache=True, cache_ttl_sec=cache_ttl_sec)
    result["lane"] = lane
    result["yahoo_symbol"] = f"{base}.JK"
    if result.get("ok"):
        _write_cached(symbol, lane, result)
    return result


def parse_structural_row(
    symbol: str,
    profile: dict[str, Any] | None,
    insider: dict[str, Any] | None,
    info: dict[str, Any] | None,
) -> dict[str, Any]:
    from idn_rapidapi_idx import slim_emiten_info, slim_emiten_insider, slim_emiten_profile

    row: dict[str, Any] = {
        "yahoo_symbol": symbol if symbol.endswith(".JK") else f"{symbol}.JK",
        "collected_at_utc": datetime.now(UTC).isoformat(),
        "profile_ok": bool(profile and profile.get("ok")),
        "insider_ok": bool(insider and insider.get("ok")),
        "info_ok": bool(info and info.get("ok")),
    }
    prof = slim_emiten_profile(profile) if profile else None
    ins = slim_emiten_insider(insider) if insider else None
    inf = slim_emiten_info(info) if info else None
    if prof:
        row.update({k: v for k, v in prof.items() if k != "yahoo_symbol"})
    if ins:
        row.update(ins)
    if inf:
        row["app_followers"] = inf.get("followers")
        row["emiten_name"] = inf.get("name")
        row["last_price"] = inf.get("last")
        if not row.get("sector"):
            row["sector"] = inf.get("sector")
        for k in ("idx_memberships", "is_trading_limit", "is_daytrade", "is_idx_liquid"):
            if inf.get(k) is not None:
                row[k] = inf.get(k)
    ff = row.get("free_float_pct")
    th = row.get("top_holder_pct")
    row["controller_ownership_pct"] = th
    row["low_free_float"] = bool(ff is not None and ff < 5.0)
    row["ultra_low_free_float"] = bool(ff is not None and ff < 1.0)
    row["structurally_fryable"] = bool(
        row.get("low_free_float")
        or row.get("is_watchlist_board")
        or row.get("is_acceleration_board")
        or row.get("is_trading_limit")
    )
    return row


def _load_cached_emiten_lane(symbol: str, lane: str) -> dict[str, Any] | None:
    path = _cache_file(symbol, lane)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def enrich_structural_from_emiten_cache(symbols: list[str] | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Re-parse structural fields from on-disk emiten cache (no live API)."""
    symbols = symbols or load_fry_symbols()
    rows: list[dict[str, Any]] = []
    stats = {"symbols": len(symbols), "parsed": 0, "missing_cache": 0}
    for sym in symbols:
        profile = _load_cached_emiten_lane(sym, "profile")
        insider = _load_cached_emiten_lane(sym, "insider")
        info = _load_cached_emiten_lane(sym, "info")
        if not any([profile, insider, info]):
            stats["missing_cache"] += 1
            continue
        rows.append(parse_structural_row(sym, profile, insider, info))
        stats["parsed"] += 1

    if not rows:
        return load_structural_panel(), stats

    df = pd.DataFrame(rows)
    out = _out_path("structural_panel")
    if out.exists():
        prior = pd.read_parquet(out)
        prior = prior[~prior["yahoo_symbol"].isin(df["yahoo_symbol"])]
        df = pd.concat([prior, df], ignore_index=True)
    df = df.sort_values("yahoo_symbol").drop_duplicates("yahoo_symbol", keep="last")
    df.to_parquet(out, index=False)
    stats["output"] = str(out)
    stats["n_rows"] = len(df)
    merge_structural_into_triggers(structural=df)
    return df, stats


def fetch_technical_lane(
    symbol: str,
    *,
    use_cache: bool = True,
    cache_ttl_sec: int = 43200,
    live_budget: list[int] | None = None,
) -> dict[str, Any]:
    return fetch_emiten_lane(
        symbol,
        "technical",
        use_cache=use_cache,
        cache_ttl_sec=cache_ttl_sec,
        live_budget=live_budget,
    )


def parse_technical_row(symbol: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    from idn_rapidapi_idx import slim_technical_extended

    ysym = symbol if symbol.endswith(".JK") else f"{symbol}.JK"
    row: dict[str, Any] = {
        "yahoo_symbol": ysym,
        "technical_ok": False,
        "fetched_at_utc": datetime.now(UTC).isoformat(),
    }
    if not payload or not payload.get("ok"):
        row["technical_reason"] = (payload or {}).get("reason", "missing")
        return row
    slim = slim_technical_extended(payload)
    if not slim:
        row["technical_reason"] = "parse_failed"
        return row
    row.update(slim)
    row["technical_ok"] = True
    return row


def collect_technical_symbol_panel(
    symbols: list[str] | None = None,
    *,
    max_live_calls: int = 50,
    use_cache: bool = True,
    only_missing: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Current technical snapshot per fry symbol (live API — not historical as-of trigger)."""
    out = _out_path("technical_panel")
    prior = pd.read_parquet(out) if out.exists() else pd.DataFrame()
    symbols = symbols or load_fry_symbols()
    if only_missing and not prior.empty and "technical_ok" in prior.columns:
        missing = prior[~prior["technical_ok"].fillna(False)]["yahoo_symbol"].tolist()
        have = set(prior[prior["technical_ok"].fillna(False)]["yahoo_symbol"])
        symbols = [s for s in symbols if s not in have]
        symbols = missing + [s for s in symbols if s not in set(missing)]
    symbols = prioritize_fry_symbols(symbols)[: max(max_live_calls * 3, max_live_calls)]
    budget = [max_live_calls]
    rows: list[dict[str, Any]] = []
    stats = {"symbols": len(symbols), "live_calls": 0, "ok": 0}

    for sym in symbols:
        payload = fetch_technical_lane(sym, use_cache=use_cache, live_budget=budget)
        if payload.get("ok") and not payload.get("from_disk_cache"):
            stats["live_calls"] += 1
        row = parse_technical_row(sym, payload)
        if row.get("technical_ok"):
            stats["ok"] += 1
        rows.append(row)

    df = pd.DataFrame(rows)
    out = _out_path("technical_panel")
    out.parent.mkdir(parents=True, exist_ok=True)
    if not prior.empty:
        prior = prior[~prior["yahoo_symbol"].isin(df["yahoo_symbol"])]
        df = pd.concat([prior, df], ignore_index=True)
    df = df.sort_values("yahoo_symbol").drop_duplicates("yahoo_symbol", keep="last")
    df.to_parquet(out, index=False)
    stats["output"] = str(out)
    stats["n_rows"] = len(df)
    stats["live_budget_remaining"] = budget[0]
    return df, stats


def collect_technical_trigger_panel(
    *,
    max_live_calls: int = 30,
    max_days_after_trigger: int = 21,
    use_cache: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Attach technical snapshots to recent trigger episodes (prioritize freshest triggers)."""
    trig = load_fry_triggers()
    if trig.empty or "episode_id" not in trig.columns:
        return pd.DataFrame(), {"skipped": True, "reason": "no_triggers"}

    out = _out_path("technical_trigger_panel")
    existing = pd.read_parquet(out) if out.exists() else pd.DataFrame()
    have_eps = set(existing["episode_id"].astype(str)) if not existing.empty and "episode_id" in existing.columns else set()

    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    pending = trig[~trig["episode_id"].astype(str).isin(have_eps)].copy()
    pending["days_after_trigger"] = (now - pending["date"]).dt.days
    pending = pending[pending["days_after_trigger"] <= max_days_after_trigger]
    pending = pending.sort_values("date", ascending=False)

    budget = [max_live_calls]
    fetched_symbols: dict[str, dict[str, Any]] = {}
    new_rows: list[dict[str, Any]] = []
    stats = {"pending_episodes": int(len(pending)), "live_calls": 0, "episodes_written": 0}

    for _, tr in pending.iterrows():
        if budget[0] <= 0:
            break
        sym = str(tr["yahoo_symbol"])
        if sym not in fetched_symbols:
            payload = fetch_technical_lane(sym, use_cache=use_cache, live_budget=budget)
            if payload.get("ok") and not payload.get("from_disk_cache"):
                stats["live_calls"] += 1
            fetched_symbols[sym] = parse_technical_row(sym, payload)
        base = fetched_symbols[sym].copy()
        base["episode_id"] = tr["episode_id"]
        base["trigger_date"] = tr["date"]
        base["days_after_trigger"] = int(tr["days_after_trigger"])
        base["technical_near_trigger"] = base["days_after_trigger"] <= 7
        new_rows.append(base)
        stats["episodes_written"] += 1

    if new_rows:
        df = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True) if not existing.empty else pd.DataFrame(new_rows)
        df = df.drop_duplicates("episode_id", keep="last")
        df.to_parquet(out, index=False)
    else:
        df = existing

    stats["output"] = str(out)
    stats["n_rows"] = int(len(df))
    stats["live_budget_remaining"] = budget[0]
    return df, stats


def prioritize_fry_symbols(symbols: list[str], trig: pd.DataFrame | None = None) -> list[str]:
    """Order symbols: most triggers + deepest DD first (not alphabetical)."""
    trig = trig if trig is not None else load_fry_triggers()
    if trig.empty:
        return symbols
    agg = (
        trig.groupby("yahoo_symbol")
        .agg(n_triggers=("episode_id", "count"), min_r5=("return_5d", "min"))
        .reset_index()
    )
    sym_set = set(symbols)
    agg = agg[agg["yahoo_symbol"].isin(sym_set)].copy()
    agg = agg.sort_values(["n_triggers", "min_r5"], ascending=[False, True])
    ordered = agg["yahoo_symbol"].tolist()
    tail = [s for s in symbols if s not in set(ordered)]
    return ordered + sorted(tail)


def collect_structural_panel(
    symbols: list[str] | None = None,
    *,
    max_live_calls: int = 500,
    use_cache: bool = True,
    lanes: tuple[str, ...] = ("profile", "insider", "info"),
) -> tuple[pd.DataFrame, dict[str, Any]]:
    symbols = symbols or load_fry_symbols()
    symbols = prioritize_fry_symbols(symbols)
    budget = [max_live_calls]
    rows: list[dict[str, Any]] = []
    stats = {"symbols": len(symbols), "live_calls": 0, "errors": []}

    for sym in symbols:
        profile = insider = info = None
        if "profile" in lanes:
            profile = fetch_emiten_lane(sym, "profile", use_cache=use_cache, live_budget=budget)
            if not profile.get("from_disk_cache") and profile.get("ok"):
                stats["live_calls"] += 1
        if "insider" in lanes:
            insider = fetch_emiten_lane(sym, "insider", use_cache=use_cache, live_budget=budget)
            if not insider.get("from_disk_cache") and insider.get("ok"):
                stats["live_calls"] += 1
        if "info" in lanes:
            info = fetch_emiten_lane(sym, "info", use_cache=use_cache, live_budget=budget)
            if not info.get("from_disk_cache") and info.get("ok"):
                stats["live_calls"] += 1

        row = parse_structural_row(sym, profile, insider, info)
        if not any(row.get(f"{k}_ok") for k in ("profile", "insider", "info")):
            stats["errors"].append({"symbol": sym, "reason": "all_lanes_failed"})
        else:
            stats.setdefault("ok_symbols", []).append(sym)
        rows.append(row)

    df = pd.DataFrame(rows)
    out = _out_path("structural_panel")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and len(symbols) < len(load_fry_symbols()):
        prior = pd.read_parquet(out)
        prior = prior[~prior["yahoo_symbol"].isin(df["yahoo_symbol"])]
        df = pd.concat([prior, df], ignore_index=True)
        df = df.sort_values("yahoo_symbol").drop_duplicates("yahoo_symbol", keep="last")
    df.to_parquet(out, index=False)
    stats["output"] = str(out)
    stats["n_rows"] = len(df)
    stats["n_profile_ok"] = int(df["profile_ok"].sum()) if "profile_ok" in df.columns else 0
    stats["n_with_free_float"] = int(df["free_float_pct"].notna().sum()) if "free_float_pct" in df.columns else 0
    stats["live_budget_remaining"] = budget[0]
    return df, stats


def collect_trending_snapshot() -> dict[str, Any]:
    from idn_rapidapi_idx import get

    cfg = load_config()
    path = cfg.get("rapidapi", {}).get("trending_path", "/api/main/trending")
    r = get(path, use_cache=False, cache_ttl_sec=300)
    if not r.get("ok"):
        return {"ok": False, "reason": r.get("reason")}

    items_raw = ((r.get("data") or {}).get("data") or {}).get("data") or []
    rows: list[dict[str, Any]] = []
    day = datetime.now(UTC).date().isoformat()
    for i, it in enumerate(items_raw, start=1):
        sym = str(it.get("symbol") or it.get("symbol_2") or "").upper()
        if not sym:
            continue
        rows.append(
            {
                "snapshot_date": day,
                "yahoo_symbol": f"{sym}.JK",
                "trending_rank": i,
                "percent_change": it.get("percent"),
                "last": it.get("last"),
                "name": it.get("name"),
                "volume": it.get("volume"),
            }
        )

    hist_path = _out_path("trending_history")
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    if hist_path.exists() and not df.empty:
        old = pd.read_parquet(hist_path)
        old = old[old["snapshot_date"] != day]
        df = pd.concat([old, df], ignore_index=True)
    if not df.empty:
        df.to_parquet(hist_path, index=False)

    fry_syms = set(load_fry_symbols())
    fry_in_trending = [row for row in rows if row["yahoo_symbol"] in fry_syms]
    return {
        "ok": True,
        "snapshot_date": day,
        "n_trending": len(rows),
        "n_fry_in_trending": len(fry_in_trending),
        "fry_trending": fry_in_trending[:20],
        "history_path": str(hist_path),
    }


def build_attention_panel(structural: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    structural = structural if structural is not None else load_structural_panel()
    trending_snap = collect_trending_snapshot()
    day = trending_snap.get("snapshot_date") or datetime.now(UTC).date().isoformat()

    rank_map: dict[str, int | None] = {}
    pct_map: dict[str, Any] = {}
    if trending_snap.get("ok"):
        for row in trending_snap.get("fry_trending", []):
            sym = row["yahoo_symbol"]
            rank_map[sym] = row.get("trending_rank")
            pct_map[sym] = row.get("percent_change")
        hist_path = _out_path("trending_history")
        if hist_path.exists():
            hist = pd.read_parquet(hist_path)
            hist = hist[hist["snapshot_date"] == day]
            for _, r in hist.iterrows():
                sym = r["yahoo_symbol"]
                if sym not in rank_map:
                    rank_map[sym] = int(r["trending_rank"]) if pd.notna(r["trending_rank"]) else None
                    pct_map[sym] = r.get("percent_change")

    symbols = load_fry_symbols()
    if structural is not None and not structural.empty:
        sym_set = set(structural["yahoo_symbol"])
        symbols = sorted(sym_set | set(symbols))

    rows: list[dict[str, Any]] = []
    struct_by_sym = {}
    if structural is not None and not structural.empty:
        struct_by_sym = structural.set_index("yahoo_symbol").to_dict("index")

    for sym in symbols:
        srow = struct_by_sym.get(sym, {})
        followers = srow.get("app_followers")
        rank = rank_map.get(sym)
        att = 0.0
        if rank is not None:
            att += max(0.0, 1.0 - (rank / 50.0))
        if followers is not None and pd.notna(followers):
            try:
                att += min(0.5, float(followers) / 5_000_000.0)
            except (TypeError, ValueError):
                pass
        rows.append(
            {
                "yahoo_symbol": sym,
                "snapshot_date": day,
                "trending_rank": rank,
                "trending_pct": pct_map.get(sym),
                "app_followers": followers,
                "attention_score": round(att, 4),
                "in_trending_top50": rank is not None and rank <= 50,
            }
        )

    df = pd.DataFrame(rows)
    out = _out_path("attention_panel")
    df.to_parquet(out, index=False)
    return df, {"output": str(out), "n_rows": len(df), "trending": trending_snap}


def collect_reddit_fry_mentions(symbols: list[str] | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Scan Reddit IDX subs for fry ticker mentions (no per-symbol API)."""
    import os

    import requests
    from dotenv import load_dotenv

    for p in [REPO / ".env.local", REPO / ".env"]:
        if p.exists():
            load_dotenv(p, override=False)

    cfg = load_config()
    rd = cfg.get("reddit", {})
    if not rd.get("enabled", True):
        return pd.DataFrame(), {"ok": False, "reason": "disabled"}

    symbols = symbols or load_fry_symbols()
    sym_set = set(symbols)
    base_map = {_base_symbol(s): s for s in symbols}

    ua = os.getenv("REDDIT_USER_AGENT", "SharpeRenaissanceFry/1.0")
    headers = {"User-Agent": ua}
    posts: list[dict[str, Any]] = []
    errors: list[str] = []

    for sub in rd.get("subreddits", ["finansial", "Indostock"]):
        url = f"https://www.reddit.com/r/{sub}/new.json"
        try:
            r = requests.get(url, params={"limit": 100}, headers=headers, timeout=30)
            if r.status_code != 200:
                errors.append(f"{sub}:http_{r.status_code}")
                continue
            for ch in r.json().get("data", {}).get("children", []):
                d = ch.get("data", {})
                text = f"{d.get('title','')}\n{d.get('selftext','')}".upper()
                found = []
                for m in TICKER_TOKEN_RE.finditer(text):
                    base = m.group(1)
                    if base in base_map:
                        found.append(base_map[base])
                if found:
                    posts.append(
                        {
                            "post_id": d.get("id"),
                            "subreddit": sub,
                            "created_utc": d.get("created_utc"),
                            "title": (d.get("title") or "")[:300],
                            "tickers": sorted(set(found)),
                        }
                    )
        except Exception as exc:
            errors.append(f"{sub}:{exc}")
        time.sleep(1.5)

    mention_counts: dict[str, int] = {s: 0 for s in symbols}
    for p in posts:
        for t in p.get("tickers", []):
            mention_counts[t] = mention_counts.get(t, 0) + 1

    rows = [
        {
            "yahoo_symbol": sym,
            "snapshot_date": datetime.now(UTC).date().isoformat(),
            "reddit_mentions_7d_proxy": mention_counts.get(sym, 0),
            "reddit_post_hits": mention_counts.get(sym, 0),
        }
        for sym in symbols
    ]
    df = pd.DataFrame(rows)
    out = _out_path("reddit_mentions")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return df, {"ok": True, "n_posts_with_fry": len(posts), "errors": errors, "output": str(out)}


def refresh_broker_queue(trig: pd.DataFrame | None = None) -> list[dict[str, Any]]:
    from idn_fry_strategic_indicator_lib import fry_trigger_broker_queue

    trig = trig if trig is not None else load_fry_triggers()
    queue = fry_trigger_broker_queue(trig)
    out = _out_path("broker_queue")
    out.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    return queue


def merge_structural_into_triggers(
    trig: pd.DataFrame | None = None,
    structural: pd.DataFrame | None = None,
) -> pd.DataFrame:
    trig = trig if trig is not None else load_fry_triggers()
    structural = structural if structural is not None else load_structural_panel()
    if trig.empty:
        return trig
    if structural is None or structural.empty:
        return trig

    keep_cols = [
        "yahoo_symbol",
        "free_float_pct",
        "listing_board",
        "is_watchlist_board",
        "is_acceleration_board",
        "is_trading_limit",
        "is_daytrade",
        "is_idx_liquid",
        "top_holder_pct",
        "controller_ownership_pct",
        "controller_is_foreign",
        "latest_insider_buy",
        "latest_holder_pct_change",
        "low_free_float",
        "ultra_low_free_float",
        "structurally_fryable",
        "app_followers",
    ]
    cols = [c for c in keep_cols if c in structural.columns]
    merged = trig.merge(structural[cols].drop_duplicates("yahoo_symbol"), on="yahoo_symbol", how="left")
    out = _out_path("triggers_enriched")
    merged.to_parquet(out, index=False)
    return merged


def load_structural_panel() -> pd.DataFrame:
    path = _out_path("structural_panel")
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def symbols_missing_structural(panel: pd.DataFrame | None = None) -> list[str]:
    """Fry symbols without profile or free-float from structural panel."""
    panel = panel if panel is not None else load_structural_panel()
    all_syms = load_fry_symbols()
    if panel.empty:
        return all_syms
    bad = panel[~panel["profile_ok"].fillna(False) | panel["free_float_pct"].isna()]
    missing_set = set(bad["yahoo_symbol"].tolist())
    have = set(panel.loc[panel["profile_ok"].fillna(False), "yahoo_symbol"])
    for sym in all_syms:
        if sym not in have:
            missing_set.add(sym)
    return sorted(missing_set)


def load_attention_panel() -> pd.DataFrame:
    path = _out_path("attention_panel")
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def load_technical_panel() -> pd.DataFrame:
    path = _out_path("technical_panel")
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def load_technical_trigger_panel() -> pd.DataFrame:
    path = _out_path("technical_trigger_panel")
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def run_broker_backfill(*, max_calls: int = 200, delay: float = 3.5) -> dict[str, Any]:
    """Invoke fry broker backfill subprocess-style via import."""
    import subprocess
    import sys

    cmd = [
        sys.executable,
        str(REPO / "scripts/run_idn_broker_backfill.py"),
        "--source",
        "fry",
        "--max-calls",
        str(max_calls),
        "--delay",
        str(delay),
    ]
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    manifest_path = REPO / "data_lake/markets/idx_broker_summary/backfill_manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "exit_code": proc.returncode,
        "stdout_tail": proc.stdout[-2000:] if proc.stdout else "",
        "stderr_tail": proc.stderr[-1000:] if proc.stderr else "",
        "manifest": manifest,
    }


def build_collection_manifest(results: dict[str, Any]) -> dict[str, Any]:
    trig = load_fry_triggers()
    structural = load_structural_panel()
    attention = load_attention_panel()

    manifest = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "n_fry_symbols": len(load_fry_symbols()),
        "n_triggers": int(len(trig)),
        "lanes": results,
        "coverage": {
            "structural_symbols": int(len(structural)) if not structural.empty else 0,
            "structural_free_float_pct": round(
                100 * structural["free_float_pct"].notna().mean(), 2
            )
            if not structural.empty and "free_float_pct" in structural.columns
            else 0.0,
            "triggers_with_structural": round(
                100 * trig["yahoo_symbol"].isin(structural["yahoo_symbol"]).mean(), 2
            )
            if not trig.empty and not structural.empty
            else 0.0,
            "attention_symbols": int(len(attention)) if not attention.empty else 0,
            "technical_symbols": int(len(load_technical_panel())) if _out_path("technical_panel").exists() else 0,
            "technical_trigger_episodes": int(len(load_technical_trigger_panel()))
            if _out_path("technical_trigger_panel").exists()
            else 0,
        },
        "outputs": {
            "structural_panel": str(_out_path("structural_panel")),
            "attention_panel": str(_out_path("attention_panel")),
            "technical_panel": str(_out_path("technical_panel")),
            "technical_trigger_panel": str(_out_path("technical_trigger_panel")),
            "triggers_enriched": str(_out_path("triggers_enriched")),
            "broker_queue": str(_out_path("broker_queue")),
            "trending_history": str(_out_path("trending_history")),
            "reddit_mentions": str(_out_path("reddit_mentions")),
        },
    }
    out = _out_path("collection_manifest")
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def run_all_lanes(
    *,
    max_live_calls: int = 450,
    broker_max_calls: int = 200,
    broker_delay: float = 3.5,
    skip_broker: bool = False,
    skip_reddit: bool = True,
    cache_only: bool = False,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    symbols = symbols or load_fry_symbols()

    struct_df, struct_stats = collect_structural_panel(
        symbols,
        max_live_calls=0 if cache_only else max_live_calls,
        use_cache=True,
    )
    results["structural"] = struct_stats

    enrich_df, enrich_stats = enrich_structural_from_emiten_cache(symbols)
    results["structural_enrich_cache"] = enrich_stats

    att_df, att_stats = build_attention_panel(enrich_df if not enrich_df.empty else struct_df)
    results["attention"] = att_stats

    if cache_only:
        results["technical"] = {"skipped": True, "reason": "cache_only"}
        results["technical_triggers"] = {"skipped": True, "reason": "cache_only"}
    else:
        tech_budget = min(40, max(10, max_live_calls // 10))
        _, tech_stats = collect_technical_symbol_panel(symbols, max_live_calls=tech_budget, use_cache=True)
        results["technical"] = tech_stats
        _, ttrig_stats = collect_technical_trigger_panel(max_live_calls=min(20, tech_budget), use_cache=True)
        results["technical_triggers"] = ttrig_stats

    if not skip_reddit:
        _, reddit_stats = collect_reddit_fry_mentions(symbols)
        results["reddit"] = reddit_stats
    else:
        results["reddit"] = {"skipped": True}

    queue = refresh_broker_queue()
    results["broker_queue"] = {"pending_sessions": len(queue)}

    if not skip_broker and not cache_only:
        results["broker_backfill"] = run_broker_backfill(max_calls=broker_max_calls, delay=broker_delay)
    else:
        results["broker_backfill"] = {"skipped": True}

    merged = merge_structural_into_triggers(structural=enrich_df if not enrich_df.empty else struct_df)
    results["merge"] = {"n_triggers": len(merged), "output": str(_out_path("triggers_enriched"))}

    manifest = build_collection_manifest(results)
    results["manifest"] = manifest
    return results
