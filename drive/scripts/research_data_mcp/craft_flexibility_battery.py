#!/usr/bin/env python3
"""Craft flexibility battery: ~100 public URLs → plan shape + optional land subset + Composer smoke.

Does NOT treat vendors as product modules — every target is a URL for research_craft_collect_plan.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "http://100.127.141.44:8765"
DESK_TOKEN_PATH = Path.home() / ".config/research-drive/front-door.desk-token"


def desk_token() -> str:
    return DESK_TOKEN_PATH.read_text().strip()

OUT = Path(
    "/home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/"
    "research-drive-private-front-door/drive/docs/status/generated/craft_flexibility_battery.json"
)

# Diverse public targets: direct files, gov APIs, open data, docs/HTML, crypto peers of Skynet, research portals.
URLS: list[tuple[str, str]] = [
    # --- direct JSON/CSV/API (should prefer http_manifest) ---
    ("sec_tickers", "https://www.sec.gov/files/company_tickers.json"),
    ("sec_tickers_exch", "https://www.sec.gov/files/company_tickers_exchange.json"),
    ("twse_day_all", "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"),
    ("twse_bwibbu", "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"),
    ("twse_profile", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"),
    ("twse_material", "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"),
    ("twse_revenue", "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"),
    ("wb_countries", "https://api.worldbank.org/v2/country?format=json&per_page=50"),
    ("wb_indicators", "https://api.worldbank.org/v2/indicator?format=json&per_page=50"),
    ("fred_gdp", "https://api.stlouisfed.org/fred/series?series_id=GDP&file_type=json"),
    ("nasa_apod_meta", "https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY"),
    ("usgs_quakes", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"),
    ("usgs_week", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.geojson"),
    ("gdelt_doc", "https://api.gdeltproject.org/api/v2/doc/doc?query=taiwan&mode=ArtList&format=json&maxrecords=10"),
    ("coingecko_ping", "https://api.coingecko.com/api/v3/ping"),
    ("coingecko_global", "https://api.coingecko.com/api/v3/global"),
    ("coingecko_markets", "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page=5"),
    ("defillama_protocols", "https://api.llama.fi/protocols"),
    ("defillama_stablecoins", "https://stablecoins.llama.fi/stablecoins?includePrices=true"),
    ("defillama_chains", "https://api.llama.fi/v2/chains"),
    ("binance_ping", "https://api.binance.com/api/v3/ping"),
    ("binance_time", "https://api.binance.com/api/v3/time"),
    ("binance_ticker", "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"),
    ("kraken_time", "https://api.kraken.com/0/public/Time"),
    ("kraken_asset", "https://api.kraken.com/0/public/Assets"),
    ("cryptocompare_price", "https://min-api.cryptocompare.com/data/price?fsym=BTC&tsyms=USD"),
    ("mempool_fees", "https://mempool.space/api/v1/fees/recommended"),
    ("blockchair_stats", "https://api.blockchair.com/bitcoin/stats"),
    ("etherscan_eth_supply", "https://api.etherscan.io/api?module=stats&action=ethsupply"),
    ("openalex_works", "https://api.openalex.org/works?search=stablecoin&per-page=5"),
    ("openalex_authors", "https://api.openalex.org/authors?search=finance&per-page=5"),
    ("zenodo_records", "https://zenodo.org/api/records?q=nft&size=5"),
    ("datacite_dois", "https://api.datacite.org/dois?query=taiwan%20equity&page[size]=5"),
    ("crossref_works", "https://api.crossref.org/works?query=momentum%20taiwan&rows=5"),
    ("arxiv_api", "https://export.arxiv.org/api/query?search_query=all:stablecoin&start=0&max_results=3"),
    ("pubmed_search", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=fintech&retmode=json&retmax=5"),
    ("wikidata_sparql_meta", "https://www.wikidata.org/wiki/Special:EntityData/Q154798.json"),
    ("wikipedia_summary", "https://en.wikipedia.org/api/rest_v1/page/summary/Tether_(cryptocurrency)"),
    ("restcountries", "https://restcountries.com/v3.1/name/taiwan"),
    ("openmeteo", "https://api.open-meteo.com/v1/forecast?latitude=25.03&longitude=121.57&current_weather=true"),
    ("nominatim", "https://nominatim.openstreetmap.org/search?q=Taipei&format=json&limit=3"),
    ("github_meta", "https://api.github.com/repos/ethereum/go-ethereum"),
    ("github_releases", "https://api.github.com/repos/bitcoin/bitcoin/releases?per_page=3"),
    ("hn_top", "https://hacker-news.firebaseio.com/v0/topstories.json"),
    ("hn_item", "https://hacker-news.firebaseio.com/v0/item/1.json"),
    ("jsonplaceholder", "https://jsonplaceholder.typicode.com/posts/1"),
    ("httpbin_json", "https://httpbin.org/json"),
    ("httpbin_uuid", "https://httpbin.org/uuid"),
    ("dog_ceo", "https://dog.ceo/api/breeds/image/random"),
    ("catfact", "https://catfact.ninja/fact"),
    ("agify", "https://api.agify.io/?name=michael"),
    ("genderize", "https://api.genderize.io/?name=alice"),
    ("ipify", "https://api.ipify.org?format=json"),
    ("quotable", "https://api.quotable.io/random"),
    ("jokeapi", "https://v2.jokeapi.dev/joke/Any?type=single"),
    ("universities", "https://universities.hipolabs.com/search?country=Taiwan"),
    ("exchange_rate", "https://open.er-api.com/v6/latest/USD"),
    ("coinbase_spot", "https://api.coinbase.com/v2/prices/BTC-USD/spot"),
    ("blockchain_info", "https://blockchain.info/ticker"),
    ("alternative_fng", "https://api.alternative.me/fng/?limit=3"),
    ("messari_assets", "https://data.messari.io/api/v1/assets?limit=5"),
    ("coinpaprika", "https://api.coinpaprika.com/v1/tickers?limit=5"),
    ("coincap_assets", "https://api.coincap.io/v2/assets?limit=5"),
    ("gemini_symbols", "https://api.gemini.com/v1/symbols"),
    ("bitstamp_ticker", "https://www.bitstamp.net/api/v2/ticker/btcusd/"),
    ("poloniex_time", "https://api.poloniex.com/markets/timestamp"),
    ("okx_time", "https://www.okx.com/api/v5/public/time"),
    ("bybit_time", "https://api.bybit.com/v5/market/time"),
    ("deribit_time", "https://www.deribit.com/api/v2/public/get_time"),
    ("ftx_legacy_note", "https://api.coingecko.com/api/v3/exchanges/list"),
    ("glassnode_freeish", "https://api.coingecko.com/api/v3/coins/list"),
    # --- HTML / SPA / leaderboard peers (often scraper_run) ---
    ("defillama_site", "https://defillama.com/stablecoins"),
    ("defillama_chains_page", "https://defillama.com/chains"),
    ("coingecko_site", "https://www.coingecko.com/en/coins/tether"),
    ("coinmarketcap_btc", "https://coinmarketcap.com/currencies/bitcoin/"),
    ("certik_home", "https://www.certik.com/"),
    ("skynet_peer_leaderboard", "https://www.certik.com/products/skynet"),
    ("dune_home", "https://dune.com/browse/dashboards"),
    ("tokenterminal", "https://tokenterminal.com/"),
    ("nansen_home", "https://www.nansen.ai/"),
    ("arkham", "https://platform.arkhamintelligence.com/"),
    ("etherscan_usdt", "https://etherscan.io/token/0xdac17f958d2ee523a2206206994597c13d831ec7"),
    ("bscscan_home", "https://bscscan.com/"),
    ("polygonscan", "https://polygonscan.com/"),
    ("opensea_explore", "https://opensea.io/"),
    ("blur_io", "https://blur.io/"),
    ("rarible", "https://rarible.com/"),
    ("ssrn_home", "https://www.ssrn.com/"),
    ("nber_wp", "https://www.nber.org/papers"),
    ("imf_data", "https://data.imf.org/"),
    ("oecd_data", "https://data.oecd.org/"),
    ("bis_stats", "https://www.bis.org/statistics/index.htm"),
    ("twse_portal", "https://www.twse.com.tw/en/"),
    ("mops_portal", "https://mops.twse.com.tw/"),
    ("cnyes", "https://www.cnyes.com/"),
    ("yahoo_tw", "https://tw.stock.yahoo.com/"),
    ("investing_crypto", "https://www.investing.com/crypto/"),
    ("reuters_biz", "https://www.reuters.com/business/"),
    ("bloomberg_markets", "https://www.bloomberg.com/markets"),
    ("ft_markets", "https://www.ft.com/markets"),
    ("wsj_markets", "https://www.wsj.com/market-data"),
    ("github_explore", "https://github.com/explore"),
    ("huggingface_datasets", "https://huggingface.co/datasets"),
    ("kaggle_datasets", "https://www.kaggle.com/datasets"),
    ("data_gov", "https://catalog.data.gov/dataset"),
    ("eu_data", "https://data.europa.eu/data/datasets"),
    ("taiwan_data", "https://data.gov.tw/datasets"),
    ("sg_data", "https://data.gov.sg/"),
    ("hk_data", "https://data.gov.hk/en/"),
    ("worldbank_data", "https://data.worldbank.org/"),
    ("ourworldindata", "https://ourworldindata.org/grapher/bitcoin-price"),
]


def api(method: str, path: str, body: dict | None = None, timeout: int = 120) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {desk_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"error": raw[:400]}
        payload["_http_status"] = exc.code
        return payload


def main() -> None:
    assert len(URLS) >= 90, len(URLS)
    craft_rows: list[dict] = []
    by_type: Counter[str] = Counter()
    errors = 0
    forbidden_hits = 0

    print(f"CRAFT battery n={len(URLS)}")
    for name, url in URLS:
        t0 = time.time()
        out = api(
            "POST",
            "/library/craft/collect-plan",
            {
                "research_need": f"Land public research snapshot from {name} for desk flexibility test",
                "url": url,
                "title": f"Craft battery · {name}",
            },
            timeout=60,
        )
        ms = int((time.time() - t0) * 1000)
        plan = out.get("plan") if isinstance(out.get("plan"), dict) else {}
        jt = str(plan.get("job_type") or out.get("error") or "FAIL")
        if out.get("_http_status") or out.get("error") and not plan:
            errors += 1
            jt = "ERROR"
        if any(
            x in json.dumps(plan).lower()
            for x in ("skynet_stablecoin_harvest", "opensea_nft_metadata_layer", "ethereum_usdt_rpc")
        ):
            forbidden_hits += 1
        by_type[jt] += 1
        craft_rows.append(
            {
                "name": name,
                "url": url,
                "ms": ms,
                "job_type": plan.get("job_type"),
                "script_key": plan.get("script_key"),
                "pipeline": plan.get("pipeline"),
                "crafted": plan.get("crafted"),
                "dataset_id": plan.get("dataset_id"),
                "error": out.get("error") or out.get("detail"),
                "http": out.get("_http_status"),
            }
        )
        print(f"  {name:24s} {jt:14s} {ms:4d}ms")

    # Land a safe subset: http_manifest only, cap 12, skip keys that need API keys / likely 401
    skip_substrings = ("api_key=", "stlouisfed", "etherscan.io/api", "messari", "nasa.gov")
    land_candidates = [
        r
        for r in craft_rows
        if r.get("job_type") == "http_manifest"
        and r.get("pipeline") == "custom"
        and not any(s in (r.get("url") or "") for s in skip_substrings)
    ][:12]

    land_jobs: list[dict] = []
    print(f"\nLAND subset n={len(land_candidates)}")
    for r in land_candidates:
        plan_body = api(
            "POST",
            "/library/craft/collect-plan",
            {
                "research_need": f"Flexibility land · {r['name']}",
                "url": r["url"],
                "title": f"Craft land · {r['name']}",
            },
        ).get("plan") or {}
        # stamp unique dataset id for this run
        plan_body["dataset_id"] = f"craft_flex_{r['name']}_{int(time.time())}"
        plan_body["destination"] = f"data_lake/procured/{plan_body['dataset_id']}"
        submitted = api(
            "POST",
            "/library/jobs",
            {
                "title": plan_body.get("title") or r["name"],
                "plan": plan_body,
                "request": {"source": "craft_flexibility_battery", "peer_of": "skynet_style_target"},
                "auto_approve": True,
            },
            timeout=90,
        )
        job = submitted.get("job") or submitted
        land_jobs.append(
            {
                "name": r["name"],
                "job_id": job.get("id"),
                "status": job.get("status"),
                "error": job.get("error") or submitted.get("error"),
            }
        )
        print(f"  submit {r['name']}: {job.get('id')} {job.get('status')}")

    # Poll lands
    terminal = {"completed", "failed", "cancelled"}
    for _ in range(90):
        pending = [j for j in land_jobs if j.get("status") not in terminal and j.get("job_id")]
        if not pending:
            break
        time.sleep(3)
        for j in pending:
            got = api("GET", f"/library/jobs/{j['job_id']}", timeout=60)
            j["status"] = got.get("status")
            j["error"] = (got.get("error") or "")[:200]
            ev = (got.get("result") or {}).get("registration_evidence") or {}
            j["readiness"] = ev.get("readiness")
            j["usable_query"] = None

    # Query completed
    for j in land_jobs:
        if j.get("status") != "completed":
            continue
        # dataset_id from job result if present
        got = api("GET", f"/library/jobs/{j['job_id']}", timeout=60)
        did = ((got.get("result") or {}).get("dataset_id") or (got.get("plan") or {}).get("dataset_id") or "")
        j["dataset_id"] = did
        if not did:
            continue
        try:
            q = api("GET", f"/query/{did}?limit=1", timeout=60)
            j["usable_query"] = bool(q.get("rows") is not None and q.get("error") is None)
            j["query_returned"] = (q.get("meta") or {}).get("returned")
        except Exception as exc:  # noqa: BLE001
            j["usable_query"] = False
            j["query_error"] = str(exc)[:200]

    # Composer Ask smoke — peer of Skynet (DeFiLlama stablecoins), expect craft tool use
    print("\nCOMPOSER smoke…")
    chat = api(
        "POST",
        "/library/chat",
        {
            "message": (
                "I need public stablecoin TVL / peg research data from DefiLlama "
                "(https://stablecoins.llama.fi/stablecoins?includePrices=true). "
                "Do NOT use any named Skynet/OpenSea/USDT product module. "
                "Use research_craft_collect_plan then yzu_submit_job with a generic plan only. "
                "Submit pending (do not approve)."
            ),
            "session_id": f"craft_flex_composer_{int(time.time())}",
            "email": "drkong@saturn.yzu.edu.tw",
        },
        timeout=300,
    )
    reply = str(chat.get("reply") or chat.get("message") or "")[:500]
    action = chat.get("action_result") or chat.get("plan") or {}
    composer_summary = {
        "ok": not bool(chat.get("error")),
        "brain": (action.get("brain") if isinstance(action, dict) else None) or chat.get("brain"),
        "reply_head": reply,
        "action_keys": list(action)[:20] if isinstance(action, dict) else type(action).__name__,
        "pending_job_id": (action.get("state_patch") or {}).get("pending_job_id")
        if isinstance(action, dict)
        else None,
        "tool_name": chat.get("tool_name"),
        "raw_error": chat.get("error") or (action.get("error") if isinstance(action, dict) else None),
    }
    print("COMPOSER", json.dumps(composer_summary, indent=2)[:800])

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "url_count": len(URLS),
        "craft_histogram": dict(by_type),
        "craft_errors": errors,
        "forbidden_product_hits": forbidden_hits,
        "land_submitted": len(land_jobs),
        "land_completed": sum(1 for j in land_jobs if j.get("status") == "completed"),
        "land_failed": sum(1 for j in land_jobs if j.get("status") == "failed"),
        "land_query_usable": sum(1 for j in land_jobs if j.get("usable_query")),
        "craft_rows": craft_rows,
        "land_jobs": land_jobs,
        "composer": composer_summary,
        "chat_keys": list(chat)[:30] if isinstance(chat, dict) else None,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print("\nSUMMARY", json.dumps({k: report[k] for k in report if k not in {"craft_rows", "land_jobs", "composer", "chat_keys"}}, indent=2))
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
