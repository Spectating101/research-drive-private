"""Shared helpers for ticker-level news-market research panels."""

from __future__ import annotations

import csv
import gzip
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

csv.field_size_limit(sys.maxsize)

REPO = Path(__file__).resolve().parents[1]
WINDOW_RE = re.compile(r"^asia_gkg_window_(\d{8})_(\d{8})_")
DEFAULT_ALIAS_SUPPLEMENT = REPO / "config/ticker_entity_aliases_v2.json"
MATCH_TIER_RANK = {"exact_ticker": 3, "alias_high": 2, "alias_fuzzy": 1}

TRADABLE_TYPES = {"equity_or_fund", "company", "etf_or_fund"}

COUNTRY_NEWS_PREFIXES = (
    "news_",
    "mean_tone",
    "market_relevant",
    "broad_context",
    "financial_stress",
    "geopolitical_security",
    "governance_corruption",
    "health_",
    "macro_policy",
    "natural_environment",
    "political_instability",
    "trade_supply_chain",
    "crypto_",
    "asset_",
    "event_",
    "source_news",
    "source_crypto",
)

GLOBAL_PREFIXES = ("global_", "vix_")


def latest_run(root: Path) -> Path:
    candidates = [p for p in root.iterdir() if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"no run directories under {root}")
    return sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]


def write_frame(df: pd.DataFrame, path: Path) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = path.with_suffix(".csv")
    parquet_path = path.with_suffix(".parquet")
    df.to_csv(csv_path, index=False)
    parquet_written = False
    try:
        df.to_parquet(parquet_path, index=False)
        parquet_written = True
    except Exception:
        parquet_path = None
    return {
        "csv": str(csv_path),
        "parquet": str(parquet_path) if parquet_written and parquet_path else "",
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
    }


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def parse_gkg_organizations(raw: str) -> str:
    if not raw:
        return ""
    left = raw.split("|", 1)[0]
    return left.replace(";", " ")


@dataclass(frozen=True)
class EntityAlias:
    entity_id: str
    yahoo_symbol: str
    market_country: str
    alias: str
    alias_norm: str
    confidence: str
    match_tier: str = "alias_fuzzy"


def load_entity_universe(
    entity_root: Path,
    entity_run: str = "latest",
    min_price_rows: int = 200,
    countries: list[str] | None = None,
) -> pd.DataFrame:
    run_dir = latest_run(entity_root) if entity_run == "latest" else entity_root / entity_run
    master = pd.read_csv(run_dir / "asia_entity_master.csv")
    master["market_country"] = master["market_country"].fillna("").astype(str).str.strip()
    master["row_count_daily"] = pd.to_numeric(master["row_count_daily"], errors="coerce")
    mask = master["instrument_type"].isin(TRADABLE_TYPES) & master["market_country"].ne("")
    if min_price_rows > 0:
        mask &= master["row_count_daily"].fillna(0).ge(min_price_rows)
    if countries:
        mask &= master["market_country"].isin(countries)
    out = master.loc[mask, [
        "entity_id",
        "market_country",
        "exchange",
        "local_code",
        "yahoo_symbol",
        "name",
        "name_local",
        "instrument_type",
        "confidence",
        "row_count_daily",
    ]].copy()
    out["yahoo_symbol"] = out["yahoo_symbol"].astype(str).str.upper().str.strip()
    return out.drop_duplicates(subset=["yahoo_symbol"]).reset_index(drop=True)


def _tier_for_alias(alias_norm: str, symbol: str, name_norm: str, source_field: str) -> str:
    symbol_u = symbol.upper().strip()
    if alias_norm == normalize_text(symbol_u) or source_field == "yahoo_symbol":
        return "exact_ticker"
    if source_field in {"name", "name_local"} or alias_norm == name_norm:
        return "alias_high"
    if source_field == "local_code":
        return "alias_high"
    return "alias_fuzzy"


