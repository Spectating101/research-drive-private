#!/usr/bin/env python3
"""
Build Asia market universes from online holding/index sources.

This is intentionally separate from the curated/manual Asia config. It fetches
current ETF holding tables, maps local exchange symbols into Yahoo Finance
tickers, optionally validates them with yfinance, and writes:

  data_lake/markets/sourced_universes/<run_id>/
    asia_etf_holdings_raw.csv
    asia_etf_holdings_mapped.csv
    manifest.csv
    generated_yfinance_universes.json

The output config can then be passed to scripts/fetch_accessible_market_universes.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests


ETF_SOURCES: list[dict[str, str]] = [
    {
        "id": "ewt_holdings_taiwan",
        "etf": "EWT",
        "country": "Taiwan",
        "source_url": "https://companiesmarketcap.com/ishares-msci-taiwan-etf/holdings/",
        "source_type": "ETF holdings proxy",
    },
    {
        "id": "ewy_holdings_korea",
        "etf": "EWY",
        "country": "Korea",
        "source_url": "https://companiesmarketcap.com/ishares-msci-south-korea-etf/holdings/",
        "source_type": "ETF holdings proxy",
    },
    {
        "id": "ewj_holdings_japan",
        "etf": "EWJ",
        "country": "Japan",
        "source_url": "https://companiesmarketcap.com/ishares-msci-japan-etf/holdings/",
        "source_type": "ETF holdings proxy",
    },
    {
        "id": "eido_holdings_indonesia",
        "etf": "EIDO",
        "country": "Indonesia",
        "source_url": "https://companiesmarketcap.com/ishares-msci-indonesia-etf/holdings/",
        "source_type": "ETF holdings proxy",
    },
    {
        "id": "ewm_holdings_malaysia",
        "etf": "EWM",
        "country": "Malaysia",
        "source_url": "https://companiesmarketcap.com/ishares-msci-malaysia-etf/holdings/",
        "source_type": "ETF holdings proxy",
    },
    {
        "id": "thd_holdings_thailand",
        "etf": "THD",
        "country": "Thailand",
        "source_url": "https://companiesmarketcap.com/ishares-msci-thailand-etf/holdings/",
        "source_type": "ETF holdings proxy",
    },
    {
        "id": "ews_holdings_singapore",
        "etf": "EWS",
        "country": "Singapore",
        "source_url": "https://companiesmarketcap.com/ishares-msci-singapore-etf/holdings/",
        "source_type": "ETF holdings proxy",
    },
    {
        "id": "ewh_holdings_hong_kong",
        "etf": "EWH",
        "country": "Hong Kong",
        "source_url": "https://companiesmarketcap.com/ishares-msci-hong-kong-etf/holdings/",
        "source_type": "ETF holdings proxy",
    },
    {
        "id": "vnm_holdings_vietnam",
        "etf": "VNM",
        "country": "Vietnam",
        "source_url": "https://stockanalysis.com/etf/vnm/holdings/",
        "source_type": "ETF holdings proxy",
    },
    {
        "id": "inda_holdings_india",
        "etf": "INDA",
        "country": "India",
        "source_url": "https://companiesmarketcap.com/ishares-msci-india-etf/holdings/",
        "source_type": "ETF holdings proxy",
    },
]


SKIP_SYMBOLS = {"", "-", "CASH", "XTSLA", "USD", "HKD", "JPY", "KRW", "TWD", "IDR", "SGD", "MYR", "THB", "VND"}


def fetch_holdings_table(url: str, timeout: int = 30) -> pd.DataFrame:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    }
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    tables = pd.read_html(StringIO(r.text))
    for table in tables:
        cols = {str(c).strip().lower(): c for c in table.columns}
        if "symbol" in cols and "name" in cols:
            return table.rename(columns={cols["symbol"]: "raw_symbol", cols["name"]: "name"})
        if "ticker" in cols and "name" in cols:
            rename = {cols["ticker"]: "raw_symbol", cols["name"]: "name"}
            if "weight %" in cols:
                rename[cols["weight %"]] = "% Weight"
            return table.rename(columns=rename)
    raise RuntimeError(f"No holdings table with Symbol/Name columns: {url}")


def normalize_weight(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_raw_symbol(raw: str) -> tuple[str, str]:
    raw = str(raw).strip()
    if ":" in raw:
        exchange, code = raw.split(":", 1)
        return exchange.strip().upper(), code.strip().upper()
    return "", raw.strip().upper()


def map_simple(raw_symbol: str) -> str | None:
    exchange, code = parse_raw_symbol(raw_symbol)
    code = code.strip()
    if not code or code in SKIP_SYMBOLS:
        return None
    if "." in code and not exchange:
        return code
    if exchange == "IDX":
        return f"{code}.JK"
    if exchange == "KRX":
        return f"{code.zfill(6)}.KS"
    if exchange in {"TPE", "TWSE"}:
        return f"{code}.TW"
    if exchange in {"TWO", "TPEX"}:
        return f"{code}.TWO"
    if exchange == "TYO":
        return f"{code}.T"
    if exchange == "HKG":
        if code.isdigit():
            code = code.zfill(4)
        return f"{code}.HK"
    if exchange == "SGX":
        return f"{code}.SI"
    if exchange in {"HOSE", "HNX", "UPCOM"}:
        return f"{code}.VN"
    if exchange == "NSE":
        return f"{code}.NS"
    if exchange == "BSE":
        return f"{code}.BO"
    if code.endswith(".BK"):
        return code
    return None


def yahoo_search_symbol(name: str, suffix: str, exchange_code: str, pause: float = 0.2) -> str | None:
    q = re.sub(r"\s+", " ", str(name)).strip()
    if not q:
        return None
    try:
        r = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": q, "quotesCount": 8, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        time.sleep(max(0.0, pause))
        r.raise_for_status()
        quotes = r.json().get("quotes", [])
    except Exception:
        return None
    for quote in quotes:
        symbol = str(quote.get("symbol", "")).upper()
        exch = str(quote.get("exchange", "")).upper()
        if symbol.endswith(suffix.upper()) and (not exchange_code or exchange_code.upper() in exch):
            return symbol
    for quote in quotes:
        symbol = str(quote.get("symbol", "")).upper()
        if symbol.endswith(suffix.upper()):
            return symbol
    return None


def map_country_plain_symbol(code: str, country: str) -> str | None:
    code = str(code).strip().upper()
    if not code or code in SKIP_SYMBOLS:
        return None
    if country == "Taiwan":
        return f"{code}.TW"
    if country == "Korea":
        return f"{code.zfill(6)}.KS"
    if country == "Japan":
        return f"{code}.T"
    if country == "Indonesia":
        return f"{code}.JK"
    if country == "Thailand":
        return f"{code.replace('.', '-')}.BK"
    if country == "Singapore":
        return f"{code}.SI"
    if country == "Hong Kong":
        return f"{code.zfill(4) if code.isdigit() else code}.HK"
    if country == "India":
        return f"{code}.NS"
    if country == "Vietnam":
        return f"{code}.VN"
    return None


def map_symbol(
    raw_symbol: str,
    name: str,
    country: str,
    search_cache: dict[tuple[str, str], str | None],
) -> tuple[str | None, str]:
    exchange, code = parse_raw_symbol(raw_symbol)
    if not exchange:
        if country == "Malaysia":
            key = (str(name), ".KL")
            if key not in search_cache:
                search_cache[key] = yahoo_search_symbol(str(name), ".KL", "KLS")
            if search_cache[key]:
                return search_cache[key], "yahoo_search"
        mapped = map_country_plain_symbol(code, country)
        if mapped:
            return mapped, "country_rule"
    simple = map_simple(raw_symbol)
    if simple:
        return simple, "rule"
    if exchange == "KLSE":
        key = (str(name), ".KL")
        if key not in search_cache:
            search_cache[key] = yahoo_search_symbol(str(name), ".KL", "KLS")
        return search_cache[key], "yahoo_search"
    return None, "unmapped"


def validate_tickers(tickers: list[str], period: str = "5d", batch_size: int = 50) -> set[str]:
    import yfinance as yf

    valid: set[str] = set()
    for i in range(0, len(tickers), max(1, batch_size)):
        chunk = tickers[i : i + max(1, batch_size)]
        try:
            df = yf.download(chunk, period=period, interval="1d", auto_adjust=False, progress=False, threads=True)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            level0 = {str(x) for x in df.columns.get_level_values(0)}
            ticker_first = any(t in level0 for t in chunk)
            for ticker in chunk:
                try:
                    sub = df.xs(ticker, axis=1, level=0 if ticker_first else 1, drop_level=True)
                except Exception:
                    continue
                if "Close" in sub.columns and pd.to_numeric(sub["Close"], errors="coerce").notna().any():
                    valid.add(ticker)
        elif len(chunk) == 1 and "Close" in df.columns and pd.to_numeric(df["Close"], errors="coerce").notna().any():
            valid.add(chunk[0])
    return valid


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch sourced Asia ETF holding universes.")
    ap.add_argument("--out-root", type=Path, default=Path("data_lake/markets/sourced_universes"))
    ap.add_argument("--run-id", default="")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--search-pause", type=float, default=0.2)
    args = ap.parse_args()

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_rows: list[dict[str, Any]] = []
    mapped_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    search_cache: dict[tuple[str, str], str | None] = {}

    for src in ETF_SOURCES:
        table = fetch_holdings_table(src["source_url"])
        rows_before = len(table)
        mapped_count = 0
        for _, row in table.iterrows():
            raw_symbol = str(row.get("raw_symbol", "")).strip()
            name = str(row.get("name", "")).strip()
            weight = normalize_weight(row.get("% Weight", row.get("Weight", None)))
            exchange, code = parse_raw_symbol(raw_symbol)
            raw_rows.append(
                {
                    **src,
                    "raw_symbol": raw_symbol,
                    "exchange": exchange,
                    "local_code": code,
                    "name": name,
                    "weight_pct": weight,
                }
            )
            yahoo_symbol, mapping_method = map_symbol(raw_symbol, name, src["country"], search_cache)
            if yahoo_symbol:
                mapped_count += 1
            mapped_rows.append(
                {
                    **src,
                    "raw_symbol": raw_symbol,
                    "exchange": exchange,
                    "local_code": code,
                    "name": name,
                    "weight_pct": weight,
                    "yahoo_symbol": yahoo_symbol or "",
                    "mapping_method": mapping_method,
                }
            )
        manifest_rows.append(
            {
                **src,
                "source_rows": rows_before,
                "mapped_rows": mapped_count,
                "source_url": src["source_url"],
            }
        )

    mapped_df = pd.DataFrame(mapped_rows)
    if args.validate:
        tickers = sorted(t for t in mapped_df["yahoo_symbol"].dropna().astype(str).unique() if t)
        valid = validate_tickers(tickers)
        mapped_df["yfinance_valid_5d"] = mapped_df["yahoo_symbol"].isin(valid)
    else:
        mapped_df["yfinance_valid_5d"] = ""

    raw_path = out_dir / "asia_etf_holdings_raw.csv"
    mapped_path = out_dir / "asia_etf_holdings_mapped.csv"
    manifest_path = out_dir / "manifest.csv"
    pd.DataFrame(raw_rows).to_csv(raw_path, index=False)
    mapped_df.to_csv(mapped_path, index=False)
    pd.DataFrame(manifest_rows).to_csv(manifest_path, index=False)

    universes: list[dict[str, Any]] = []
    for uid, group in mapped_df.groupby("id", sort=False):
        tickers = [t for t in group["yahoo_symbol"].dropna().astype(str).tolist() if t]
        if args.validate:
            tickers = [
                t
                for t in tickers
                if bool(group.loc[group["yahoo_symbol"] == t, "yfinance_valid_5d"].any())
            ]
        tickers = sorted(dict.fromkeys(tickers))
        src_row = group.iloc[0].to_dict()
        universes.append(
            {
                "id": str(uid),
                "description": f"{src_row['etf']} current holdings mapped to Yahoo tickers ({src_row['source_type']})",
                "source_url": str(src_row["source_url"]),
                "source_type": str(src_row["source_type"]),
                "tickers": tickers,
            }
        )

    generated = {
        "name": "Generated Asia sourced yfinance universes",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "notes": [
            "Generated by scripts/fetch_asia_sourced_universes.py.",
            "These are current ETF holdings proxies, not official full exchange universes.",
            "Use alongside exchange/index official sources when available.",
        ],
        "universes": universes,
    }
    generated_path = out_dir / "generated_yfinance_universes.json"
    generated_path.write_text(json.dumps(generated, indent=2))

    ticker_path = out_dir / "unique_yahoo_tickers.txt"
    all_tickers = sorted({t for u in universes for t in u.get("tickers", [])})
    ticker_path.write_text("\n".join(all_tickers) + "\n")

    print(f"wrote {raw_path}")
    print(f"wrote {mapped_path}")
    print(f"wrote {manifest_path}")
    print(f"wrote {generated_path}")
    print(f"unique yahoo tickers: {len(all_tickers)}")
    with (out_dir / "summary.txt").open("w") as f:
        writer = csv.writer(f)
        writer.writerow(["unique_yahoo_tickers", len(all_tickers)])
        writer.writerow(["mapped_rows", int((mapped_df["yahoo_symbol"].astype(str) != "").sum())])
        writer.writerow(["raw_rows", len(mapped_df)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
