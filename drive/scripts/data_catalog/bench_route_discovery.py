#!/usr/bin/env python3
"""Reproducible route-discovery benchmark: does a research need reach a usable route?

Quoting a figure in a comment goes stale the moment the code improves — three call sites
carried "6 of 13" after the number had moved. This is the committed measurement instead.
Each need lists every route that could legitimately supply it; any of them counts.

    python -m scripts.data_catalog.bench_route_discovery [--json]

Needs RESEARCH_DATA_ROOTS and the registry, like every holdings measurement here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# A need, and the routes that could honestly answer it. Multiple accepted; order-free.
NEEDS: tuple[tuple[str, frozenset[str]], ...] = (
    ("US equity daily prices with delisting-adjusted returns", frozenset({"crsp_moveit", "wrds_crsp_compustat"})),
    ("company fundamentals for North American listed firms", frozenset({"capital_iq_compustat", "wrds_crsp_compustat"})),
    ("full text of SEC corporate filings", frozenset({"sec_edgar"})),
    ("Taiwan listed company official disclosures", frozenset({"twse_official", "mops_taiwan"})),
    ("global news coverage by country and event type", frozenset({"gdelt"})),
    ("academic paper metadata and citation graph", frozenset({"openalex", "open_research_catalogs"})),
    ("published research datasets with DOIs", frozenset({"zenodo", "datacite_harvest", "datacite_procured", "open_research_catalogs"})),
    ("machine learning benchmark datasets", frozenset({"huggingface"})),
    ("US patent grants and citations", frozenset({"bigquery_public"})),
    ("cryptocurrency token prices and market caps", frozenset({"coingecko"})),
    ("Reddit discussion threads for sentiment analysis", frozenset({"reddit_social"})),
    ("Fama-French factor return series", frozenset({"public_macro"})),
    ("US options implied volatility and short interest", frozenset({"lseg_desktop_rescue", "lseg_edp"})),
)


def _routes(gateway: Any, need: str, k: int) -> list[str]:
    out: list[str] = []
    result = gateway.discover_source_search(need, limit=k)
    for row in (result.get("results") or []):
        sid = str(row.get("source_id") or row.get("id") or "")
        if sid and sid not in out:
            out.append(sid)
    for section in (result.get("sections") or []):
        for row in (section.get("rows") or []):
            sid = str(row.get("source_id") or row.get("id") or "")
            if sid and sid not in out:
                out.append(sid)
    return out[:k]


def run(repo_root: Path | str = ".", *, k: int = 5) -> dict[str, Any]:
    from scripts.research_data_mcp.bootstrap import create_stack

    root = Path(repo_root).resolve()
    gateway = create_stack(registry_path=str(root / "drive/config/research_query_registry.json")).gateway
    rows: list[dict[str, Any]] = []
    for need, accepted in NEEDS:
        got = _routes(gateway, need, k)
        rank = next((i for i, sid in enumerate(got, 1) if sid in accepted), 0)
        rows.append({"need": need, "accepted": sorted(accepted), "returned": got, "rank": rank})
    n = len(rows)
    at = lambda d: sum(1 for r in rows if 1 <= r["rank"] <= d)  # noqa: E731
    return {
        "needs": n,
        "rank1": at(1),
        "top3": at(3),
        "top5": at(5),
        "missed": sum(1 for r in rows if r["rank"] == 0),
        "results": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    report = run(args.repo_root)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    n = report["needs"]
    for r in report["results"]:
        mark = f"#{r['rank']}" if r["rank"] else "MISS"
        print(f"  {r['need'][:52]:<54}{mark:<6}{', '.join(r['returned'][:3])}")
    print(f"\n  rank1 {report['rank1']}/{n}  top3 {report['top3']}/{n}  "
          f"top5 {report['top5']}/{n}  missed {report['missed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