def load_supplemental_aliases(path: Path | None = None) -> list[EntityAlias]:
    config_path = path or DEFAULT_ALIAS_SUPPLEMENT
    if not config_path.exists():
        return []
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    out: list[EntityAlias] = []
    symbol_set = set()
    for entry in payload.get("entries", []):
        symbol = str(entry.get("yahoo_symbol", "")).upper().strip()
        country = str(entry.get("market_country", "")).upper().strip()
        tier = str(entry.get("match_tier", "alias_high"))
        entity_id = f"SUPP:{symbol}"
        for alias in entry.get("aliases", []):
            alias_norm = normalize_text(str(alias))
            if len(alias_norm) < 4:
                continue
            out.append(
                EntityAlias(
                    entity_id=entity_id,
                    yahoo_symbol=symbol,
                    market_country=country,
                    alias=str(alias),
                    alias_norm=alias_norm,
                    confidence="high",
                    match_tier=tier,
                )
            )
        symbol_set.add(symbol)
    return out


def build_entity_alias_index(
    entities: pd.DataFrame,
    supplement_path: Path | None = None,
) -> list[EntityAlias]:
    aliases: list[EntityAlias] = []
    seen: set[tuple[str, str]] = set()
    for row in entities.itertuples(index=False):
        entity_id = str(row.entity_id)
        symbol = str(row.yahoo_symbol)
        country = str(row.market_country)
        confidence = str(row.confidence or "medium")
        name_norm = normalize_text(row.name)
        field_candidates: list[tuple[str, str]] = []
        for field_name, field in (
            ("name", row.name),
            ("name_local", row.name_local),
            ("local_code", row.local_code),
            ("yahoo_symbol", row.yahoo_symbol),
        ):
            text = str(field or "").strip()
            if len(text) >= 4:
                field_candidates.append((field_name, text))
        if len(name_norm) >= 8:
            field_candidates.append(("name", name_norm))
            parts = [p for p in name_norm.split() if len(p) >= 4]
            if len(parts) >= 2:
                field_candidates.append(("name", " ".join(parts[:4])))
        symbol_base = symbol.split(".", 1)[0]
        if len(symbol_base) >= 4 and symbol_base.isalnum():
            field_candidates.append(("local_code", symbol_base))
        for source_field, alias in field_candidates:
            alias_norm = normalize_text(alias)
            if len(alias_norm) < 4:
                continue
            key = (entity_id, alias_norm)
            if key in seen:
                continue
            seen.add(key)
            aliases.append(
                EntityAlias(
                    entity_id=entity_id,
                    yahoo_symbol=symbol,
                    market_country=country,
                    alias=alias,
                    alias_norm=alias_norm,
                    confidence=confidence,
                    match_tier=_tier_for_alias(alias_norm, symbol, name_norm, source_field),
                )
            )
    aliases.extend(load_supplemental_aliases(supplement_path))
    aliases.sort(key=lambda item: (MATCH_TIER_RANK.get(item.match_tier, 0), len(item.alias_norm)), reverse=True)
    return aliases


def match_entities_in_text(
    text: str,
    country_iso3: str,
    alias_index: list[EntityAlias],
    country_only: bool = True,
    allow_supplement_cross_country: bool = True,
) -> list[EntityAlias]:
    haystack = normalize_text(text)
    if not haystack:
        return []
    best: dict[str, EntityAlias] = {}
    for alias in alias_index:
        if country_only:
            if alias.market_country != country_iso3:
                if not (allow_supplement_cross_country and alias.entity_id.startswith("SUPP:")):
                    continue
        if alias.alias_norm not in haystack:
            continue
        current = best.get(alias.yahoo_symbol)
        if current is None or MATCH_TIER_RANK.get(alias.match_tier, 0) > MATCH_TIER_RANK.get(current.match_tier, 0):
            best[alias.yahoo_symbol] = alias
        elif (
            current is not None
            and MATCH_TIER_RANK.get(alias.match_tier, 0) == MATCH_TIER_RANK.get(current.match_tier, 0)
            and len(alias.alias_norm) > len(current.alias_norm)
        ):
            best[alias.yahoo_symbol] = alias
    return list(best.values())


