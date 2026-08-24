#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import json
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROCESSED = REPO / "data_lake/news_shock_taxonomy/processed"
COINGECKO = REPO / "data_lake/coingecko_archive/coingecko_full_active_2009.sqlite3"
OPENSEA_MANIFEST = REPO / "data_lake/opensea/manifests/download_manifest.csv"
OUT = REPO / "data_lake/news_shock_taxonomy/reports/gdelt_research_value_audit"
csv.field_size_limit(sys.maxsize)

WINDOW_RE = re.compile(r"^asia_gkg_window_(\d{8})_(\d{8})_")
SHOCK_COLUMNS = [
    "macro_policy_rows",
    "trade_supply_chain_rows",
    "governance_corruption_rows",
    "political_instability_rows",
    "geopolitical_security_rows",
    "financial_stress_rows",
    "health_rows",
    "natural_environment_rows",
]
CRYPTO_TOPICS = {
    "bitcoin": ("bitcoin", "btc"),
    "ethereum": ("ethereum", "ether", "eth"),
    "crypto_general": ("crypto", "cryptocurrency", "digital asset", "virtual asset"),
    "blockchain": ("blockchain", "distributed ledger"),
    "nft_opensea": ("nft", "non-fungible", "opensea"),
    "stablecoin_usdt": ("stablecoin", "tether", "usdt"),
    "defi": ("defi", "decentralized finance"),
    "exchange": ("crypto exchange", "binance", "coinbase", "kraken", "okx", "bybit"),
    "security_hack": ("hack", "exploit", "cyber", "ransomware"),
    "regulation": ("regulation", "regulatory", "securities commission", "sec.gov"),
}


def canonical_windows() -> list[tuple[str, str, Path]]:
    candidates: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for panel in PROCESSED.glob("*/daily_country_shock_panel.csv"):
        match = WINDOW_RE.match(panel.parent.name)
        if match:
            candidates[(match.group(1), match.group(2))].append(panel.parent)
    chosen = []
    for (start, end), dirs in sorted(candidates.items()):
        dirs.sort(key=lambda path: (path / "daily_country_shock_panel.csv").stat().st_mtime, reverse=True)
        chosen.append((start, end, dirs[0]))
    return chosen


