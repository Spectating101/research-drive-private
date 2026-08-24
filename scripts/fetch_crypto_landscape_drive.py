#!/usr/bin/env python3
"""Fetch a Drive-first crypto landscape snapshot.

The collector stages a single run under /tmp, uploads it to Google Drive with
rclone, and removes the local staging directory after a successful upload.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_DRIVE_ROOT = "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/markets/crypto-landscape"
DEFAULT_STAGE_ROOT = Path("/tmp/sharpe_crypto_landscape")
USER_AGENT = "Sharpe-Renaissance crypto-landscape-drive/1.0 research-contact=local@example.invalid"

DEFILLAMA_ENDPOINTS = [
    ("defillama", "chains", "https://api.llama.fi/v2/chains"),
    ("defillama", "protocols", "https://api.llama.fi/protocols"),
    ("defillama", "historical_chain_tvl_all", "https://api.llama.fi/v2/historicalChainTvl"),
    ("defillama", "stablecoins", "https://stablecoins.llama.fi/stablecoins?includePrices=true"),
    ("defillama", "stablecoinchains", "https://stablecoins.llama.fi/stablecoinchains"),
    ("defillama", "stablecoincharts_all", "https://stablecoins.llama.fi/stablecoincharts/all"),
    ("defillama", "yields_pools", "https://yields.llama.fi/pools"),
    (
        "defillama",
        "dexs_overview",
        "https://api.llama.fi/overview/dexs?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=false",
    ),
    (
        "defillama",
        "fees_overview",
        "https://api.llama.fi/overview/fees?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=false",
    ),
    (
        "defillama",
        "open_interest_overview",
        "https://api.llama.fi/overview/open-interest?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=false",
    ),
    ("defillama", "hacks", "https://api.llama.fi/hacks"),
]

COINGECKO_ENDPOINTS = [
    ("coingecko", "global", "https://api.coingecko.com/api/v3/global"),
    ("coingecko", "global_defi", "https://api.coingecko.com/api/v3/global/decentralized_finance_defi"),
    ("coingecko", "categories", "https://api.coingecko.com/api/v3/coins/categories"),
    ("coingecko", "categories_list", "https://api.coingecko.com/api/v3/coins/categories/list"),
    ("coingecko", "trending", "https://api.coingecko.com/api/v3/search/trending"),
    (
        "coingecko",
        "markets_page_1",
        "https://api.coingecko.com/api/v3/coins/markets"
        "?vs_currency=usd&order=market_cap_desc&per_page=250&page=1"
        "&sparkline=false&price_change_percentage=1h,24h,7d,30d",
    ),
    (
        "coingecko",
        "markets_page_2",
        "https://api.coingecko.com/api/v3/coins/markets"
        "?vs_currency=usd&order=market_cap_desc&per_page=250&page=2"
        "&sparkline=false&price_change_percentage=1h,24h,7d,30d",
    ),
    (
        "coingecko",
        "exchanges",
        "https://api.coingecko.com/api/v3/exchanges?per_page=250&page=1",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drive-root", default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--stage-root", type=Path, default=DEFAULT_STAGE_ROOT)
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--sleep", type=float, default=1.5, help="Seconds between API calls.")
    parser.add_argument("--no-defillama", action="store_true")
    parser.add_argument("--no-coingecko", action="store_true")
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--keep-local", action="store_true")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def fetch_json(url: str, timeout: int, retries: int) -> tuple[Any, bytes]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    last_error: str | None = None
    for attempt in range(max(1, retries)):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return json.loads(raw), raw
        except urllib.error.HTTPError as exc:
            body = exc.read(500).decode("utf-8", errors="replace")
            last_error = f"HTTP {exc.code}: {body}"
            if exc.code == 429 and attempt + 1 < retries:
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 10 + attempt * 10
                time.sleep(delay)
                continue
            if exc.code in {500, 502, 503, 504} and attempt + 1 < retries:
                time.sleep(5 + attempt * 5)
                continue
            raise RuntimeError(last_error) from exc
        except (OSError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            if attempt + 1 < retries:
                time.sleep(4 + attempt * 4)
                continue
            raise RuntimeError(last_error) from exc
    raise RuntimeError(last_error or "unknown fetch error")


def write_raw_gz(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb", compresslevel=6) as fh:
        fh.write(raw)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: stringify(row.get(field)) for field in fields})


def stringify(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def as_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def total_pegged_usd(payload: Any) -> float | None:
    if not isinstance(payload, dict):
        return None
    total = 0.0
    found = False
    for value in payload.values():
        number = as_float(value)
        if number is not None:
            total += number
            found = True
    return total if found else None


def normalize_defillama(payloads: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {}

    chains = payloads.get("defillama/chains") or []
    if isinstance(chains, list):
        tables["defillama_chains"] = [
            {
                "name": row.get("name"),
                "gecko_id": row.get("gecko_id"),
                "token_symbol": row.get("tokenSymbol"),
                "chain_id": row.get("chainId"),
                "cmc_id": row.get("cmcId"),
                "tvl_usd": row.get("tvl"),
            }
            for row in chains
            if isinstance(row, dict)
        ]

    protocols = payloads.get("defillama/protocols") or []
    if isinstance(protocols, list):
        tables["defillama_protocols"] = [
            {
                "name": row.get("name"),
                "slug": row.get("slug"),
                "category": row.get("category"),
                "chain": row.get("chain"),
                "chains": row.get("chains"),
                "symbol": row.get("symbol"),
                "url": row.get("url"),
                "tvl_usd": row.get("tvl"),
                "mcap_usd": row.get("mcap"),
                "change_1d": row.get("change_1d"),
                "change_7d": row.get("change_7d"),
                "change_1m": row.get("change_1m"),
                "listed_at": row.get("listedAt"),
            }
            for row in protocols
            if isinstance(row, dict)
        ]

    stablecoinchains = payloads.get("defillama/stablecoinchains") or []
    if isinstance(stablecoinchains, list):
        tables["defillama_stablecoin_chains"] = [
            {
                "name": row.get("name"),
                "stablecoins_usd": total_pegged_usd(row.get("totalCirculatingUSD")),
                "total_circulating_json": row.get("totalCirculatingUSD"),
            }
            for row in stablecoinchains
            if isinstance(row, dict)
        ]

    stablecoins = payloads.get("defillama/stablecoins") or {}
    pegged_assets = stablecoins.get("peggedAssets", []) if isinstance(stablecoins, dict) else []
    if isinstance(pegged_assets, list):
        tables["defillama_stablecoins"] = [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "symbol": row.get("symbol"),
                "peg_type": row.get("pegType"),
                "peg_mechanism": row.get("pegMechanism"),
                "price": row.get("price"),
                "circulating_usd": total_pegged_usd(row.get("circulating")),
                "chains": row.get("chains"),
            }
            for row in pegged_assets
            if isinstance(row, dict)
        ]

    yields = payloads.get("defillama/yields_pools") or {}
    pools = yields.get("data", []) if isinstance(yields, dict) else []
    if isinstance(pools, list):
        tables["defillama_yield_pools"] = [
            {
                "pool": row.get("pool"),
                "chain": row.get("chain"),
                "project": row.get("project"),
                "symbol": row.get("symbol"),
                "tvl_usd": row.get("tvlUsd"),
                "apy": row.get("apy"),
                "apy_base": row.get("apyBase"),
                "apy_reward": row.get("apyReward"),
                "apy_pct_1d": row.get("apyPct1D"),
                "apy_pct_7d": row.get("apyPct7D"),
                "apy_pct_30d": row.get("apyPct30D"),
                "stablecoin": row.get("stablecoin"),
                "il_risk": row.get("ilRisk"),
                "exposure": row.get("exposure"),
                "pool_meta": row.get("poolMeta"),
                "volume_usd_1d": row.get("volumeUsd1d"),
                "volume_usd_7d": row.get("volumeUsd7d"),
            }
            for row in pools
            if isinstance(row, dict)
        ]

    for name in ["dexs_overview", "fees_overview", "open_interest_overview"]:
        payload = payloads.get(f"defillama/{name}") or {}
        rows = extract_overview_protocols(payload, name)
        if rows:
            tables[f"defillama_{name}_protocols"] = rows

    hacks = payloads.get("defillama/hacks") or []
    if isinstance(hacks, list):
        tables["defillama_hacks"] = [
            {
                "date": row.get("date"),
                "name": row.get("name"),
                "classification": row.get("classification"),
                "technique": row.get("technique"),
                "amount_usd": row.get("amount"),
                "chain": row.get("chain"),
                "bridge": row.get("bridge"),
                "target_type": row.get("targetType"),
                "source": row.get("source"),
            }
            for row in hacks
            if isinstance(row, dict)
        ]

    return tables


def extract_overview_protocols(payload: Any, metric_name: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    protocols = payload.get("protocols") or payload.get("data") or []
    if not isinstance(protocols, list):
        return []
    rows = []
    for row in protocols:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "metric": metric_name,
                "name": row.get("name"),
                "display_name": row.get("displayName"),
                "module": row.get("module"),
                "category": row.get("category"),
                "chains": row.get("chains"),
                "total_24h": row.get("total24h"),
                "total_48h_to_24h": row.get("total48hto24h"),
                "total_7d": row.get("total7d"),
                "total_30d": row.get("total30d"),
                "total_all_time": row.get("totalAllTime"),
                "change_1d": row.get("change_1d"),
                "change_7d": row.get("change_7d"),
                "change_1m": row.get("change_1m"),
            }
        )
    return rows


def normalize_coingecko(payloads: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {}

    global_payload = payloads.get("coingecko/global") or {}
    global_data = global_payload.get("data", {}) if isinstance(global_payload, dict) else {}
    if isinstance(global_data, dict):
        tables["coingecko_global"] = [
            {
                "active_cryptocurrencies": global_data.get("active_cryptocurrencies"),
                "markets": global_data.get("markets"),
                "total_market_cap_usd": (global_data.get("total_market_cap") or {}).get("usd"),
                "total_volume_usd": (global_data.get("total_volume") or {}).get("usd"),
                "btc_dominance_pct": (global_data.get("market_cap_percentage") or {}).get("btc"),
                "eth_dominance_pct": (global_data.get("market_cap_percentage") or {}).get("eth"),
                "market_cap_change_24h_usd_pct": global_data.get("market_cap_change_percentage_24h_usd"),
                "updated_at": global_data.get("updated_at"),
            }
        ]

    defi_payload = payloads.get("coingecko/global_defi") or {}
    defi_data = defi_payload.get("data", {}) if isinstance(defi_payload, dict) else {}
    if isinstance(defi_data, dict):
        tables["coingecko_global_defi"] = [
            {
                "defi_market_cap": defi_data.get("defi_market_cap"),
                "eth_market_cap": defi_data.get("eth_market_cap"),
                "defi_to_eth_ratio": defi_data.get("defi_to_eth_ratio"),
                "trading_volume_24h": defi_data.get("trading_volume_24h"),
                "defi_dominance": defi_data.get("defi_dominance"),
                "top_coin_name": defi_data.get("top_coin_name"),
                "top_coin_defi_dominance": defi_data.get("top_coin_defi_dominance"),
            }
        ]

    categories = payloads.get("coingecko/categories") or []
    if isinstance(categories, list):
        tables["coingecko_categories"] = [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "market_cap_usd": row.get("market_cap"),
                "market_cap_change_24h": row.get("market_cap_change_24h"),
                "volume_24h_usd": row.get("volume_24h"),
                "top_3_coins_id": row.get("top_3_coins_id"),
                "updated_at": row.get("updated_at"),
            }
            for row in categories
            if isinstance(row, dict)
        ]

    markets: list[dict[str, Any]] = []
    for name in ["markets_page_1", "markets_page_2"]:
        page = payloads.get(f"coingecko/{name}") or []
        if isinstance(page, list):
            markets.extend(row for row in page if isinstance(row, dict))
    if markets:
        tables["coingecko_top_markets"] = [
            {
                "id": row.get("id"),
                "symbol": row.get("symbol"),
                "name": row.get("name"),
                "market_cap_rank": row.get("market_cap_rank"),
                "current_price": row.get("current_price"),
                "market_cap_usd": row.get("market_cap"),
                "total_volume_usd": row.get("total_volume"),
                "circulating_supply": row.get("circulating_supply"),
                "total_supply": row.get("total_supply"),
                "ath": row.get("ath"),
                "ath_change_percentage": row.get("ath_change_percentage"),
                "price_change_percentage_24h": row.get("price_change_percentage_24h"),
                "price_change_percentage_7d": row.get("price_change_percentage_7d_in_currency"),
                "price_change_percentage_30d": row.get("price_change_percentage_30d_in_currency"),
                "last_updated": row.get("last_updated"),
            }
            for row in markets
        ]

    exchanges = payloads.get("coingecko/exchanges") or []
    if isinstance(exchanges, list):
        tables["coingecko_exchanges"] = [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "year_established": row.get("year_established"),
                "country": row.get("country"),
                "trust_score": row.get("trust_score"),
                "trust_score_rank": row.get("trust_score_rank"),
                "trade_volume_24h_btc": row.get("trade_volume_24h_btc"),
                "trade_volume_24h_btc_normalized": row.get("trade_volume_24h_btc_normalized"),
                "url": row.get("url"),
            }
            for row in exchanges
            if isinstance(row, dict)
        ]

    trending = payloads.get("coingecko/trending") or {}
    coins = trending.get("coins", []) if isinstance(trending, dict) else []
    if isinstance(coins, list):
        tables["coingecko_trending_coins"] = [
            {
                "id": (row.get("item") or {}).get("id"),
                "coin_id": (row.get("item") or {}).get("coin_id"),
                "name": (row.get("item") or {}).get("name"),
                "symbol": (row.get("item") or {}).get("symbol"),
                "market_cap_rank": (row.get("item") or {}).get("market_cap_rank"),
                "score": (row.get("item") or {}).get("score"),
            }
            for row in coins
            if isinstance(row, dict)
        ]

    return tables


def build_chain_summary(tables: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    tvl_by_chain = {row.get("name"): as_float(row.get("tvl_usd")) for row in tables.get("defillama_chains", [])}
    stable_by_chain = {
        row.get("name"): as_float(row.get("stablecoins_usd"))
        for row in tables.get("defillama_stablecoin_chains", [])
    }
    protocol_counts: dict[str, int] = {}
    for row in tables.get("defillama_protocols", []):
        chains = row.get("chains")
        if isinstance(chains, str):
            try:
                chains = json.loads(chains)
            except json.JSONDecodeError:
                chains = [chains]
        if isinstance(chains, list):
            for chain in chains:
                protocol_counts[str(chain)] = protocol_counts.get(str(chain), 0) + 1
        elif row.get("chain"):
            chain = str(row["chain"])
            protocol_counts[chain] = protocol_counts.get(chain, 0) + 1

    names = sorted(set(tvl_by_chain) | set(stable_by_chain) | set(protocol_counts))
    rows = []
    for name in names:
        tvl = tvl_by_chain.get(name)
        stable = stable_by_chain.get(name)
        rows.append(
            {
                "chain": name,
                "tvl_usd": tvl,
                "stablecoins_usd": stable,
                "protocol_count": protocol_counts.get(name, 0),
                "stablecoin_to_tvl": round(stable / tvl, 6) if stable is not None and tvl else "",
            }
        )
    rows.sort(key=lambda row: as_float(row.get("tvl_usd")) or 0.0, reverse=True)
    return rows


def table_fields(table: str) -> list[str]:
    fields = {
        "defillama_chains": ["name", "gecko_id", "token_symbol", "chain_id", "cmc_id", "tvl_usd"],
        "defillama_protocols": [
            "name",
            "slug",
            "category",
            "chain",
            "chains",
            "symbol",
            "url",
            "tvl_usd",
            "mcap_usd",
            "change_1d",
            "change_7d",
            "change_1m",
            "listed_at",
        ],
        "defillama_stablecoin_chains": ["name", "stablecoins_usd", "total_circulating_json"],
        "defillama_stablecoins": [
            "id",
            "name",
            "symbol",
            "peg_type",
            "peg_mechanism",
            "price",
            "circulating_usd",
            "chains",
        ],
        "defillama_yield_pools": [
            "pool",
            "chain",
            "project",
            "symbol",
            "tvl_usd",
            "apy",
            "apy_base",
            "apy_reward",
            "apy_pct_1d",
            "apy_pct_7d",
            "apy_pct_30d",
            "stablecoin",
            "il_risk",
            "exposure",
            "pool_meta",
            "volume_usd_1d",
            "volume_usd_7d",
        ],
        "defillama_hacks": [
            "date",
            "name",
            "classification",
            "technique",
            "amount_usd",
            "chain",
            "bridge",
            "target_type",
            "source",
        ],
        "coingecko_global": [
            "active_cryptocurrencies",
            "markets",
            "total_market_cap_usd",
            "total_volume_usd",
            "btc_dominance_pct",
            "eth_dominance_pct",
            "market_cap_change_24h_usd_pct",
            "updated_at",
        ],
        "coingecko_global_defi": [
            "defi_market_cap",
            "eth_market_cap",
            "defi_to_eth_ratio",
            "trading_volume_24h",
            "defi_dominance",
            "top_coin_name",
            "top_coin_defi_dominance",
        ],
        "coingecko_categories": [
            "id",
            "name",
            "market_cap_usd",
            "market_cap_change_24h",
            "volume_24h_usd",
            "top_3_coins_id",
            "updated_at",
        ],
        "coingecko_top_markets": [
            "id",
            "symbol",
            "name",
            "market_cap_rank",
            "current_price",
            "market_cap_usd",
            "total_volume_usd",
            "circulating_supply",
            "total_supply",
            "ath",
            "ath_change_percentage",
            "price_change_percentage_24h",
            "price_change_percentage_7d",
            "price_change_percentage_30d",
            "last_updated",
        ],
        "coingecko_exchanges": [
            "id",
            "name",
            "year_established",
            "country",
            "trust_score",
            "trust_score_rank",
            "trade_volume_24h_btc",
            "trade_volume_24h_btc_normalized",
            "url",
        ],
        "coingecko_trending_coins": ["id", "coin_id", "name", "symbol", "market_cap_rank", "score"],
        "chain_landscape_summary": ["chain", "tvl_usd", "stablecoins_usd", "protocol_count", "stablecoin_to_tvl"],
    }
    if table.startswith("defillama_") and table.endswith("_overview_protocols"):
        return [
            "metric",
            "name",
            "display_name",
            "module",
            "category",
            "chains",
            "total_24h",
            "total_48h_to_24h",
            "total_7d",
            "total_30d",
            "total_all_time",
            "change_1d",
            "change_7d",
            "change_1m",
        ]
    return fields[table]


def write_sqlite(path: Path, tables: dict[str, list[dict[str, Any]]]) -> None:
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    try:
        for table, rows in sorted(tables.items()):
            fields = table_fields(table)
            con.execute(f"create table {table} ({', '.join(f'{field} text' for field in fields)})")
            if rows:
                placeholders = ",".join("?" for _ in fields)
                con.executemany(
                    f"insert into {table} ({', '.join(fields)}) values ({placeholders})",
                    [[stringify(row.get(field)) for field in fields] for row in rows],
                )
        con.commit()
    finally:
        con.close()


def fetch_all(args: argparse.Namespace, run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    endpoints = []
    if not args.no_defillama:
        endpoints.extend(DEFILLAMA_ENDPOINTS)
    if not args.no_coingecko:
        endpoints.extend(COINGECKO_ENDPOINTS)

    payloads: dict[str, Any] = {}
    manifest: list[dict[str, Any]] = []
    for index, (source, name, url) in enumerate(endpoints, 1):
        started = now_iso()
        record = {
            "source": source,
            "name": name,
            "url": url,
            "started_at": started,
            "finished_at": "",
            "status": "pending",
            "raw_path": f"raw/{source}/{name}.json.gz",
            "bytes_raw": "",
            "bytes_gzip": "",
            "error": "",
        }
        print(f"[{index}/{len(endpoints)}] fetch {source}/{name}", flush=True)
        try:
            payload, raw = fetch_json(url, args.timeout, args.retries)
            raw_path = run_dir / "raw" / source / f"{name}.json.gz"
            write_raw_gz(raw_path, raw)
            payloads[f"{source}/{name}"] = payload
            record.update(
                {
                    "finished_at": now_iso(),
                    "status": "ok",
                    "bytes_raw": len(raw),
                    "bytes_gzip": raw_path.stat().st_size,
                }
            )
        except Exception as exc:
            record.update({"finished_at": now_iso(), "status": "error", "error": str(exc)})
            print(f"  ERROR {source}/{name}: {exc}", file=sys.stderr, flush=True)
        manifest.append(record)
        if index != len(endpoints):
            time.sleep(max(0.0, args.sleep))
    return payloads, manifest


def write_outputs(run_dir: Path, run_id: str, payloads: dict[str, Any], manifest: list[dict[str, Any]]) -> dict[str, Any]:
    tables: dict[str, list[dict[str, Any]]] = {}
    tables.update(normalize_defillama(payloads))
    tables.update(normalize_coingecko(payloads))
    tables["chain_landscape_summary"] = build_chain_summary(tables)

    normalized_dir = run_dir / "normalized"
    for table, rows in sorted(tables.items()):
        write_csv(normalized_dir / f"{table}.csv", rows, table_fields(table))

    write_sqlite(run_dir / "crypto_landscape_snapshot.sqlite3", tables)
    write_csv(run_dir / "manifest.csv", manifest, list(manifest[0].keys()) if manifest else ["source", "name", "status"])

    source_counts = {record["status"]: sum(1 for item in manifest if item["status"] == record["status"]) for record in manifest}
    table_counts = {table: len(rows) for table, rows in sorted(tables.items())}
    summary = {
        "run_id": run_id,
        "generated_at": now_iso(),
        "source_status_counts": dict(sorted(source_counts.items())),
        "table_row_counts": table_counts,
        "top_chain_tvl": tables["chain_landscape_summary"][:20],
        "notes": [
            "Raw API responses are stored as gzip JSON under raw/.",
            "Normalized CSVs and crypto_landscape_snapshot.sqlite3 are built from the same snapshot.",
            "This archive is intended for Drive-first storage; local staging can be deleted after upload.",
        ],
    }
    write_json(run_dir / "run_summary.json", summary)
    write_json(run_dir / "manifest.json", manifest)
    (run_dir / "README.md").write_text(
        "# Crypto Landscape Snapshot\n\n"
        f"Run ID: `{run_id}`\n\n"
        "Drive-first snapshot of crypto market and fundamentals layers from DeFiLlama and CoinGecko.\n\n"
        "Contents:\n"
        "- `raw/`: compressed raw JSON responses.\n"
        "- `normalized/`: analysis-ready CSV extracts.\n"
        "- `crypto_landscape_snapshot.sqlite3`: SQLite copy of normalized tables.\n"
        "- `manifest.*`: source fetch status.\n"
        "- `run_summary.json`: row counts and top chain TVL summary.\n",
        encoding="utf-8",
    )
    return summary


def rclone_copy(src: Path, dest: str) -> None:
    subprocess.run(["rclone", "copy", str(src), dest, "--stats-one-line"], check=True)


def main() -> int:
    args = parse_args()
    run_dir = args.stage_root.resolve() / args.run_id
    if run_dir.exists():
        raise SystemExit(f"Refusing to reuse existing staging path: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)

    print(json.dumps({"run_id": args.run_id, "stage": str(run_dir), "drive_root": args.drive_root}, indent=2), flush=True)
    upload_ok = False
    try:
        payloads, manifest = fetch_all(args, run_dir)
        summary = write_outputs(run_dir, args.run_id, payloads, manifest)
        print(json.dumps({"summary": summary["source_status_counts"], "tables": summary["table_row_counts"]}, indent=2), flush=True)
        if not args.no_upload:
            print(f"upload runs/{args.run_id}", flush=True)
            rclone_copy(run_dir, f"{args.drive_root}/runs/{args.run_id}")
            print("upload latest", flush=True)
            rclone_copy(run_dir, f"{args.drive_root}/latest")
            upload_ok = True
    finally:
        if upload_ok and not args.keep_local:
            shutil.rmtree(run_dir)
            print(f"removed local staging {run_dir}", flush=True)
        elif args.keep_local or not upload_ok:
            print(f"local staging retained {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
