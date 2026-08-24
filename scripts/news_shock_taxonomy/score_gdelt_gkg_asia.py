#!/usr/bin/env python3
"""Score filtered Asia GDELT GKG rows for research and enrichment priority.

The bulk GKG collector is intentionally broad. This postprocess layer separates
the raw radar feed into practical buckets: primary-country confidence, source
quality, market relevance, likely noise, and URL enrichment priority.
"""

from __future__ import annotations

import argparse
import gzip
import gc
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pandas as pd


UTC = timezone.utc

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO / "config/news_shock_asia_universe.json"
DEFAULT_INPUT_ROOT = REPO / "data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk"
DEFAULT_OUT_ROOT = REPO / "data_lake/news_shock_taxonomy/processed"

COUNTRY_SUFFIXES = [
    (".com.au", "AUS"),
    (".net.au", "AUS"),
    (".org.au", "AUS"),
    (".co.kr", "KOR"),
    (".or.kr", "KOR"),
    (".go.kr", "KOR"),
    (".com.cn", "CHN"),
    (".gov.cn", "CHN"),
    (".com.hk", "HKG"),
    (".com.sg", "SGP"),
    (".com.my", "MYS"),
    (".com.ph", "PHL"),
    (".com.tw", "TWN"),
    (".co.jp", "JPN"),
    (".co.in", "IND"),
    (".go.id", "IDN"),
    (".id", "IDN"),
    (".tw", "TWN"),
    (".kr", "KOR"),
    (".jp", "JPN"),
    (".cn", "CHN"),
    (".hk", "HKG"),
    (".sg", "SGP"),
    (".my", "MYS"),
    (".th", "THA"),
    (".ph", "PHL"),
    (".vn", "VNM"),
    (".in", "IND"),
    (".au", "AUS"),
]

SIGNAL_TERMS: dict[str, list[str]] = {
    "direct_market_finance": [
        "stock", "stocks", "share", "shares", "equity", "bond", "bonds",
        "yield", "yields", "etf", "index", "market", "markets", "investor",
        "investment", "trading", "exchange", "bourse", "ipo", "earnings",
        "profit", "profits", "loss", "losses", "revenue", "jci", "ihsg",
        "nikkei", "kospi", "taiex", "hang seng", "nifty", "sensex", "asx",
        "sgx",
    ],
    "macro_policy": [
        "inflation", "gdp", "growth", "recession", "central bank",
        "interest rate", "rate cut", "rate hike", "monetary", "fiscal",
        "budget", "deficit", "debt", "tax", "subsidy", "policy",
        "reserves",
    ],
    "fx_rates": [
        "currency", "forex", "fx", "exchange rate", "usd", "dollar",
        "rupiah", "rupee", "yen", "won", "yuan", "renminbi", "ringgit",
        "baht", "peso",
    ],
    "trade_supply": [
        "tariff", "tariffs", "trade", "export", "exports", "import",
        "imports", "shipping", "supply chain", "port", "ports", "chip",
        "chips", "semiconductor", "semiconductors", "oil", "gas", "coal",
        "commodity", "commodities",
    ],
    "governance_institutions": [
        "corruption", "probe", "investigation", "scandal", "election",
        "protest", "unrest", "coup", "minister", "parliament", "court",
        "law", "regulation", "regulator", "sanction", "watchdog",
    ],
    "geopolitical_security": [
        "war", "military", "conflict", "border", "attack", "terrorism",
        "insurgency", "invasion", "strait", "missile", "drone",
    ],
    "health_disaster": [
        "covid", "pandemic", "disease", "virus", "ebola", "hantavirus",
        "flood", "earthquake", "typhoon", "cyclone", "wildfire", "climate",
        "disaster",
    ],
    "local_crime": [
        "murder", "rape", "stabbed", "stabbing", "shooting", "assault",
        "sex crime", "drug", "smuggling", "crash", "accident", "dead",
        "death", "killed", "arrested", "jail", "custody",
    ],
    "entertainment_sports": [
        "sport", "sports", "football", "soccer", "cricket", "nba", "nfl",
        "tennis", "golf", "formula 1", "motogp", "ipl", "fifa",
        "entertainment", "celebrity", "bollywood", "hollywood", "movie",
        "film", "music", "concert", "actor", "actress", "showbiz", "kpop",
        "anime", "manga",
    ],
    "press_release": [
        "prnewswire", "globenewswire", "businesswire", "einpresswire",
        "openpr", "tmt newswire",
    ],
    "low_value": [
        "horoscope", "recipe", "lottery", "weather forecast",
    ],
}

