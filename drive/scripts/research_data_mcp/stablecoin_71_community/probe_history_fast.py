#!/usr/bin/env python3
from __future__ import annotations
import csv, json, os, time
from pathlib import Path
from datetime import datetime, timezone
import requests

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("STABLECOIN_71_FAST_OUT", HERE / "fast_output"))
RAW = OUT / "raw_history"
OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

KEY = os.environ.get("COINGECKO_API_KEY", "").strip()
BASE = "https://pro-api.coingecko.com/api/v3" if KEY else "https://api.coingecko.com/api/v3"
HEADERS = {"Accept": "application/json", "User-Agent": "YZU-stablecoin-history-probe/1.1"}
if KEY:
    HEADERS["x-cg-pro-api-key"] = KEY

COIN_IDS = [
    "ageur", "alchemix-usd", "binance-bridged-usdc-bnb-smart-chain",
    "binance-bridged-usdt-bnb-smart-chain", "celo-dollar", "celo-euro",
    "dola-usd", "dollar-2", "ethena-usde", "frax", "gemini-dollar",
    "global-dollar", "gyen", "husd", "monerium-eur-money", "musd", "nxusd",
    "origin-dollar", "paypal-usd", "ripple-usd", "rupiah-token", "stasis-eurs",
    "straitsx-xusd", "terrausd-wormhole", "tether-eurt", "tonoreum",
    "usd1-wlfi", "usdd", "usdh-2", "usdkg", "usds", "usdtb", "vai",
    "yusd-stablecoin", "zasset-zusd"
]
DATES = ["01-07-2022", "01-07-2023", "01-07-2024", "01-07-2025", "01-07-2026"]

def number(value):
    try:
        x = float(value)
        return x if x == x else None
    except Exception:
        return None

def request_history(coin_id: str, date_value: str):
    params = {"date": date_value, "localization": "false"}
    last_error = ""
    for attempt in range(4):
        started = time.time()
        try:
            response = requests.get(
                f"{BASE}/coins/{coin_id}/history",
                params=params,
                headers=HEADERS,
                timeout=45,
            )
            info = {
                "coin_id": coin_id,
                "date_requested": date_value,
                "status_code": response.status_code,
                "elapsed_seconds": round(time.time() - started, 3),
                "requested_url": response.url,
            }
            if response.status_code == 200:
                return response.json(), info
            last_error = f"http_{response.status_code}:{response.text[:400]}"
            info["error"] = last_error
            if response.status_code not in {408, 429, 500, 502, 503, 504}:
                return None, info
        except Exception as exc:
            last_error = f"{type(exc).__name__}:{exc}"
            info = {
                "coin_id": coin_id,
                "date_requested": date_value,
                "status_code": None,
                "elapsed_seconds": round(time.time() - started, 3),
                "error": last_error,
            }
        time.sleep(min(3 * (2 ** attempt), 20))
    return None, info

def write_csv(path: Path, rows: list[dict]):
    fields = sorted({key for row in rows for key in row}) if rows else ["coin_id"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def main():
    observations = []
    manifest = []
    for coin_id in COIN_IDS:
        for date_value in DATES:
            payload, info = request_history(coin_id, date_value)
            manifest.append(info)
            raw_path = RAW / f"{coin_id}__{date_value.replace('-', '_')}.json"
            raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            community = payload.get("community_data") if isinstance(payload, dict) else {}
            community = community or {}
            observations.append({
                "coin_id": coin_id,
                "date_requested": date_value,
                "response_success_flag": int(isinstance(payload, dict)),
                "returned_id": payload.get("id") if isinstance(payload, dict) else None,
                "returned_name": payload.get("name") if isinstance(payload, dict) else None,
                "returned_symbol": payload.get("symbol") if isinstance(payload, dict) else None,
                "reddit_subscribers": number(community.get("reddit_subscribers")),
                "reddit_average_posts_48h": number(community.get("reddit_average_posts_48h")),
                "reddit_average_comments_48h": number(community.get("reddit_average_comments_48h")),
                "reddit_accounts_active_48h": number(community.get("reddit_accounts_active_48h")),
                "telegram_channel_user_count": number(community.get("telegram_channel_user_count")),
                "facebook_likes": number(community.get("facebook_likes")),
                "source": "CoinGecko /coins/{id}/history",
            })
            write_csv(OUT / "01_historical_annual_probe.csv", observations)
            write_csv(OUT / "02_request_manifest.csv", manifest)
            time.sleep(0.35 if KEY else 2.15)

    coverage = []
    for coin_id in COIN_IDS:
        rows = [r for r in observations if r["coin_id"] == coin_id]
        positive_reddit = [r for r in rows if r.get("reddit_subscribers") not in {None, 0, 0.0}]
        positive_telegram = [r for r in rows if r.get("telegram_channel_user_count") not in {None, 0, 0.0}]
        positive_activity = [r for r in rows if r.get("reddit_accounts_active_48h") not in {None, 0, 0.0}]
        coverage.append({
            "coin_id": coin_id,
            "dates_requested": len(DATES),
            "successful_responses": sum(r["response_success_flag"] for r in rows),
            "positive_reddit_subscriber_dates": len(positive_reddit),
            "positive_telegram_member_dates": len(positive_telegram),
            "positive_reddit_activity_dates": len(positive_activity),
            "first_positive_reddit_date": positive_reddit[0]["date_requested"] if positive_reddit else "",
            "last_positive_reddit_date": positive_reddit[-1]["date_requested"] if positive_reddit else "",
            "historical_community_fields_found_flag": int(bool(positive_reddit or positive_telegram or positive_activity)),
        })
    write_csv(OUT / "03_historical_coverage_by_coin_id.csv", coverage)
    summary = {
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_mode": "pro" if KEY else "public",
        "coin_ids_probed": len(COIN_IDS),
        "dates_per_coin": len(DATES),
        "successful_responses": sum(r["response_success_flag"] for r in observations),
        "coin_ids_with_positive_reddit_history": sum(r["positive_reddit_subscriber_dates"] > 0 for r in coverage),
        "coin_ids_with_positive_telegram_history": sum(r["positive_telegram_member_dates"] > 0 for r in coverage),
        "coin_ids_with_any_historical_community_field": sum(r["historical_community_fields_found_flag"] for r in coverage),
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