def number(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except ValueError:
        return 0.0


def pearson(xs: list[float], ys: list[float]) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return None
    xbar = sum(x for x, _ in pairs) / len(pairs)
    ybar = sum(y for _, y in pairs) / len(pairs)
    numerator = sum((x - xbar) * (y - ybar) for x, y in pairs)
    xvar = sum((x - xbar) ** 2 for x, _ in pairs)
    yvar = sum((y - ybar) ** 2 for _, y in pairs)
    if xvar == 0 or yvar == 0:
        return None
    return numerator / math.sqrt(xvar * yvar)


def load_panels(windows: list[tuple[str, str, Path]]):
    totals = Counter()
    countries: dict[str, Counter] = defaultdict(Counter)
    years: dict[str, Counter] = defaultdict(Counter)
    daily: dict[str, Counter] = defaultdict(Counter)
    dates = set()
    rows_out = []
    for start, end, directory in windows:
        panel_path = directory / "daily_country_shock_panel.csv"
        month = f"{start[:4]}-{start[4:6]}"
        month_counts = Counter()
        with panel_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                date = row["date"]
                country = row["country_iso3"]
                year = date[:4]
                dates.add(date)
                keys = ["rows", "unique_urls", "high_priority_urls", "market_relevant_rows", "broad_context_rows", *SHOCK_COLUMNS]
                for key in keys:
                    value = number(row, key)
                    totals[key] += value
                    countries[country][key] += value
                    years[year][key] += value
                    month_counts[key] += value
                    daily[date][key] += value
        rows_out.append({"month": month, "directory": str(directory.relative_to(REPO)), **{k: int(v) for k, v in month_counts.items()}})
    return totals, countries, years, daily, dates, rows_out


def scan_crypto_topics(windows: list[tuple[str, str, Path]]):
    counts = Counter()
    country_counts: dict[str, Counter] = defaultdict(Counter)
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    sample_rows = 0
    for _, _, directory in windows:
        path = directory / "sample_high_priority.csv"
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            for row in csv.DictReader(handle):
                sample_rows += 1
                text = " ".join(
                    row.get(key, "")
                    for key in ("document_identifier", "themes", "organizations", "source_common_name", "shock_hints")
                ).lower()
                for topic, terms in CRYPTO_TOPICS.items():
                    if any(term in text for term in terms):
                        counts[topic] += 1
                        country_counts[topic][row.get("country_iso3", "")] += 1
                        if len(examples[topic]) < 5:
                            examples[topic].append({
                                "date": row.get("date", ""),
                                "country": row.get("country_iso3", ""),
                                "url": row.get("canonical_url", row.get("document_identifier", "")),
                                "score": row.get("market_relevance_score", ""),
                            })
    return sample_rows, counts, country_counts, examples


def coingecko_series():
    if not COINGECKO.exists():
        return {}, {}
    conn = sqlite3.connect(f"file:{COINGECKO}?mode=ro", uri=True)
    coverage = {}
    series = {}
    for coin in ("bitcoin", "ethereum"):
        rows = conn.execute(
            "SELECT ts_ms, price FROM coin_history WHERE coin_id=? AND price IS NOT NULL ORDER BY ts_ms",
            (coin,),
        ).fetchall()
        by_date: dict[str, list[float]] = defaultdict(list)
        for ts_ms, price in rows:
            date = datetime.fromtimestamp(ts_ms / 1000, timezone.utc).date().isoformat()
            by_date[date].append(float(price))
        daily = {date: values[-1] for date, values in by_date.items()}
        series[coin] = daily
        coverage[coin] = {
            "raw_points": len(rows),
            "daily_points": len(daily),
            "start": min(daily) if daily else None,
            "end": max(daily) if daily else None,
        }
    conn.close()
    return coverage, series


def market_join(daily_news: dict[str, Counter], coin_series: dict[str, dict[str, float]]):
    results = []
    for coin, prices in coin_series.items():
        ordered_dates = sorted(set(daily_news) & set(prices))
        for horizon in (1, 7, 30):
            signals = defaultdict(list)
            targets = defaultdict(list)
            for date in ordered_dates:
                future = (datetime.fromisoformat(date).date() + timedelta(days=horizon)).isoformat()
                if future not in prices or not prices[date] or not prices[future]:
                    continue
                forward_return = prices[future] / prices[date] - 1
                counts = daily_news[date]
                rows = max(counts["rows"], 1)
                market_share = counts["market_relevant_rows"] / rows
                for key in ["market_relevant_rows", *SHOCK_COLUMNS]:
                    value = market_share if key == "market_relevant_rows" else counts[key] / rows
                    signals[key].append(value)
                    targets[key].append(abs(forward_return))
            for key in signals:
                results.append({
                    "coin": coin,
                    "horizon_days": horizon,
                    "signal": "market_relevant_share" if key == "market_relevant_rows" else key.removesuffix("_rows") + "_share",
                    "observations": len(signals[key]),
                    "correlation_with_absolute_forward_return": pearson(signals[key], targets[key]),
                })
    return results


def opensea_summary():
    if not OPENSEA_MANIFEST.exists():
        return {"manifest_rows": 0}
    with OPENSEA_MANIFEST.open(newline="", encoding="utf-8", errors="replace") as handle:
        rows = list(csv.DictReader(handle))
    return {
        "manifest_rows": len(rows),
        "columns": list(rows[0]) if rows else [],
        "collections": dict(Counter(row.get("collection", row.get("slug", "unknown")) for row in rows)),
    }


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    windows = canonical_windows()
    totals, countries, years, daily, dates, monthly_rows = load_panels(windows)
    sample_rows, topic_counts, topic_countries, topic_examples = scan_crypto_topics(windows)
    coin_coverage, coin_series = coingecko_series()
    joins = market_join(daily, coin_series)
    open_sea = opensea_summary()

    country_rows = []
    for country, values in sorted(countries.items()):
        row_count = max(values["rows"], 1)
        country_rows.append({
            "country": country,
            "article_country_rows": int(values["rows"]),
            "unique_url_month_sum": int(values["unique_urls"]),
            "market_relevant_rows": int(values["market_relevant_rows"]),
            "market_relevant_share": values["market_relevant_rows"] / row_count,
            **{key.removesuffix("_rows") + "_share": values[key] / row_count for key in SHOCK_COLUMNS},
        })
    topic_rows = [{
        "topic": topic,
        "matched_high_priority_sample_rows": int(topic_counts[topic]),
        "sample_share": topic_counts[topic] / max(sample_rows, 1),
        "top_countries": ";".join(f"{country}:{count}" for country, count in topic_countries[topic].most_common(5)),
    } for topic in CRYPTO_TOPICS]

    write_csv(OUT / "monthly_coverage.csv", monthly_rows)
    write_csv(OUT / "country_topic_coverage.csv", country_rows)
    write_csv(OUT / "crypto_topic_evidence.csv", topic_rows)
    write_csv(OUT / "coingecko_join_diagnostics.csv", joins)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gdelt": {
            "canonical_months": len(windows),
            "start_date": min(dates) if dates else None,
            "end_date": max(dates) if dates else None,
            "daily_country_rows": sum(1 for _ in daily),
            "calendar_days": len(dates),
            "countries": sorted(countries),
            "article_country_rows": int(totals["rows"]),
            "unique_url_month_sum": int(totals["unique_urls"]),
            "market_relevant_rows": int(totals["market_relevant_rows"]),
            "high_priority_urls": int(totals["high_priority_urls"]),
            "shock_row_counts": {key.removesuffix("_rows"): int(totals[key]) for key in SHOCK_COLUMNS},
        },
        "retained_high_priority_evidence": {
            "rows_scanned": sample_rows,
            "crypto_topic_matches": dict(topic_counts),
            "examples": topic_examples,
        },
        "coingecko": coin_coverage,
        "opensea_local": open_sea,
        "join_diagnostics": joins,
        "assessment": {
            "strongest_use": "Exogenous Asia news-risk, attention, policy, trade, governance, and volatility-regime layer.",
            "crypto_limitation": "Existing taxonomy does not isolate crypto/NFT events; add a dedicated overlay before direct OpenSea/CoinGecko causal claims.",
            "grain": "Join GDELT country-day or global-day features to CoinGecko/OpenSea daily outcomes by UTC date, then add lags and event windows.",
        },
    }
    (OUT / "audit.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    strongest = sorted(
        (row for row in joins if row["correlation_with_absolute_forward_return"] is not None),
        key=lambda row: abs(row["correlation_with_absolute_forward_return"]),
        reverse=True,
    )[:10]
    lines = [
        "# GDELT Research Value Audit",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Coverage",
        "",
        f"- Canonical monthly windows: {len(windows)}",
        f"- Dates: {report['gdelt']['start_date']} through {report['gdelt']['end_date']}",
        f"- Countries: {len(countries)}",
        f"- Article-country rows: {int(totals['rows']):,}",
        f"- Month-summed unique URLs: {int(totals['unique_urls']):,}",
        f"- Market-relevant rows: {int(totals['market_relevant_rows']):,}",
        f"- High-priority URLs: {int(totals['high_priority_urls']):,}",
        "",
        "## Research Assessment",
        "",
        "The dataset is already functional as a daily Asia news-risk and attention panel. Its defensible role is an explanatory/control, event-discovery, and risk-regime layer for market datasets. It should not yet be described as a direct crypto-news dataset.",
        "",
        "The existing categories cover macro policy, trade and supply chains, governance, political instability, geopolitical security, financial stress, health, and environmental shocks. A crypto overlay should add Bitcoin, Ethereum, stablecoins, exchanges, regulation, hacks/exploits, DeFi, and NFT/OpenSea events.",
        "",
        "## Retained Crypto Evidence",
        "",
        f"High-priority sample rows scanned: {sample_rows:,}",
    ]
    lines.extend(f"- {row['topic']}: {row['matched_high_priority_sample_rows']:,}" for row in topic_rows)
    lines.extend(["", "## Strongest CoinGecko Join Diagnostics", ""])
    for row in strongest:
        lines.append(
            f"- {row['coin']} {row['horizon_days']}d `{row['signal']}`: "
            f"r={row['correlation_with_absolute_forward_return']:.3f}, n={row['observations']}"
        )
    lines.extend([
        "",
        "These correlations are diagnostics, not causal or trading claims. They establish that the datasets can be joined and that the resulting signals have measurable variation.",
    ])
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "months": len(windows), "dates": len(dates), "sample_rows": sample_rows}, indent=2))


if __name__ == "__main__":
    main()
