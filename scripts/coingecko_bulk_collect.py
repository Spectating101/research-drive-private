#!/usr/bin/env python3
"""
CoinGecko bulk collector for research/RA workflows.

Collects and stores:
- coin categories
- coin list (id map)
- market snapshot
- coin details (metadata fields shown on coin info pages)
- historical prices / market caps / volumes
- exchange list/data/details/volume chart

Storage target: SQLite (resumable, append-safe for snapshots).
"""

from __future__ import annotations

import argparse
import csv
import math
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DB_PATH = Path("data/crypto/coingecko/coingecko_dump.sqlite3")
PRO_BASE_URL = "https://pro-api.coingecko.com/api/v3"
PUBLIC_BASE_URL = "https://api.coingecko.com/api/v3"
DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) SharpeRenaissance/1.0"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_ENV_FILE = _REPO_ROOT / ".env.local"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_datetime_to_unix(value: str) -> int:
    v = (value or "").strip().lower()
    if v == "now":
        return int(time.time())
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def normalize_query_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def load_coin_ids_from_file(path: Path, column: str) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    first_nonblank = next((line for line in lines if line.strip()), "")
    if not first_nonblank:
        return []

    if "\t" in first_nonblank:
        reader = csv.DictReader(lines, delimiter="\t")
        if reader.fieldnames and column in reader.fieldnames:
            return dedupe_preserve_order(row.get(column, "") for row in reader)
    if "," in first_nonblank:
        reader = csv.DictReader(lines)
        if reader.fieldnames and column in reader.fieldnames:
            return dedupe_preserve_order(row.get(column, "") for row in reader)
    return dedupe_preserve_order(lines)


