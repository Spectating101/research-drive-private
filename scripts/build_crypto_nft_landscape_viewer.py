#!/usr/bin/env python3
"""Build a static chain-level crypto/NFT map from local OpenSea and Coingecko data."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CHAIN_CONTEXT = [
    {
        "id": "bitcoin",
        "chain": "Bitcoin / Ordinals",
        "coin_id": "bitcoin",
        "symbol": "BTC",
        "role": "reference base asset",
        "x": -76,
        "y": 38,
        "color": "#d08a24",
        "note": "Included as a market-cap reference; no OpenSea collections in this package are mapped to Bitcoin.",
    },
    {
        "id": "ethereum",
        "chain": "Ethereum",
        "coin_id": "ethereum",
        "symbol": "ETH",
        "role": "primary NFT base chain",
        "x": 0,
        "y": 0,
        "color": "#5266d6",
        "note": "All current OpenSea collection metadata in this package maps to Ethereum.",
    },
    {
        "id": "solana",
        "chain": "Solana",
        "coin_id": "solana",
        "symbol": "SOL",
        "role": "NFT-capable L1",
        "x": 76,
        "y": 36,
        "color": "#1f9f86",
    },
    {
        "id": "bnb",
        "chain": "BNB Chain",
        "coin_id": "binancecoin",
        "symbol": "BNB",
        "role": "NFT-capable L1",
        "x": 76,
        "y": -28,
        "color": "#b6871d",
    },
    {
        "id": "polygon",
        "chain": "Polygon",
        "coin_id": "polygon-ecosystem-token",
        "symbol": "POL",
        "role": "NFT-capable scaling chain",
        "x": 95,
        "y": 3,
        "color": "#7a4cc2",
    },
    {
        "id": "avalanche",
        "chain": "Avalanche",
        "coin_id": "avalanche-2",
        "symbol": "AVAX",
        "role": "NFT-capable L1",
        "x": 42,
        "y": -61,
        "color": "#c44836",
    },
    {
        "id": "cardano",
        "chain": "Cardano",
        "coin_id": "cardano",
        "symbol": "ADA",
        "role": "NFT-capable L1",
        "x": -62,
        "y": -45,
        "color": "#236caa",
    },
    {
        "id": "flow",
        "chain": "Flow",
        "coin_id": "flow",
        "symbol": "FLOW",
        "role": "NFT-specific L1",
        "x": -96,
        "y": -8,
        "color": "#24956e",
    },
    {
        "id": "immutable",
        "chain": "Immutable",
        "coin_id": "immutable-x",
        "symbol": "IMX",
        "role": "NFT / gaming scaling chain",
        "x": -10,
        "y": -67,
        "color": "#2f6f95",
    },
    {
        "id": "arbitrum",
        "chain": "Arbitrum",
        "coin_id": "arbitrum",
        "symbol": "ARB",
        "role": "Ethereum L2",
        "x": 16,
        "y": 66,
        "color": "#3a7cbf",
    },
    {
        "id": "optimism",
        "chain": "Optimism",
        "coin_id": "optimism",
        "symbol": "OP",
        "role": "Ethereum L2",
        "x": 57,
        "y": 64,
        "color": "#c83b32",
    },
    {
        "id": "base",
        "chain": "Base",
        "coin_id": "base",
        "symbol": "BASE",
        "role": "Ethereum L2",
        "x": -83,
        "y": 18,
        "color": "#2467d6",
        "note": "Base does not have a normal native market-cap series in this local Coingecko snapshot.",
    },
]


COLLECTION_CONTEXT = {
    "opensea_zip_azuki": {
        "label": "Azuki",
        "category": "PFP / anime",
        "chain_id": "ethereum",
        "related_assets": ["ETH"],
        "x": 23,
        "y": -24,
    },
    "opensea_zip_bayc": {
        "label": "BAYC",
        "category": "PFP / IP",
        "chain_id": "ethereum",
        "related_assets": ["ETH", "APE"],
        "x": 13,
        "y": 30,
    },
    "opensea_zip_clone_x": {
        "label": "CLONE X",
        "category": "Avatar / fashion",
        "chain_id": "ethereum",
        "related_assets": ["ETH"],
        "x": -25,
        "y": -24,
    },
    "opensea_zip_cool_cats": {
        "label": "Cool Cats",
        "category": "PFP / character brand",
        "chain_id": "ethereum",
        "related_assets": ["ETH"],
        "x": 46,
        "y": -16,
    },
    "opensea_zip_cryptopunks": {
        "label": "CryptoPunks",
        "category": "PFP / historical",
        "chain_id": "ethereum",
        "related_assets": ["ETH"],
        "x": -20,
        "y": 28,
    },
    "opensea_zip_cryptoskulls": {
        "label": "CryptoSkulls",
        "category": "PFP / historical",
        "chain_id": "ethereum",
        "related_assets": ["ETH"],
        "x": -48,
        "y": 4,
    },
    "opensea_zip_doodles": {
        "label": "Doodles",
        "category": "PFP / character brand",
        "chain_id": "ethereum",
        "related_assets": ["ETH"],
        "x": 5,
        "y": -36,
    },
    "opensea_zip_mayc": {
        "label": "MAYC",
        "category": "PFP / IP",
        "chain_id": "ethereum",
        "related_assets": ["ETH", "APE"],
        "x": 29,
        "y": 17,
    },
    "opensea_zip_meebits": {
        "label": "Meebits",
        "category": "3D avatar",
        "chain_id": "ethereum",
        "related_assets": ["ETH"],
        "x": -34,
        "y": -4,
    },
    "opensea_zip_moonbirds": {
        "label": "Moonbirds",
        "category": "PFP",
        "chain_id": "ethereum",
        "related_assets": ["ETH"],
        "x": -10,
        "y": -38,
    },
    "opensea_zip_mooncats": {
        "label": "MoonCats",
        "category": "PFP / historical",
        "chain_id": "ethereum",
        "related_assets": ["ETH"],
        "x": -39,
        "y": 16,
    },
    "opensea_zip_pudgy_penguins": {
        "label": "Pudgy Penguins",
        "category": "PFP / consumer brand",
        "chain_id": "ethereum",
        "related_assets": ["ETH", "PENGU"],
        "x": 36,
        "y": 0,
    },
    "opensea_zip_supducks": {
        "label": "SupDucks",
        "category": "PFP",
        "chain_id": "ethereum",
        "related_assets": ["ETH"],
        "x": 47,
        "y": 20,
    },
    "opensea_zip_world_of_women": {
        "label": "World of Women",
        "category": "PFP / art",
        "chain_id": "ethereum",
        "related_assets": ["ETH"],
        "x": -45,
        "y": -20,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opensea-package", default="deliverables/opensea_metadata_full_package_20260518")
    parser.add_argument("--coingecko-db", default="data_lake/coingecko_archive/coingecko_full_active_2009.sqlite3")
    parser.add_argument("--out-dir", default="deliverables/crypto_nft_landscape_viewer_20260518")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def latest_market(con: sqlite3.Connection, coin_id: str) -> dict[str, Any]:
    row = con.execute(
        """
        select c.symbol, c.name, m.market_cap_rank, m.current_price, m.market_cap,
               m.total_volume, m.retrieved_at
        from coin_markets m
        left join coins c on c.id = m.coin_id
        where m.coin_id = ?
        order by m.retrieved_at desc
        limit 1
        """,
        (coin_id,),
    ).fetchone()
    if row:
        return {
            "coinId": coin_id,
            "symbol": row[0] or coin_id,
            "name": row[1] or coin_id,
            "rank": row[2],
            "price": row[3],
            "marketCap": row[4] if row[4] and row[4] > 0 else None,
            "volume": row[5],
            "retrievedAt": row[6],
        }
    meta = con.execute("select symbol, name, status, retrieved_at from coins where id = ?", (coin_id,)).fetchone()
    if meta:
        return {
            "coinId": coin_id,
            "symbol": meta[0],
            "name": meta[1],
            "rank": None,
            "price": None,
            "marketCap": None,
            "volume": None,
            "retrievedAt": meta[3],
        }
    return {
        "coinId": coin_id,
        "symbol": coin_id,
        "name": coin_id,
        "rank": None,
        "price": None,
        "marketCap": None,
        "volume": None,
        "retrievedAt": None,
    }


def history_span(con: sqlite3.Connection, coin_id: str) -> dict[str, Any]:
    rows = con.execute(
        """
        select min(ts_ms), max(ts_ms), count(*)
        from coin_history
        where coin_id = ? and price is not null and price > 0
        """,
        (coin_id,),
    ).fetchone()
    if not rows or not rows[0]:
        return {"historyStart": None, "historyEnd": None, "historyRows": 0}
    start = datetime.fromtimestamp(rows[0] / 1000, tz=timezone.utc).date().isoformat()
    end = datetime.fromtimestamp(rows[1] / 1000, tz=timezone.utc).date().isoformat()
    return {"historyStart": start, "historyEnd": end, "historyRows": rows[2]}


def compact_label(folder: str, fallback: str) -> str:
    context = COLLECTION_CONTEXT.get(folder, {})
    return context.get("label") or fallback


def main() -> int:
    args = parse_args()
    opensea_package = Path(args.opensea_package).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    collection_rows = read_csv(opensea_package / "collection_metadata_summary.csv")
    trait_summary_rows = read_csv(opensea_package / "map" / "trait_summary.csv")

    trait_types_by_collection: dict[str, set[str]] = defaultdict(set)
    top_traits_by_collection: dict[str, Counter[str]] = defaultdict(Counter)
    for row in trait_summary_rows:
        folder = row.get("public_folder", "")
        trait_type = row.get("trait_type", "").strip()
        value = row.get("value", "").strip()
        count = int(float(row.get("count") or 0))
        if trait_type:
            trait_types_by_collection[folder].add(trait_type)
        if trait_type and value:
            top_traits_by_collection[folder][f"{trait_type}: {value}"] += count

    collections: list[dict[str, Any]] = []
    for row in collection_rows:
        folder = row["public_folder"]
        context = COLLECTION_CONTEXT.get(
            folder,
            {
                "label": row.get("collection") or folder,
                "category": "NFT collection",
                "chain_id": "ethereum",
                "related_assets": ["ETH"],
                "x": 0,
                "y": 0,
            },
        )
        attempted = int(float(row.get("attempted") or 0))
        covered = int(float(row.get("ok") or 0)) + int(float(row.get("existing") or 0))
        errors = int(float(row.get("error") or 0))
        trait_rows = int(float(row.get("trait_rows") or 0))
        collections.append(
            {
                "id": folder,
                "label": compact_label(folder, row.get("collection", folder)),
                "collection": row.get("collection", ""),
                "slug": row.get("slug", ""),
                "category": context["category"],
                "chainId": context["chain_id"],
                "relatedAssets": context["related_assets"],
                "x": context["x"],
                "y": context["y"],
                "attempted": attempted,
                "covered": covered,
                "errors": errors,
                "coverage": round(covered / attempted, 4) if attempted else 0,
                "traitRows": trait_rows,
                "traitTypes": len(trait_types_by_collection.get(folder, set())),
                "traitsPerToken": round(trait_rows / covered, 2) if covered else 0,
                "topTraits": [
                    {"trait": trait, "count": count}
                    for trait, count in top_traits_by_collection.get(folder, Counter()).most_common(5)
                ],
            }
        )

    collections.sort(key=lambda item: item["label"].lower())
    collection_by_chain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for collection in collections:
        collection_by_chain[collection["chainId"]].append(collection)

    con = sqlite3.connect(args.coingecko_db)
    market_by_coin = {ctx["coin_id"]: latest_market(con, ctx["coin_id"]) for ctx in CHAIN_CONTEXT}
    span_by_coin = {ctx["coin_id"]: history_span(con, ctx["coin_id"]) for ctx in CHAIN_CONTEXT}

    max_market_cap = max((stats.get("marketCap") or 0 for stats in market_by_coin.values()), default=1) or 1
    max_collection_tokens = max((collection["covered"] for collection in collections), default=1) or 1

    chains: list[dict[str, Any]] = []
    for ctx in CHAIN_CONTEXT:
        stats = market_by_coin[ctx["coin_id"]]
        chain_collections = collection_by_chain.get(ctx["id"], [])
        covered = sum(collection["covered"] for collection in chain_collections)
        attempted = sum(collection["attempted"] for collection in chain_collections)
        trait_rows = sum(collection["traitRows"] for collection in chain_collections)
        market_cap = stats.get("marketCap") or 0
        radius = 6 + 12 * math.sqrt(market_cap / max_market_cap) if market_cap else 5.5
        if chain_collections:
            radius = max(radius, 17)
        chains.append(
            {
                "id": ctx["id"],
                "name": ctx["chain"],
                "symbol": ctx["symbol"],
                "coinId": ctx["coin_id"],
                "role": ctx["role"],
                "x": ctx["x"],
                "y": ctx["y"],
                "radius": round(radius, 2),
                "color": ctx["color"],
                "note": ctx.get("note", ""),
                "market": {**stats, **span_by_coin[ctx["coin_id"]]},
                "projectCount": len(chain_collections),
                "collectionIds": [collection["id"] for collection in chain_collections],
                "attemptedTokens": attempted,
                "coveredTokens": covered,
                "errorTokens": attempted - covered,
                "traitRows": trait_rows,
            }
        )

    collection_radius = {
        collection["id"]: round(3.2 + 4.6 * math.sqrt(collection["covered"] / max_collection_tokens), 2)
        for collection in collections
    }
    for collection in collections:
        collection["radius"] = collection_radius[collection["id"]]

    chain_count_with_collections = sum(1 for chain in chains if chain["projectCount"])
    ethereum = next((chain for chain in chains if chain["id"] == "ethereum"), None)
    latest_market_snapshot = max(
        (chain["market"].get("retrievedAt") for chain in chains if chain["market"].get("retrievedAt")),
        default=None,
    )

    dashboard = {
        "generatedFrom": {
            "openseaPackage": str(opensea_package),
            "coingeckoDb": str(Path(args.coingecko_db).resolve()),
            "marketSnapshot": latest_market_snapshot,
        },
        "summary": {
            "chains": len(chains),
            "chainsWithNftData": chain_count_with_collections,
            "nftCollections": len(collections),
            "nftTokensAttempted": sum(collection["attempted"] for collection in collections),
            "nftTokensCovered": sum(collection["covered"] for collection in collections),
            "nftTraitRows": sum(collection["traitRows"] for collection in collections),
            "ethereumProjectCount": ethereum["projectCount"] if ethereum else 0,
            "ethereumMarketCap": ethereum["market"].get("marketCap") if ethereum else None,
        },
        "chains": chains,
        "collections": collections,
        "edges": [
            {"source": collection["chainId"], "target": collection["id"], "relation": "deployed_on"}
            for collection in collections
        ],
        "notes": [
            "This viewer maps NFT collections to their base crypto/network, not to semantic sectors.",
            "The current OpenSea sidecar package is Ethereum-only: every covered collection is mapped to Ethereum.",
            "Other chains are Coingecko market-cap placeholders with zero NFT projects in this local package; they are not claims about the global NFT market.",
        ],
    }

    (out_dir / "data.js").write_text(
        "window.CRYPTO_NFT_CHAIN_MAP_DATA = "
        + json.dumps(dashboard, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    (out_dir / "README.md").write_text(
        "# Crypto NFT Chain Map Viewer\n\n"
        "Static viewer mapping NFT collections to the base crypto/network they are built on. "
        "Current local OpenSea metadata coverage maps all bundled collections to Ethereum; other "
        "chains are shown from the local Coingecko market snapshot as uncovered comparison nodes.\n",
        encoding="utf-8",
    )
    print(
        f"wrote {out_dir} chains={len(chains)} collections={len(collections)} "
        f"chains_with_nfts={chain_count_with_collections}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
