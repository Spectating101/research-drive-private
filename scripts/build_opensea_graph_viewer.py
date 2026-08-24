#!/usr/bin/env python3
"""Build a static OpenSea graph dashboard from the metadata sidecar package."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


COLLECTION_CONTEXT = {
    "opensea_zip_azuki": {"category": "PFP", "assets": ["ETH"]},
    "opensea_zip_bayc": {"category": "PFP", "assets": ["ETH", "APE"]},
    "opensea_zip_clone_x": {"category": "PFP / fashion", "assets": ["ETH"]},
    "opensea_zip_cool_cats": {"category": "PFP", "assets": ["ETH"]},
    "opensea_zip_cryptopunks": {"category": "PFP / historical", "assets": ["ETH"]},
    "opensea_zip_cryptoskulls": {"category": "PFP / historical", "assets": ["ETH"]},
    "opensea_zip_doodles": {"category": "PFP", "assets": ["ETH"]},
    "opensea_zip_mayc": {"category": "PFP", "assets": ["ETH", "APE"]},
    "opensea_zip_meebits": {"category": "3D avatar", "assets": ["ETH"]},
    "opensea_zip_moonbirds": {"category": "PFP", "assets": ["ETH"]},
    "opensea_zip_mooncats": {"category": "PFP / historical", "assets": ["ETH"]},
    "opensea_zip_pudgy_penguins": {"category": "PFP / consumer brand", "assets": ["ETH", "PENGU"]},
    "opensea_zip_supducks": {"category": "PFP", "assets": ["ETH"]},
    "opensea_zip_world_of_women": {"category": "PFP / art", "assets": ["ETH"]},
}

COLLECTION_COLORS = [
    "#2d7dd2",
    "#d95d39",
    "#3f8f68",
    "#7f5af0",
    "#bb3e7a",
    "#c98a1a",
    "#2a9d8f",
    "#91684a",
    "#4056a1",
    "#bf4e30",
    "#138a72",
    "#8a5a99",
    "#5c7c2f",
    "#ad5d92",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", default="deliverables/opensea_metadata_full_package_20260518")
    parser.add_argument("--out-dir", default="deliverables/opensea_graph_viewer_20260518")
    parser.add_argument("--top-trait-types", type=int, default=6)
    parser.add_argument("--top-values", type=int, default=4)
    parser.add_argument("--sample-tokens", type=int, default=8)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def safe_id(*parts: Any) -> str:
    text = "::".join(str(part).strip() for part in parts)
    return "".join(ch if ch.isalnum() or ch in "-_:.#" else "_" for ch in text)


def fmt_label(public_folder: str) -> str:
    return (
        public_folder.removeprefix("opensea_zip_")
        .replace("_", " ")
        .replace("bayc", "BAYC")
        .replace("mayc", "MAYC")
        .title()
        .replace("Bayc", "BAYC")
        .replace("Mayc", "MAYC")
    )


def main() -> int:
    args = parse_args()
    package_root = Path(args.package_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "assets").mkdir(exist_ok=True)

    summary_rows = read_csv(package_root / "collection_metadata_summary.csv")
    trait_rows = read_csv(package_root / "map" / "trait_summary.csv")

    summary_by_collection = {row["public_folder"]: row for row in summary_rows}
    trait_counts: dict[str, Counter[str]] = defaultdict(Counter)
    trait_values: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    trait_presence: dict[str, set[str]] = defaultdict(set)

    for row in trait_rows:
        public_folder = row["public_folder"]
        trait_type = row["trait_type"].strip() or "Unlabeled"
        value = row["value"].strip() or "Unlabeled"
        count = int(row["count"] or 0)
        trait_counts[public_folder][trait_type] += count
        trait_values[(public_folder, trait_type)][value] += count
        trait_presence[trait_type].add(public_folder)

    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    token_index = package_root / "token_metadata_index.csv"
    if token_index.exists():
        with token_index.open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                public_folder = row["public_folder"]
                if row.get("status") == "error" or len(samples[public_folder]) >= args.sample_tokens:
                    continue
                samples[public_folder].append(
                    {
                        "tokenId": row["token_id"],
                        "name": row.get("name") or f"Token {row['token_id']}",
                        "attributes": int(row.get("attribute_count") or 0),
                        "status": row.get("status", ""),
                    }
                )

    collections: list[dict[str, Any]] = []
    for idx, row in enumerate(summary_rows):
        public_folder = row["public_folder"]
        attempted = int(row["attempted"] or 0)
        ok = int(row["ok"] or 0)
        existing = int(row["existing"] or 0)
        errors = int(row["error"] or 0)
        covered = ok + existing
        context = COLLECTION_CONTEXT.get(public_folder, {"category": "PFP", "assets": ["ETH"]})
        collections.append(
            {
                "id": public_folder,
                "name": row["collection"],
                "slug": row["slug"],
                "attempted": attempted,
                "covered": covered,
                "errors": errors,
                "coverage": round(covered / attempted, 4) if attempted else 0,
                "traitRows": int(row["trait_rows"] or 0),
                "category": context["category"],
                "assets": context["assets"],
                "color": COLLECTION_COLORS[idx % len(COLLECTION_COLORS)],
                "topTraitTypes": [
                    {"traitType": trait_type, "count": count}
                    for trait_type, count in trait_counts[public_folder].most_common(args.top_trait_types)
                ],
                "topValues": {
                    trait_type: [
                        {"value": value, "count": count}
                        for value, count in trait_values[(public_folder, trait_type)].most_common(args.top_values)
                    ]
                    for trait_type, _count in trait_counts[public_folder].most_common(args.top_trait_types)
                },
                "sampleTokens": samples.get(public_folder, []),
            }
        )

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def add_node(node: dict[str, Any]) -> None:
        nodes.append(node)

    def add_edge(source: str, target: str, relation: str, weight: float = 1.0) -> None:
        edges.append({"source": source, "target": target, "relation": relation, "weight": weight})

    add_node({"id": "chain:Ethereum", "label": "Ethereum", "type": "chain", "x": 0, "y": 0, "radius": 26})
    category_labels = sorted({c["category"] for c in collections})
    asset_labels = sorted({asset for c in collections for asset in c["assets"]})
    for idx, category in enumerate(category_labels):
        angle = -math.pi / 2 + idx * (2 * math.pi / max(1, len(category_labels)))
        node_id = safe_id("category", category)
        add_node(
            {
                "id": node_id,
                "label": category,
                "type": "category",
                "x": math.cos(angle) * 115,
                "y": math.sin(angle) * 115,
                "radius": 15,
            }
        )
        add_edge("chain:Ethereum", node_id, "contains category", 1.6)

    for idx, asset in enumerate(asset_labels):
        angle = math.pi / 2 + idx * (2 * math.pi / max(1, len(asset_labels)))
        node_id = f"asset:{asset}"
        add_node(
            {
                "id": node_id,
                "label": asset,
                "type": "asset",
                "x": math.cos(angle) * 175,
                "y": math.sin(angle) * 175,
                "radius": 16,
            }
        )
        add_edge("chain:Ethereum", node_id, "related asset", 1.25)

    for idx, collection in enumerate(collections):
        angle = -math.pi / 2 + idx * (2 * math.pi / len(collections))
        collection_x = math.cos(angle) * 305
        collection_y = math.sin(angle) * 305
        collection_id = f"collection:{collection['id']}"
        add_node(
            {
                "id": collection_id,
                "label": collection["name"],
                "type": "collection",
                "collection": collection["id"],
                "x": collection_x,
                "y": collection_y,
                "radius": 18 + min(10, math.sqrt(collection["covered"]) / 22),
                "coverage": collection["coverage"],
                "color": collection["color"],
            }
        )
        add_edge(safe_id("category", collection["category"]), collection_id, "has collection", 2.2)
        for asset in collection["assets"]:
            add_edge(collection_id, f"asset:{asset}", "asset exposure", 1.1)

        top_traits = collection["topTraitTypes"]
        for trait_idx, trait in enumerate(top_traits):
            offset = 0 if len(top_traits) == 1 else (trait_idx / (len(top_traits) - 1) - 0.5)
            trait_angle = angle + offset * 1.05
            trait_x = collection_x + math.cos(trait_angle) * 105
            trait_y = collection_y + math.sin(trait_angle) * 105
            trait_id = safe_id("trait_type", collection["id"], trait["traitType"])
            add_node(
                {
                    "id": trait_id,
                    "label": trait["traitType"],
                    "type": "traitType",
                    "collection": collection["id"],
                    "traitType": trait["traitType"],
                    "x": trait_x,
                    "y": trait_y,
                    "radius": 10 + min(8, math.sqrt(trait["count"]) / 70),
                    "count": trait["count"],
                    "color": collection["color"],
                }
            )
            add_edge(collection_id, trait_id, "has trait type", 1.0 + min(2.0, trait["count"] / max(1, collection["traitRows"]) * 14))

            values = collection["topValues"].get(trait["traitType"], [])
            for value_idx, value in enumerate(values):
                value_offset = 0 if len(values) == 1 else (value_idx / (len(values) - 1) - 0.5)
                value_angle = trait_angle + value_offset * 0.55
                value_id = safe_id("trait_value", collection["id"], trait["traitType"], value["value"])
                add_node(
                    {
                        "id": value_id,
                        "label": value["value"],
                        "type": "traitValue",
                        "collection": collection["id"],
                        "traitType": trait["traitType"],
                        "x": trait_x + math.cos(value_angle) * 55,
                        "y": trait_y + math.sin(value_angle) * 55,
                        "radius": 6 + min(7, math.sqrt(value["count"]) / 22),
                        "count": value["count"],
                        "color": collection["color"],
                    }
                )
                add_edge(trait_id, value_id, "has value", 0.7 + min(2.4, value["count"] / max(1, trait["count"]) * 8))

    shared_traits = [
        {"traitType": trait_type, "collections": len(collection_set), "collectionIds": sorted(collection_set)}
        for trait_type, collection_set in trait_presence.items()
        if len(collection_set) >= 3
    ]
    shared_traits.sort(key=lambda row: (-row["collections"], row["traitType"]))

    dashboard = {
        "generatedFrom": str(package_root),
        "collections": collections,
        "graph": {"nodes": nodes, "edges": edges},
        "sharedTraits": shared_traits[:40],
        "summary": {
            "collectionCount": len(collections),
            "tokenRows": sum(c["attempted"] for c in collections),
            "coveredRows": sum(c["covered"] for c in collections),
            "errorRows": sum(c["errors"] for c in collections),
            "traitRows": sum(c["traitRows"] for c in collections),
            "graphNodes": len(nodes),
            "graphEdges": len(edges),
        },
    }

    data_js = "window.OPENSEA_GRAPH_DATA = " + json.dumps(dashboard, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (out_dir / "data.js").write_text(data_js, encoding="utf-8")

    readme = [
        "# OpenSea Graph Viewer",
        "",
        "Static graph dashboard generated from the OpenSea metadata full package.",
        "",
        "Open `index.html` directly in a browser, or serve the folder with a simple HTTP server.",
        "",
        "The graph intentionally renders an interpretable reduced view: collections, category/asset links, top trait types, and top trait values.",
    ]
    (out_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(f"wrote {out_dir} nodes={len(nodes)} edges={len(edges)} collections={len(collections)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