def sqlite_real(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        out = float(value)
        if not math.isfinite(out):
            return None
        return out
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_value(name: str, env_path: Path | None = None) -> str:
    explicit_path = env_path is not None
    path = env_path or _ENV_FILE
    if not explicit_path:
        value = str(os.environ.get(name, "") or "").strip()
        if value:
            return value
    if not path.exists():
        return str(os.environ.get(name, "") or "").strip() if explicit_path else ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if not line.startswith(f"{name}="):
            continue
        return _strip_wrapping_quotes(line.split("=", 1)[1])
    return str(os.environ.get(name, "") or "").strip() if explicit_path else ""


@dataclass
class CoinGeckoClient:
    base_url: str
    api_key: str
    timeout_s: int = 30
    min_interval_s: float = 1.2
    max_retries: int = 4
    retry_backoff_s: float = 3.0
    _last_request_mono: float = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_mono
        wait_s = self.min_interval_s - elapsed
        if wait_s > 0:
            time.sleep(wait_s)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = urllib.parse.urlencode(
            {k: normalize_query_value(v) for k, v in (params or {}).items() if v is not None}
        )
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"

        for attempt in range(self.max_retries + 1):
            self._throttle()
            req = urllib.request.Request(url=url, method="GET")
            req.add_header("Accept", "application/json")
            req.add_header("User-Agent", DEFAULT_USER_AGENT)
            if self.api_key:
                req.add_header("x-cg-pro-api-key", self.api_key)

            payload = ""
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    payload = resp.read().decode("utf-8", errors="replace")
                return json.loads(payload)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code in {408, 429, 500, 503} and attempt < self.max_retries:
                    wait_s = self.retry_backoff_s * (2 ** attempt)
                    print(
                        f"[retry] HTTP {exc.code} url={url} attempt={attempt + 1}/{self.max_retries} wait={wait_s:.1f}s",
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(wait_s)
                    continue
                raise RuntimeError(f"HTTP {exc.code} for {url}: {body[:350]}") from exc
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    wait_s = self.retry_backoff_s * (2 ** attempt)
                    print(
                        f"[retry] network url={url} attempt={attempt + 1}/{self.max_retries} wait={wait_s:.1f}s err={exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(wait_s)
                    continue
                raise RuntimeError(f"Network error for {url}: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Non-JSON response for {url}: {payload[:350]}") from exc
            finally:
                self._last_request_mono = time.monotonic()

        raise RuntimeError(f"Request retries exhausted for {url}")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS ingest_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            args_json TEXT NOT NULL,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS categories (
            category_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            retrieved_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS coins (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            platforms_json TEXT NOT NULL,
            status TEXT NOT NULL,
            retrieved_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS coin_markets (
            coin_id TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            market_cap_rank INTEGER,
            current_price REAL,
            market_cap REAL,
            total_volume REAL,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (coin_id, retrieved_at)
        );

        CREATE TABLE IF NOT EXISTS coin_details (
            coin_id TEXT PRIMARY KEY,
            asset_platform_id TEXT,
            hashing_algorithm TEXT,
            categories_json TEXT NOT NULL,
            links_json TEXT NOT NULL,
            image_json TEXT NOT NULL,
            platforms_json TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            retrieved_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS coin_history (
            coin_id TEXT NOT NULL,
            ts_ms INTEGER NOT NULL,
            price REAL,
            market_cap REAL,
            total_volume REAL,
            retrieved_at TEXT NOT NULL,
            PRIMARY KEY (coin_id, ts_ms)
        );

        CREATE TABLE IF NOT EXISTS coin_history_ranges (
            coin_id TEXT NOT NULL,
            from_ts INTEGER NOT NULL,
            to_ts INTEGER NOT NULL,
            point_count INTEGER NOT NULL,
            retrieved_at TEXT NOT NULL,
            PRIMARY KEY (coin_id, from_ts, to_ts)
        );

        CREATE TABLE IF NOT EXISTS exchanges (
            exchange_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            year_established INTEGER,
            country TEXT,
            trust_score INTEGER,
            trade_volume_24h_btc REAL,
            raw_json TEXT NOT NULL,
            retrieved_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS exchange_details (
            exchange_id TEXT PRIMARY KEY,
            raw_json TEXT NOT NULL,
            retrieved_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS exchange_volume_chart (
            exchange_id TEXT NOT NULL,
            ts_ms INTEGER NOT NULL,
            volume_btc REAL,
            retrieved_at TEXT NOT NULL,
            PRIMARY KEY (exchange_id, ts_ms)
        );

        CREATE TABLE IF NOT EXISTS failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL,
            item_id TEXT,
            error TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def log_failure(conn: sqlite3.Connection, endpoint: str, item_id: str | None, error: str) -> None:
    conn.execute(
        "INSERT INTO failures(endpoint, item_id, error, occurred_at) VALUES (?, ?, ?, ?)",
        (endpoint, item_id, error[:2000], utc_now_iso()),
    )
    conn.commit()


def upsert_categories(conn: sqlite3.Connection, rows: list[dict[str, Any]], fetched_at: str) -> None:
    payload = [(str(r.get("category_id") or ""), str(r.get("name") or ""), fetched_at) for r in rows]
    conn.executemany(
        """
        INSERT INTO categories(category_id, name, retrieved_at)
        VALUES (?, ?, ?)
        ON CONFLICT(category_id) DO UPDATE SET
          name=excluded.name,
          retrieved_at=excluded.retrieved_at
        """,
        payload,
    )
    conn.commit()


def upsert_coins(conn: sqlite3.Connection, rows: list[dict[str, Any]], status: str, fetched_at: str) -> None:
    payload = [
        (
            str(r.get("id") or ""),
            str(r.get("symbol") or ""),
            str(r.get("name") or ""),
            json.dumps(r.get("platforms") or {}, ensure_ascii=False),
            status,
            fetched_at,
        )
        for r in rows
        if r.get("id")
    ]
    conn.executemany(
        """
        INSERT INTO coins(id, symbol, name, platforms_json, status, retrieved_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          symbol=excluded.symbol,
          name=excluded.name,
          platforms_json=excluded.platforms_json,
          status=excluded.status,
          retrieved_at=excluded.retrieved_at
        """,
        payload,
    )
    conn.commit()


def insert_market_snapshot(conn: sqlite3.Connection, rows: list[dict[str, Any]], fetched_at: str) -> None:
    payload = []
    for r in rows:
        coin_id = str(r.get("id") or "")
        if not coin_id:
            continue
        payload.append(
            (
                coin_id,
                fetched_at,
                r.get("market_cap_rank"),
                r.get("current_price"),
                r.get("market_cap"),
                r.get("total_volume"),
                json.dumps(r, ensure_ascii=False),
            )
        )
    conn.executemany(
        """
        INSERT OR REPLACE INTO coin_markets(
          coin_id, retrieved_at, market_cap_rank, current_price, market_cap, total_volume, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        payload,
    )
    conn.commit()


def upsert_coin_detail(conn: sqlite3.Connection, coin_id: str, row: dict[str, Any], fetched_at: str) -> None:
    conn.execute(
        """
        INSERT INTO coin_details(
          coin_id, asset_platform_id, hashing_algorithm, categories_json, links_json, image_json,
          platforms_json, raw_json, retrieved_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(coin_id) DO UPDATE SET
          asset_platform_id=excluded.asset_platform_id,
          hashing_algorithm=excluded.hashing_algorithm,
          categories_json=excluded.categories_json,
          links_json=excluded.links_json,
          image_json=excluded.image_json,
          platforms_json=excluded.platforms_json,
          raw_json=excluded.raw_json,
          retrieved_at=excluded.retrieved_at
        """,
        (
            coin_id,
            row.get("asset_platform_id"),
            row.get("hashing_algorithm"),
            json.dumps(row.get("categories") or [], ensure_ascii=False),
            json.dumps(row.get("links") or {}, ensure_ascii=False),
            json.dumps(row.get("image") or {}, ensure_ascii=False),
            json.dumps(row.get("platforms") or {}, ensure_ascii=False),
            json.dumps(row, ensure_ascii=False),
            fetched_at,
        ),
    )


def insert_history(
    conn: sqlite3.Connection,
    coin_id: str,
    row: dict[str, Any],
    fetched_at: str,
) -> int:
    prices = row.get("prices") or []
    caps = {int(x[0]): x[1] for x in (row.get("market_caps") or []) if len(x) >= 2}
    vols = {int(x[0]): x[1] for x in (row.get("total_volumes") or []) if len(x) >= 2}
    points = []
    for item in prices:
        if len(item) < 2:
            continue
        ts_ms = int(item[0])
        points.append(
            (
                coin_id,
                ts_ms,
                sqlite_real(item[1]),
                sqlite_real(caps.get(ts_ms)),
                sqlite_real(vols.get(ts_ms)),
                fetched_at,
            )
        )
    conn.executemany(
        """
        INSERT INTO coin_history(coin_id, ts_ms, price, market_cap, total_volume, retrieved_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(coin_id, ts_ms) DO UPDATE SET
          price=excluded.price,
          market_cap=excluded.market_cap,
          total_volume=excluded.total_volume,
          retrieved_at=excluded.retrieved_at
        """,
        points,
    )
    return len(points)


def existing_coin_detail_ids(conn: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in conn.execute("SELECT coin_id FROM coin_details")}


def history_range_exists(conn: sqlite3.Connection, coin_id: str, from_ts: int, to_ts: int) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM coin_history_ranges
        WHERE coin_id = ?
          AND from_ts = ?
          AND to_ts = ?
        LIMIT 1
        """,
        (coin_id, int(from_ts), int(to_ts)),
    ).fetchone()
    return row is not None


def record_history_range(conn: sqlite3.Connection, coin_id: str, from_ts: int, to_ts: int, point_count: int, fetched_at: str) -> None:
    conn.execute(
        """
        INSERT INTO coin_history_ranges(coin_id, from_ts, to_ts, point_count, retrieved_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(coin_id, from_ts, to_ts) DO UPDATE SET
          point_count=excluded.point_count,
          retrieved_at=excluded.retrieved_at
        """,
        (coin_id, int(from_ts), int(to_ts), int(point_count), fetched_at),
    )


def upsert_exchange(conn: sqlite3.Connection, row: dict[str, Any], fetched_at: str) -> None:
    exchange_id = str(row.get("id") or "")
    if not exchange_id:
        return
    conn.execute(
        """
        INSERT INTO exchanges(
          exchange_id, name, year_established, country, trust_score, trade_volume_24h_btc, raw_json, retrieved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(exchange_id) DO UPDATE SET
          name=excluded.name,
          year_established=excluded.year_established,
          country=excluded.country,
          trust_score=excluded.trust_score,
          trade_volume_24h_btc=excluded.trade_volume_24h_btc,
          raw_json=excluded.raw_json,
          retrieved_at=excluded.retrieved_at
        """,
        (
            exchange_id,
            str(row.get("name") or ""),
            row.get("year_established"),
            row.get("country"),
            row.get("trust_score"),
            row.get("trade_volume_24h_btc"),
            json.dumps(row, ensure_ascii=False),
            fetched_at,
        ),
    )


def upsert_exchange_detail(conn: sqlite3.Connection, exchange_id: str, row: dict[str, Any], fetched_at: str) -> None:
    conn.execute(
        """
        INSERT INTO exchange_details(exchange_id, raw_json, retrieved_at)
        VALUES (?, ?, ?)
        ON CONFLICT(exchange_id) DO UPDATE SET
          raw_json=excluded.raw_json,
          retrieved_at=excluded.retrieved_at
        """,
        (exchange_id, json.dumps(row, ensure_ascii=False), fetched_at),
    )


def insert_exchange_volume_chart(conn: sqlite3.Connection, exchange_id: str, rows: Iterable[Any], fetched_at: str) -> int:
    payload = []
    for item in rows:
        if not isinstance(item, list) or len(item) < 2:
            continue
        payload.append((exchange_id, int(item[0]), item[1], fetched_at))
    conn.executemany(
        """
        INSERT INTO exchange_volume_chart(exchange_id, ts_ms, volume_btc, retrieved_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(exchange_id, ts_ms) DO UPDATE SET
          volume_btc=excluded.volume_btc,
          retrieved_at=excluded.retrieved_at
        """,
        payload,
    )
    return len(payload)


def fetch_paginated_markets(
    client: CoinGeckoClient, vs_currency: str, per_page: int, max_pages: int
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        if max_pages > 0 and page > max_pages:
            break
        chunk = client.get(
            "/coins/markets",
            {
                "vs_currency": vs_currency,
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": page,
                "sparkline": False,
                "price_change_percentage": "24h,7d,30d",
            },
        )
        if not isinstance(chunk, list) or not chunk:
            break
        rows.extend(chunk)
        print(f"[markets] page={page} rows={len(chunk)} total={len(rows)}", flush=True)
        if len(chunk) < per_page:
            break
        page += 1
    return rows


def fetch_paginated_exchanges(client: CoinGeckoClient, per_page: int, max_pages: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        if max_pages > 0 and page > max_pages:
            break
        chunk = client.get("/exchanges", {"page": page, "per_page": per_page})
        if not isinstance(chunk, list) or not chunk:
            break
        rows.extend(chunk)
        print(f"[exchanges] page={page} rows={len(chunk)} total={len(rows)}", flush=True)
        if len(chunk) < per_page:
            break
        page += 1
    return rows


def coin_history_chunks(start_ts: int, end_ts: int, chunk_days: int) -> list[tuple[int, int]]:
    if start_ts >= end_ts:
        return []
    chunk_s = max(1, chunk_days) * 24 * 60 * 60
    out: list[tuple[int, int]] = []
    cur = start_ts
    while cur < end_ts:
        nxt = min(cur + chunk_s, end_ts)
        out.append((cur, nxt))
        cur = nxt
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Collect CoinGecko coin/category/history/exchange datasets into SQLite.")
    ap.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    ap.add_argument("--base-url", default=PRO_BASE_URL, help=f"API root URL (default: {PRO_BASE_URL})")
    ap.add_argument(
        "--api-key",
        default="",
        help="CoinGecko Pro API key (or use COINGECKO_API_KEY env)",
    )
    ap.add_argument("--vs-currency", default="usd")
    ap.add_argument("--coins-limit", type=int, default=50, help="Limit number of coins processed for detail/history.")
    ap.add_argument("--coin-id", action="append", default=[], help="Explicit coin id(s) for detail/history (repeatable).")
    ap.add_argument("--coin-id-file", type=Path, help="Optional file containing explicit coin ids or a table with a coin-id column.")
    ap.add_argument("--coin-id-column", default="coingecko_id", help="Column name to read from --coin-id-file tables.")
    ap.add_argument("--history-from", default="2020-01-01T00:00:00+00:00")
    ap.add_argument("--history-to", default="now")
    ap.add_argument("--history-chunk-days", type=int, default=365)
    ap.add_argument("--exchange-limit", type=int, default=100, help="Limit number of exchanges for detail/chart calls.")
    ap.add_argument("--exchange-volume-days", type=int, default=365)
    ap.add_argument("--markets-per-page", type=int, default=250)
    ap.add_argument("--markets-max-pages", type=int, default=0, help="0 means fetch all pages.")
    ap.add_argument("--exchanges-per-page", type=int, default=250)
    ap.add_argument("--exchanges-max-pages", type=int, default=0, help="0 means fetch all pages.")
    ap.add_argument("--min-interval-seconds", type=float, default=1.2, help="Throttle between API calls.")
    ap.add_argument("--timeout-seconds", type=int, default=30)
    ap.add_argument("--max-retries", type=int, default=4)
    ap.add_argument("--retry-backoff-seconds", type=float, default=3.0)
    ap.add_argument("--skip-coin-details", action="store_true")
    ap.add_argument("--skip-history", action="store_true")
    ap.add_argument("--skip-exchanges", action="store_true")
    ap.add_argument("--skip-categories", action="store_true")
    ap.add_argument("--skip-coins-list", action="store_true")
    ap.add_argument("--skip-markets", action="store_true")
    ap.add_argument("--skip-existing-details", action="store_true", help="Skip API calls for coins already present in coin_details.")
    ap.add_argument(
        "--skip-existing-history",
        action="store_true",
        help="Skip history chunk calls when any rows already exist for that coin/range.",
    )
    ap.add_argument("--use-public-api", action="store_true", help="Use public API root and skip Pro header auth.")
    return ap


def main() -> int:
    args = build_parser().parse_args()
    base_url = PUBLIC_BASE_URL if args.use_public_api else args.base_url
    api_key = "" if args.use_public_api else str(args.api_key or load_env_value("COINGECKO_API_KEY")).strip()

    if not args.use_public_api and not api_key:
        print(
            "ERROR: Missing API key. Pass --api-key or COINGECKO_API_KEY, or use --use-public-api for limited access.",
            file=sys.stderr,
        )
        return 2

    effective_min_interval = float(args.min_interval_seconds)
    if args.use_public_api:
        effective_min_interval = max(2.5, effective_min_interval)
        if effective_min_interval != float(args.min_interval_seconds):
            print(
                f"[info] raised min interval to {effective_min_interval:.1f}s for public CoinGecko API stability",
                flush=True,
            )

    run_id = f"cg-{int(time.time())}"
    started_at = utc_now_iso()
    args_json = json.dumps(vars(args), default=str, ensure_ascii=False)

    args.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(args.db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO ingest_runs(run_id, started_at, status, args_json) VALUES (?, ?, ?, ?)",
        (run_id, started_at, "running", args_json),
    )
    conn.commit()

    client = CoinGeckoClient(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        timeout_s=int(args.timeout_seconds),
        min_interval_s=effective_min_interval,
        max_retries=int(args.max_retries),
        retry_backoff_s=float(args.retry_backoff_seconds),
    )

    try:
        # Baseline endpoints.
        fetched_at = utc_now_iso()
        categories: list[dict[str, Any]] = []
        if not args.skip_categories:
            categories = client.get("/coins/categories/list")
            if not isinstance(categories, list):
                raise RuntimeError("/coins/categories/list did not return a list")
            upsert_categories(conn, categories, fetched_at)
            print(f"[ok] categories={len(categories)}", flush=True)
        else:
            print("[skip] categories", flush=True)

        coins: list[dict[str, Any]] = []
        if not args.skip_coins_list:
            coins = client.get("/coins/list", {"include_platform": True, "status": "active"})
            if not isinstance(coins, list):
                raise RuntimeError("/coins/list did not return a list")
            upsert_coins(conn, coins, "active", fetched_at)
            print(f"[ok] coins={len(coins)}", flush=True)
        else:
            print("[skip] coins list", flush=True)

        markets: list[dict[str, Any]] = []
        if not args.skip_markets:
            markets = fetch_paginated_markets(
                client,
                args.vs_currency,
                int(args.markets_per_page),
                int(args.markets_max_pages),
            )
            insert_market_snapshot(conn, markets, fetched_at)
            print(f"[ok] markets={len(markets)}", flush=True)
        else:
            print("[skip] markets", flush=True)

        file_coin_ids: list[str] = []
        if args.coin_id_file:
            file_coin_ids = load_coin_ids_from_file(Path(args.coin_id_file), str(args.coin_id_column))

        explicit_coin_ids = dedupe_preserve_order([*(args.coin_id or []), *file_coin_ids])
        market_coin_ids = dedupe_preserve_order(str(r.get("id")) for r in markets if r.get("id"))
        coin_list_ids = dedupe_preserve_order(str(r.get("id")) for r in coins if r.get("id"))
        if explicit_coin_ids:
            target_coin_ids = explicit_coin_ids
        else:
            # /coins/markets does not currently cover the full active list, so take the union.
            target_coin_ids = dedupe_preserve_order([*market_coin_ids, *coin_list_ids])
        if not target_coin_ids and (not args.skip_coin_details or not args.skip_history):
            raise RuntimeError("No coin IDs available for details/history. Use --coin-id or enable markets/coins list.")
        if target_coin_ids:
            print(
                "[ok] target_coins="
                f"{len(target_coin_ids)} "
                f"(explicit={len(explicit_coin_ids)} market_unique={len(market_coin_ids)} coin_list={len(coin_list_ids)})",
                flush=True,
            )

        if args.coins_limit > 0:
            target_coin_ids = target_coin_ids[: int(args.coins_limit)]

        # Coin details.
        if not args.skip_coin_details:
            existing_details = existing_coin_detail_ids(conn) if args.skip_existing_details else set()
            skipped_existing = 0
            fetched_details = 0
            for idx, coin_id in enumerate(target_coin_ids, start=1):
                if coin_id in existing_details:
                    skipped_existing += 1
                    continue
                try:
                    row = client.get(
                        f"/coins/{urllib.parse.quote(coin_id, safe='')}",
                        {
                            "localization": False,
                            "tickers": False,
                            "market_data": True,
                            "community_data": True,
                            "developer_data": True,
                            "sparkline": False,
                        },
                    )
                    if not isinstance(row, dict):
                        raise RuntimeError("coin detail response is not an object")
                    upsert_coin_detail(conn, coin_id, row, utc_now_iso())
                    fetched_details += 1
                    if idx % 25 == 0:
                        conn.commit()
                    print(f"[detail] {idx}/{len(target_coin_ids)} {coin_id}", flush=True)
                except Exception as exc:
                    err = str(exc)
                    print(f"[warn] detail failed coin={coin_id} err={err}", file=sys.stderr, flush=True)
                    log_failure(conn, "/coins/{id}", coin_id, err)
            conn.commit()
            print(f"[ok] details fetched={fetched_details} skipped_existing={skipped_existing}", flush=True)

        # Historical prices.
        if not args.skip_history:
            start_ts = parse_datetime_to_unix(args.history_from)
            end_ts = parse_datetime_to_unix(args.history_to)
            chunks = coin_history_chunks(start_ts, end_ts, int(args.history_chunk_days))
            total_inserted = 0
            total_skipped_chunks = 0
            total_fetched_chunks = 0
            for idx, coin_id in enumerate(target_coin_ids, start=1):
                coin_inserted = 0
                coin_skipped_chunks = 0
                coin_fetched_chunks = 0
                for from_ts, to_ts in chunks:
                    if args.skip_existing_history and history_range_exists(conn, coin_id, from_ts, to_ts):
                        coin_skipped_chunks += 1
                        total_skipped_chunks += 1
                        continue
                    try:
                        row = client.get(
                            f"/coins/{urllib.parse.quote(coin_id, safe='')}/market_chart/range",
                            {
                                "vs_currency": args.vs_currency,
                                "from": from_ts,
                                "to": to_ts,
                            },
                        )
                        if not isinstance(row, dict):
                            raise RuntimeError("history response is not an object")
                        fetched_at = utc_now_iso()
                        inserted = insert_history(conn, coin_id, row, fetched_at)
                        record_history_range(conn, coin_id, from_ts, to_ts, inserted, fetched_at)
                        total_inserted += inserted
                        coin_inserted += inserted
                        coin_fetched_chunks += 1
                        total_fetched_chunks += 1
                    except Exception as exc:
                        err = str(exc)
                        print(
                            f"[warn] history failed coin={coin_id} range={from_ts}-{to_ts} err={err}",
                            file=sys.stderr,
                            flush=True,
                        )
                        log_failure(conn, "/coins/{id}/market_chart/range", coin_id, err)
                if idx % 10 == 0:
                    conn.commit()
                print(
                    f"[history] {idx}/{len(target_coin_ids)} {coin_id} "
                    f"chunks_fetched={coin_fetched_chunks} chunks_skipped={coin_skipped_chunks} points={coin_inserted}",
                    flush=True,
                )
            conn.commit()
            print(
                f"[ok] history_points={total_inserted} "
                f"history_chunks_fetched={total_fetched_chunks} history_chunks_skipped={total_skipped_chunks}",
                flush=True,
            )

        # Exchanges.
        if not args.skip_exchanges:
            exchanges = fetch_paginated_exchanges(client, int(args.exchanges_per_page), int(args.exchanges_max_pages))
            for row in exchanges:
                upsert_exchange(conn, row, utc_now_iso())
            conn.commit()
            print(f"[ok] exchanges={len(exchanges)}", flush=True)

            exchange_ids = dedupe_preserve_order(str(x.get("id")) for x in exchanges if x.get("id"))
            if args.exchange_limit > 0:
                exchange_ids = exchange_ids[: int(args.exchange_limit)]
            for idx, exchange_id in enumerate(exchange_ids, start=1):
                try:
                    detail = client.get(f"/exchanges/{urllib.parse.quote(exchange_id, safe='')}")
                    if not isinstance(detail, dict):
                        raise RuntimeError("exchange detail response is not an object")
                    upsert_exchange_detail(conn, exchange_id, detail, utc_now_iso())
                except Exception as exc:
                    err = str(exc)
                    print(f"[warn] exchange detail failed id={exchange_id} err={err}", file=sys.stderr, flush=True)
                    log_failure(conn, "/exchanges/{id}", exchange_id, err)

                try:
                    chart = client.get(
                        f"/exchanges/{urllib.parse.quote(exchange_id, safe='')}/volume_chart",
                        {"days": int(args.exchange_volume_days)},
                    )
                    if not isinstance(chart, list):
                        raise RuntimeError("exchange volume chart is not a list")
                    insert_exchange_volume_chart(conn, exchange_id, chart, utc_now_iso())
                except Exception as exc:
                    err = str(exc)
                    print(f"[warn] volume chart failed id={exchange_id} err={err}", file=sys.stderr, flush=True)
                    log_failure(conn, "/exchanges/{id}/volume_chart", exchange_id, err)

                if idx % 20 == 0:
                    conn.commit()
                print(f"[exchange] {idx}/{len(exchange_ids)} {exchange_id}", flush=True)
            conn.commit()

        conn.execute(
            "UPDATE ingest_runs SET completed_at=?, status=?, note=? WHERE run_id=?",
            (utc_now_iso(), "done", "success", run_id),
        )
        conn.commit()
    except Exception as exc:
        conn.execute(
            "UPDATE ingest_runs SET completed_at=?, status=?, note=? WHERE run_id=?",
            (utc_now_iso(), "failed", str(exc)[:2000], run_id),
        )
        conn.commit()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(f"✅ Completed run_id={run_id} db={args.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