CORE_MARKET_FLAGS = {
    "direct_market_finance",
    "macro_policy",
    "fx_rates",
    "trade_supply",
    "governance_institutions",
    "geopolitical_security",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None, help="Filtered GKG CSV gzip. Defaults to latest run.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--run-id", default="", help="Output run id. Defaults to input parent name.")
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--chunk-size", type=int, default=200_000)
    return parser.parse_args()


def latest_input() -> Path:
    candidates = sorted(DEFAULT_INPUT_ROOT.glob("*/asia_gkg_filtered.csv.gz"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"no asia_gkg_filtered.csv.gz files under {DEFAULT_INPUT_ROOT}")
    return candidates[-1]


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def bare_domain(value: str) -> str:
    value = (value or "").strip().lower()
    if "://" in value:
        host = urlsplit(value).netloc
    else:
        host = value
    host = host.split("@")[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def canonicalize_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    scheme = (parsed.scheme or "https").lower()
    netloc = bare_domain(parsed.netloc)
    path = re.sub(r"/+$", "", parsed.path or "")
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def domain_matches(host: str, candidates: list[str]) -> bool:
    host = bare_domain(host)
    for candidate in candidates:
        candidate = bare_domain(candidate)
        if host == candidate or host.endswith("." + candidate):
            return True
    return False


def domain_country(host: str) -> str:
    host = bare_domain(host)
    for suffix, iso3 in COUNTRY_SUFFIXES:
        if host.endswith(suffix):
            return iso3
    return ""


def source_tier(host: str, config: dict[str, Any]) -> str:
    tiers = config.get("source_domain_tiers", {})
    for tier, domains in tiers.items():
        if domain_matches(host, [str(item) for item in domains]):
            return tier
    return "other"


def term_pattern(terms: list[str]) -> re.Pattern[str]:
    escaped = []
    for term in terms:
        item = re.escape(term.lower()).replace(r"\ ", r"[\s_-]+")
        escaped.append(item)
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(escaped) + r")(?![a-z0-9])")


PATTERNS = {name: term_pattern(terms) for name, terms in SIGNAL_TERMS.items()}


def flags_for_text(text: str) -> list[str]:
    text = (text or "").lower()
    return [name for name, pattern in PATTERNS.items() if pattern.search(text)]


def split_pipe(value: Any) -> list[str]:
    if not isinstance(value, str) or not value:
        return []
    return [item for item in value.split("|") if item]


def market_score(row: pd.Series) -> int:
    flags = set(split_pipe(row.get("content_signal_flags")))
    shocks = set(split_pipe(row.get("shock_hints")))
    score = 0
    if "direct_market_finance" in flags:
        score += 25
    if "macro_policy" in flags:
        score += 20
    if "fx_rates" in flags:
        score += 15
    if "trade_supply" in flags:
        score += 15
    if "governance_institutions" in flags:
        score += 12
    if "geopolitical_security" in flags:
        score += 12
    if "health_disaster" in flags:
        score += 8
    if "financial_stress" in shocks:
        score += 10
    if "trade_supply_chain" in shocks:
        score += 6
    if "governance_corruption" in shocks or "political_instability" in shocks:
        score += 6
    if row.get("source_quality_score", 0.0) >= 0.8:
        score += 5
    if row.get("has_exact_fips_match"):
        score += 5
    if row.get("doc_country_count", 99) > 3:
        score -= 10
    if row.get("doc_country_count", 99) > 8:
        score -= 10
    if row.get("is_pure_local_crime"):
        score -= 25
    if "entertainment_sports" in flags or "low_value" in flags:
        score -= 50
    if "press_release" in flags or row.get("source_tier") == "wire_press_release":
        score -= 10
    return int(max(0, min(100, score)))


def score_bucket(score: int) -> str:
    if score >= 65:
        return "high_market_relevance"
    if score >= 45:
        return "medium_market_relevance"
    if score >= 25:
        return "broad_context"
    return "low_or_noise"


def primary_country(row: pd.Series) -> tuple[int, str]:
    score = 0.0
    if row.get("has_exact_fips_match"):
        score += 4.0
    elif row.get("matched_country_terms"):
        score += 1.0
    count = int(row.get("doc_country_count", 99))
    if count == 1:
        score += 3.0
    elif count <= 3:
        score += 1.5
    elif count > 8:
        score -= 2.0
    if row.get("domain_country_iso3") and row.get("domain_country_iso3") == row.get("country_iso3"):
        score += 2.0
    if row.get("source_tier") in {"official_public", "asia_core_journalism", "market_business"}:
        score += 0.5
    value = int(max(0, min(100, round(score / 9.5 * 100))))
    if value >= 75:
        label = "high"
    elif value >= 50:
        label = "medium"
    else:
        label = "weak"
    return value, label


def collection_decision(row: pd.Series) -> str:
    flags = set(split_pipe(row.get("content_signal_flags")))
    source_tier_value = row.get("source_tier")
    source_quality = float(row.get("source_quality_score", 0.0) or 0.0)
    score = int(row.get("market_relevance_score", 0) or 0)
    if "entertainment_sports" in flags or "low_value" in flags:
        return "exclude_noise"
    if source_tier_value == "entertainment_sports":
        return "exclude_noise"
    if row.get("is_pure_local_crime") and score < 45:
        return "archive_low_priority"
    if row.get("shock_hints") == "" or pd.isna(row.get("shock_hints")):
        return "archive_no_specific_shock"
    if source_tier_value == "low_value_rebroadcast":
        return "keep_context" if score >= 45 else "archive_low_priority"
    if source_tier_value == "wire_press_release" or "press_release" in flags:
        return "keep_context" if score >= 55 else "archive_low_priority"
    if row.get("primary_country_confidence") == "weak" and score < 45:
        return "archive_weak_country"
    if (
        score >= 65
        and row.get("primary_country_confidence") == "high"
        and source_quality >= 0.5
    ):
        return "enrich_high_priority"
    if score >= 45:
        return "keep_medium_priority"
    if score >= 25:
        return "keep_context"
    return "archive_low_priority"


def merge_pipe(values: pd.Series) -> str:
    items: set[str] = set()
    for value in values.dropna():
        items.update(split_pipe(value))
    return "|".join(sorted(items))


def write_csv_gz(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        df.to_csv(fh, index=False)


def shock_counts_by_country_day(df: pd.DataFrame) -> pd.DataFrame:
    """Count sparse shock labels without materializing a full dummy matrix."""
    shock_rows = df.loc[
        df["shock_hints"].fillna("").ne(""),
        ["date", "country_iso3", "shock_hints"],
    ].copy()
    if shock_rows.empty:
        return pd.DataFrame()
    shock_rows["shock_hint"] = shock_rows["shock_hints"].map(split_pipe)
    shock_rows = shock_rows.drop(columns=["shock_hints"]).explode("shock_hint")
    shock_rows = shock_rows[shock_rows["shock_hint"].fillna("").ne("")]
    if shock_rows.empty:
        return pd.DataFrame()
    counts = (
        shock_rows.groupby(["date", "country_iso3", "shock_hint"], as_index=False, observed=True)
        .size()
        .pivot_table(
            index=["date", "country_iso3"],
            columns="shock_hint",
            values="size",
            fill_value=0,
            observed=True,
        )
        .reset_index()
    )
    counts.columns = [
        f"{column}_rows" if column not in {"date", "country_iso3"} else column
        for column in counts.columns
    ]
    return counts


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    input_path = args.input or latest_input()
    run_id = args.run_id or input_path.parent.name
    out_dir = args.out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    scored_path = out_dir / "asia_gkg_scored.csv.gz"
    queue_columns = [
        "document_identifier",
        "date",
        "country_iso3",
        "canonical_url",
        "source_domain",
        "source_tier",
        "source_quality_score",
        "primary_country_score",
        "primary_country_confidence",
        "doc_country_count",
        "market_relevance_score",
        "market_relevance_bucket",
        "collection_decision",
        "shock_hints",
        "content_signal_flags",
        "tone_avg",
    ]
    priority_order = {
        "enrich_high_priority": 0,
        "keep_medium_priority": 1,
        "keep_context": 2,
        "archive_weak_country": 3,
        "archive_no_specific_shock": 4,
        "archive_low_priority": 5,
        "exclude_noise": 6,
    }

    print(json.dumps({"stage": "count_doc_countries", "input": str(input_path)}, separators=(",", ":")), flush=True)
    url_country_pairs: set[tuple[str, str]] = set()
    for chunk in pd.read_csv(
        input_path,
        usecols=["document_identifier", "country_iso3"],
        chunksize=args.chunk_size,
    ):
        urls = chunk["document_identifier"].fillna("").map(canonicalize_url)
        countries = chunk["country_iso3"].fillna("").astype(str)
        url_country_pairs.update(zip(urls, countries))
        del chunk, urls, countries
        gc.collect()

    doc_country_counts = Counter(url for url, country in url_country_pairs if url and country)
    del url_country_pairs
    gc.collect()

    tier_scores = config.get("source_tier_scores", {})
    summary_counters = {
        "country_rows": Counter(),
        "source_tiers": Counter(),
        "primary_country_confidence": Counter(),
        "market_relevance_buckets": Counter(),
        "collection_decisions": Counter(),
        "content_signal_flags": Counter(),
    }
    rows_total = 0
    sample_frames: dict[str, list[pd.DataFrame]] = {
        "sample_high_priority": [],
        "sample_context": [],
        "sample_noise": [],
    }
    url_queue_parts: list[pd.DataFrame] = []
    panel_parts: list[pd.DataFrame] = []
    daily_url_parts: list[pd.DataFrame] = []
    shock_parts: list[pd.DataFrame] = []

    def add_sample(name: str, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        if len(frame) > args.sample_size:
            frame = frame.sample(args.sample_size, random_state=42)
        sample_frames[name].append(frame.copy())

    first_scored_chunk = True
    print(json.dumps({"stage": "score_chunks", "chunk_size": args.chunk_size}, separators=(",", ":")), flush=True)
    with gzip.open(scored_path, "wt", encoding="utf-8", newline="") as scored_fh:
        for chunk_index, df in enumerate(pd.read_csv(input_path, chunksize=args.chunk_size), start=1):
            df["canonical_url"] = df["document_identifier"].fillna("").map(canonicalize_url)
            df["source_domain"] = df["source_common_name"].fillna("").map(bare_domain)
            empty_source = df["source_domain"] == ""
            df.loc[empty_source, "source_domain"] = df.loc[empty_source, "document_identifier"].map(bare_domain)
            df["doc_country_count"] = df["canonical_url"].map(lambda value: int(doc_country_counts.get(value, 0))).astype(int)
            df["has_exact_fips_match"] = df["matched_country_terms"].fillna("").str.contains("fips:", regex=False)
            df["domain_country_iso3"] = df["source_domain"].map(domain_country)
            df["source_tier"] = df["source_domain"].map(lambda host: source_tier(host, config))
            df["source_quality_score"] = df["source_tier"].map(
                lambda tier: float(tier_scores.get(tier, tier_scores.get("other", 0.5)))
            )

            text = (
                df["document_identifier"].fillna("")
                + " "
                + df["source_domain"].fillna("")
                + " "
                + df["persons"].fillna("")
                + " "
                + df["organizations"].fillna("")
            )
            df["content_signal_flags"] = text.map(lambda value: "|".join(flags_for_text(value)))
            core_market = df["content_signal_flags"].map(
                lambda value: bool(CORE_MARKET_FLAGS.intersection(split_pipe(value)))
            )
            has_local_crime = df["content_signal_flags"].map(lambda value: "local_crime" in split_pipe(value))
            df["is_pure_local_crime"] = has_local_crime & ~core_market
            primary_values = df.apply(primary_country, axis=1)
            df["primary_country_score"] = [item[0] for item in primary_values]
            df["primary_country_confidence"] = [item[1] for item in primary_values]
            df["market_relevance_score"] = df.apply(market_score, axis=1)
            df["market_relevance_bucket"] = df["market_relevance_score"].map(score_bucket)
            df["collection_decision"] = df.apply(collection_decision, axis=1)

            df.to_csv(scored_fh, index=False, header=first_scored_chunk)
            first_scored_chunk = False

            rows_total += int(len(df))
            summary_counters["country_rows"].update(df["country_iso3"].value_counts().to_dict())
            summary_counters["source_tiers"].update(df["source_tier"].value_counts().to_dict())
            summary_counters["primary_country_confidence"].update(df["primary_country_confidence"].value_counts().to_dict())
            summary_counters["market_relevance_buckets"].update(df["market_relevance_bucket"].value_counts().to_dict())
            summary_counters["collection_decisions"].update(df["collection_decision"].value_counts().to_dict())
            summary_counters["content_signal_flags"].update(
                flag for value in df["content_signal_flags"] for flag in split_pipe(value)
            )

            add_sample(
                "sample_high_priority",
                df.loc[df["collection_decision"] == "enrich_high_priority"].drop_duplicates("canonical_url"),
            )
            add_sample(
                "sample_context",
                df.loc[df["collection_decision"] == "keep_context"].drop_duplicates("canonical_url"),
            )
            add_sample(
                "sample_noise",
                df.loc[df["collection_decision"].str.startswith("archive")].drop_duplicates("canonical_url"),
            )

            work = df[queue_columns].copy()
            for column in [
                "country_iso3",
                "source_tier",
                "primary_country_confidence",
                "market_relevance_bucket",
                "collection_decision",
            ]:
                work[column] = work[column].astype("category")

            url_queue_parts.append(
                work.sort_values(
                    ["market_relevance_score", "primary_country_score", "source_quality_score"],
                    ascending=False,
                )
                .groupby(["country_iso3", "canonical_url"], as_index=False, observed=True)
                .agg(
                    document_identifier=("document_identifier", "first"),
                    date=("date", "min"),
                    source_domain=("source_domain", "first"),
                    source_tier=("source_tier", "first"),
                    source_quality_score=("source_quality_score", "max"),
                    primary_country_score=("primary_country_score", "max"),
                    primary_country_confidence=("primary_country_confidence", "first"),
                    doc_country_count=("doc_country_count", "max"),
                    market_relevance_score=("market_relevance_score", "max"),
                    market_relevance_bucket=("market_relevance_bucket", "first"),
                    collection_decision=("collection_decision", "first"),
                    shock_hints=("shock_hints", merge_pipe),
                    content_signal_flags=("content_signal_flags", merge_pipe),
                    tone_avg=("tone_avg", "mean"),
                )
            )

            panel_part = (
                work.groupby(["date", "country_iso3"], as_index=False, observed=True)
                .agg(
                    rows=("canonical_url", "size"),
                    high_priority_urls=("collection_decision", lambda s: int((s == "enrich_high_priority").sum())),
                    market_relevant_rows=("market_relevance_score", lambda s: int((s >= 45).sum())),
                    broad_context_rows=("market_relevance_score", lambda s: int((s >= 25).sum())),
                    tone_sum=("tone_avg", "sum"),
                    tone_count=("tone_avg", "count"),
                    market_score_sum=("market_relevance_score", "sum"),
                    market_score_count=("market_relevance_score", "count"),
                )
            )
            panel_parts.append(panel_part)
            daily_url_parts.append(work[["date", "country_iso3", "canonical_url"]].drop_duplicates())
            shock_counts = shock_counts_by_country_day(work)
            if not shock_counts.empty:
                shock_parts.append(shock_counts)

            print(
                json.dumps(
                    {"stage": "chunk_scored", "chunk": chunk_index, "rows_total": rows_total},
                    separators=(",", ":"),
                ),
                flush=True,
            )
            del df, work, text, core_market, has_local_crime, primary_values
            gc.collect()

    url_queue_source = pd.concat(url_queue_parts, ignore_index=True) if url_queue_parts else pd.DataFrame()
    url_queue = (
        url_queue_source.sort_values(
            ["market_relevance_score", "primary_country_score", "source_quality_score"],
            ascending=False,
        )
        .groupby(["country_iso3", "canonical_url"], as_index=False, observed=True)
        .agg(
            document_identifier=("document_identifier", "first"),
            date=("date", "min"),
            source_domain=("source_domain", "first"),
            source_tier=("source_tier", "first"),
            source_quality_score=("source_quality_score", "max"),
            primary_country_score=("primary_country_score", "max"),
            primary_country_confidence=("primary_country_confidence", "first"),
            doc_country_count=("doc_country_count", "max"),
            market_relevance_score=("market_relevance_score", "max"),
            market_relevance_bucket=("market_relevance_bucket", "first"),
            collection_decision=("collection_decision", "first"),
            shock_hints=("shock_hints", merge_pipe),
            content_signal_flags=("content_signal_flags", merge_pipe),
            tone_avg=("tone_avg", "mean"),
        )
    )
    url_queue["enrichment_priority"] = url_queue["collection_decision"].map(lambda value: priority_order.get(value, 9))
    url_queue = url_queue.sort_values(
        ["enrichment_priority", "market_relevance_score", "primary_country_score", "source_quality_score"],
        ascending=[True, False, False, False],
    )
    queue_path = out_dir / "url_enrichment_queue.csv.gz"
    write_csv_gz(url_queue, queue_path)

    panel_source = pd.concat(panel_parts, ignore_index=True)
    panel = (
        panel_source.groupby(["date", "country_iso3"], as_index=False, observed=True)
        .sum(numeric_only=True)
    )
    unique_url_source = pd.concat(daily_url_parts, ignore_index=True).drop_duplicates()
    unique_urls = (
        unique_url_source.groupby(["date", "country_iso3"], as_index=False, observed=True)
        .size()
        .rename(columns={"size": "unique_urls"})
    )
    panel = panel.merge(unique_urls, on=["date", "country_iso3"], how="left")
    if panel.empty or "tone_sum" not in panel.columns:
        panel["mean_tone"] = pd.Series(dtype=float)
        panel["mean_market_relevance_score"] = pd.Series(dtype=float)
    else:
        panel["mean_tone"] = panel["tone_sum"] / panel["tone_count"].where(panel["tone_count"] != 0, 1)
        panel["mean_market_relevance_score"] = (
            panel["market_score_sum"] / panel["market_score_count"].where(panel["market_score_count"] != 0, 1)
        )
        panel = panel.drop(columns=["tone_sum", "tone_count", "market_score_sum", "market_score_count"])
    if shock_parts:
        shock_counts = (
            pd.concat(shock_parts, ignore_index=True)
            .groupby(["date", "country_iso3"], as_index=False, observed=True)
            .sum(numeric_only=True)
        )
        panel = panel.merge(shock_counts, on=["date", "country_iso3"], how="left")
    panel_path = out_dir / "daily_country_shock_panel.csv"
    panel.to_csv(panel_path, index=False)

    sample_paths = {}
    for key, name in {
        "sample_high_priority": "sample_high_priority.csv",
        "sample_context": "sample_context.csv",
        "sample_noise": "sample_archive_noise.csv",
    }.items():
        sample = pd.concat(sample_frames[key], ignore_index=True) if sample_frames[key] else pd.DataFrame()
        if not sample.empty:
            sample = sample.drop_duplicates("canonical_url")
            if len(sample) > args.sample_size:
                sample = sample.sample(args.sample_size, random_state=42)
        path = out_dir / name
        sample.to_csv(path, index=False)
        sample_paths[key] = str(path)

    del panel, url_queue, url_queue_source, panel_source, unique_url_source
    gc.collect()

    summary = {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "input": str(input_path),
        "rows": rows_total,
        "unique_urls": len(doc_country_counts),
        "country_rows": dict(summary_counters["country_rows"]),
        "source_tiers": dict(summary_counters["source_tiers"]),
        "primary_country_confidence": dict(summary_counters["primary_country_confidence"]),
        "market_relevance_buckets": dict(summary_counters["market_relevance_buckets"]),
        "collection_decisions": dict(summary_counters["collection_decisions"]),
        "content_signal_flags": dict(summary_counters["content_signal_flags"]),
        "outputs": {
            "scored_csv": str(scored_path),
            "url_enrichment_queue": str(queue_path),
            "daily_country_shock_panel": str(panel_path),
            **sample_paths,
        },
    }
    summary_path = out_dir / "scoring_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