def canonical_article_url(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return raw.split(" ", 1)[0].rstrip("/")


def liquidity_bucket(row_count_daily: float | int | None) -> str:
    rows = float(row_count_daily or 0)
    if rows >= 1000:
        return "large_cap_liquid"
    if rows >= 400:
        return "mid_cap"
    return "small_cap_thin"


def country_news_columns(df: pd.DataFrame) -> list[str]:
    cols = []
    for col in df.columns:
        if col in {"country_iso3", "week_end", "proxy_type", "instrument", "price", "return_1w", "return_4w",
                   "fwd_return_1w", "fwd_return_2w", "fwd_return_4w", "fwd_vol_4w", "market_data_ffilled",
                   "entity_count", "equity_count", "etf_count", "index_count", "high_confidence_count",
                   "median_price_history_rows", "top_yahoo_symbols"}:
            continue
        if col.startswith(COUNTRY_NEWS_PREFIXES) or col.startswith(GLOBAL_PREFIXES):
            cols.append(col)
        elif col in {"news_rows", "news_days", "unique_urls", "high_priority_urls", "market_relevant_rows",
                     "broad_context_rows", "mean_tone_weighted", "mean_market_relevance_score_weighted"}:
            cols.append(col)
    return cols


def load_country_week_news(fused_panel_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(fused_panel_path) if fused_panel_path.suffix == ".parquet" else pd.read_csv(fused_panel_path)
    df["week_end"] = pd.to_datetime(df["week_end"], errors="coerce")
    df["country_iso3"] = df["country_iso3"].astype(str).str.upper().str.strip()
    keep = ["country_iso3", "week_end", *country_news_columns(df)]
    keep = list(dict.fromkeys(c for c in keep if c in df.columns))
    return df[keep].drop_duplicates(subset=["country_iso3", "week_end"]).sort_values(["country_iso3", "week_end"])


def load_ticker_daily_prices(market_run_dir: Path, tickers: set[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    skip_names = {"failed_tickers.csv", "manifest.csv"}
    for path in sorted(market_run_dir.glob("*.csv")):
        if path.name in skip_names:
            continue
        try:
            df = pd.read_csv(path, usecols=lambda c: c in {"instrument", "date", "adj_close", "close", "volume"})
        except Exception:
            continue
        if "instrument" not in df.columns:
            continue
        df["instrument"] = df["instrument"].astype(str).str.upper().str.strip()
        df = df[df["instrument"].isin(tickers)]
        if df.empty:
            continue
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["adj_close"] = pd.to_numeric(df.get("adj_close"), errors="coerce")
        df["close"] = pd.to_numeric(df.get("close"), errors="coerce")
        df["price"] = df["adj_close"].fillna(df["close"])
        frames.append(df.dropna(subset=["date", "instrument", "price"]))
    if not frames:
        return pd.DataFrame(columns=["instrument", "date", "price", "volume"])
    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(["instrument", "date"]).drop_duplicates(subset=["instrument", "date"], keep="last")
    return out


def build_weekly_ticker_returns(prices: pd.DataFrame, ffill_holidays: bool = True) -> pd.DataFrame:
    if prices.empty:
        return prices
    frames = []
    for instrument, group in prices.groupby("instrument"):
        g = group.sort_values("date").set_index("date")
        observed = g["price"].astype(float).resample("W-FRI").last()
        series = observed.ffill() if ffill_holidays else observed
        weekly = series.to_frame("price")
        if weekly.empty:
            continue
        weekly["yahoo_symbol"] = instrument
        weekly["market_data_ffilled"] = observed.isna() & series.notna() if ffill_holidays else False
        weekly["return_1w"] = weekly["price"].pct_change()
        weekly["return_4w"] = weekly["price"].pct_change(4)
        weekly["fwd_return_1w"] = weekly["price"].shift(-1) / weekly["price"] - 1.0
        weekly["fwd_return_2w"] = weekly["price"].shift(-2) / weekly["price"] - 1.0
        weekly["fwd_return_4w"] = weekly["price"].shift(-4) / weekly["price"] - 1.0
        weekly["fwd_vol_4w"] = weekly["return_1w"].shift(-1).rolling(4).std().shift(-3)
        frames.append(weekly.reset_index().rename(columns={"date": "week_end"}))
    return pd.concat(frames, ignore_index=True).sort_values(["yahoo_symbol", "week_end"]).reset_index(drop=True)


def _article_source_for_window(
    processed_root: Path,
    normalized_root: Path,
    window_key: tuple[str, str],
) -> tuple[Path, Path, str] | None:
    start, end = window_key
    prefix = f"asia_gkg_window_{start}_{end}_"
    scored_candidates = sorted(
        processed_root.glob(f"{prefix}*/asia_gkg_scored.csv.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if scored_candidates:
        source = scored_candidates[0]
        return source.parent, source, "scored"
    normalized_candidates = sorted(
        normalized_root.glob(f"{prefix}*/asia_gkg_filtered.csv.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if normalized_candidates:
        source = normalized_candidates[0]
        return source.parent, source, "normalized"
    return None


def canonical_article_source_dirs(processed_root: Path, normalized_root: Path) -> list[tuple[Path, Path, str]]:
    """Return (window_dir, article_source_file, source_kind) for canonical windows."""
    choices: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for panel in processed_root.glob("*/daily_country_shock_panel.csv"):
        match = WINDOW_RE.match(panel.parent.name)
        if match:
            choices[(match.group(1), match.group(2))].append(panel.parent)
    out: list[tuple[Path, Path, str]] = []
    for window_key, paths in sorted(choices.items()):
        paths.sort(key=lambda p: (p / "daily_country_shock_panel.csv").stat().st_mtime, reverse=True)
        window_dir = paths[0]
        resolved = _article_source_for_window(processed_root, normalized_root, window_key)
        if resolved is not None:
            _, source_file, source_kind = resolved
            out.append((window_dir, source_file, source_kind))
    return out


def shock_hint_columns() -> list[str]:
    return [
        "financial_stress",
        "geopolitical_security",
        "governance_corruption",
        "health",
        "macro_policy",
        "natural_environment",
        "political_instability",
        "trade_supply_chain",
    ]


def aggregate_entity_hits_to_daily(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    def _best_tier(series: pd.Series) -> str:
        tiers = [str(t) for t in series]
        if not tiers:
            return "alias_fuzzy"
        return max(tiers, key=lambda t: MATCH_TIER_RANK.get(t, 0))

    grouped = df.groupby(["date", "yahoo_symbol", "market_country"], as_index=False).agg(
        entity_mention_rows=("entity_id", "count"),
        unique_entities=("entity_id", "nunique"),
        unique_urls=("canonical_url", "nunique"),
        mean_market_relevance_score=("market_relevance_score", "mean"),
        mean_tone_avg=("tone_avg", "mean"),
        matched_aliases=("matched_alias", lambda s: "|".join(sorted(set(map(str, s))))),
        best_match_tier=("match_tier", _best_tier),
        high_confidence_mentions=("match_tier", lambda s: int((s != "alias_fuzzy").sum())),
    )
    for hint in shock_hint_columns():
        col = f"{hint}_rows"
        if col in df.columns:
            hint_sum = df.groupby(["date", "yahoo_symbol", "market_country"])[col].sum().reset_index()
            grouped = grouped.merge(hint_sum, on=["date", "yahoo_symbol", "market_country"], how="left")
    return grouped.sort_values(["yahoo_symbol", "date"]).reset_index(drop=True)


def build_weekly_entity_news(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return daily
    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    daily = daily.dropna(subset=["date", "yahoo_symbol"])
    daily["week_end"] = daily["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
    count_cols = [c for c in daily.columns if c.endswith("_rows") or c in {"entity_mention_rows", "unique_entities"}]
    grouped = daily.groupby(["yahoo_symbol", "market_country", "week_end"], as_index=False)
    pieces = grouped[count_cols].sum()
    meta = grouped.agg(
        entity_news_days=("date", "nunique"),
        mean_market_relevance_score=("mean_market_relevance_score", "mean"),
        mean_tone_avg=("mean_tone_avg", "mean"),
    )
    pieces = pieces.merge(meta, on=["yahoo_symbol", "market_country", "week_end"], how="left")
    denom = pieces["entity_mention_rows"].replace(0, pd.NA)
    for col in [c for c in count_cols if c not in {"entity_mention_rows", "unique_entities"}]:
        base = col.removesuffix("_rows")
        pieces[f"{base}_per_1k_entity_rows"] = pieces[col] / denom * 1000.0
    return pieces.sort_values(["yahoo_symbol", "week_end"]).reset_index(drop=True)


def now_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_entity_long_panel(
    weekly_returns: pd.DataFrame,
    entity_weekly: pd.DataFrame,
    entity_count_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Ticker-week grid with zero-filled entity mention columns where no news."""
    if weekly_returns.empty:
        return weekly_returns
    entity_count_cols = entity_count_cols or [
        c for c in entity_weekly.columns
        if c.endswith("_rows") or c in {"entity_mention_rows", "unique_entities", "entity_news_days"}
    ]
    base = weekly_returns[["yahoo_symbol", "week_end"]].drop_duplicates()
    if "country_iso3" in weekly_returns.columns:
        base = weekly_returns[["yahoo_symbol", "country_iso3", "week_end"]].drop_duplicates()
    ent = entity_weekly.copy()
    ent["week_end"] = pd.to_datetime(ent["week_end"], errors="coerce")
    keys = ["yahoo_symbol", "week_end"] + (["country_iso3"] if "country_iso3" in base.columns and "market_country" in ent.columns else [])
    if "market_country" in ent.columns and "country_iso3" in base.columns:
        ent = ent.rename(columns={"market_country": "country_iso3"})
    long = base.merge(ent, on=keys, how="left")
    for col in entity_count_cols:
        if col in long.columns:
            long[col] = pd.to_numeric(long[col], errors="coerce").fillna(0)
    long["has_entity_news"] = long.get("entity_mention_rows", 0).fillna(0).gt(0)
    long["join_mode"] = "entity_long"
    return long.sort_values(["yahoo_symbol", "week_end"]).reset_index(drop=True)


def build_entity_broadcast_residual(
    entity_panel: pd.DataFrame,
    broadcast_panel: pd.DataFrame,
) -> pd.DataFrame:
    """Entity-minus-broadcast idiosyncratic mention and news-intensity residuals."""
    ent = entity_panel.copy()
    ent["week_end"] = pd.to_datetime(ent["week_end"], errors="coerce")
    bc = broadcast_panel.copy()
    bc["week_end"] = pd.to_datetime(bc["week_end"], errors="coerce")
    bcols = [c for c in bc.columns if c.startswith("country_broadcast_")]
    if not bcols:
        rename_map = {
            c: f"country_broadcast_{c}"
            for c in bc.columns
            if c not in {
                "yahoo_symbol", "country_iso3", "week_end", "entity_id", "exchange", "name",
                "instrument_type", "confidence", "row_count_daily", "price", "return_1w",
                "return_4w", "fwd_return_1w", "fwd_return_2w", "fwd_return_4w", "fwd_vol_4w",
                "market_data_ffilled", "join_mode",
            }
        }
        bc = bc.rename(columns=rename_map)
        bcols = list(rename_map.values())
    merged = ent.merge(bc[["yahoo_symbol", "week_end", *bcols]], on=["yahoo_symbol", "week_end"], how="left")
    if "entity_mention_rows" in merged.columns and "country_broadcast_news_rows" in merged.columns:
        merged["entity_excess_mentions_vs_country"] = (
            pd.to_numeric(merged["entity_mention_rows"], errors="coerce")
            - pd.to_numeric(merged["country_broadcast_news_rows"], errors="coerce")
        )
    if "entity_mention_rows" in merged.columns and "country_broadcast_market_relevant_rows" in merged.columns:
        merged["entity_excess_market_relevant_vs_country"] = (
            pd.to_numeric(merged["entity_mention_rows"], errors="coerce")
            - pd.to_numeric(merged["country_broadcast_market_relevant_rows"], errors="coerce")
        )
    merged["join_mode"] = "entity_residual"
    return merged
