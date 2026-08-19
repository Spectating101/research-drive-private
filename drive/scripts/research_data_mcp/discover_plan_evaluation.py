#!/usr/bin/env python3
"""Reproducible evaluation for model-directed public Discover plans.

This is intentionally measurement only.  The cases are evaluation fixtures,
not production source-selection rules: a model supplies the provider/query plan
for each need, while this module records what the live adapters returned and
what survived the researcher-facing relevance gate.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable


DEFAULT_CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "patent_citations",
        "query": "US patent grants and citations",
        "query_plan": {
            "providers": ["huggingface", "datacite", "zenodo", "openalex"],
            "queries": ["uspto patent citations", "patent citations"],
        },
    },
    {
        "id": "taiwan_returns",
        "query": "daily returns for Taiwan listed companies",
        "query_plan": {
            "providers": ["huggingface", "zenodo", "openalex"],
            "queries": ["taiwan stock returns", "taiwan stock"],
        },
    },
    {
        "id": "carbon_emissions",
        "query": "country-level carbon emissions panel",
        "query_plan": {
            "providers": ["datacite", "zenodo", "openalex"],
            "queries": ["carbon emissions panel", "carbon emissions"],
        },
    },
)


def summarize_discover_response(case: dict[str, Any], response: dict[str, Any], elapsed_seconds: float) -> dict[str, Any]:
    """Separate adapter yield from researcher-visible output; never score relevance."""
    remote = dict(response.get("remote_search") or {})
    adapters = list(remote.get("adapters") or [])
    results = list(response.get("results") or [])
    return {
        "id": str(case.get("id") or case.get("query") or "case"),
        "query": str(case.get("query") or ""),
        "requested_plan": case.get("query_plan"),
        "executed_plan": remote.get("query_plan"),
        "elapsed_seconds": round(float(elapsed_seconds), 3),
        "adapter_count": len(adapters),
        "adapter_successes": sum(1 for adapter in adapters if adapter.get("ok")),
        "raw_external_hits": sum(int(adapter.get("returned") or 0) for adapter in adapters),
        "researcher_visible_total": len(results),
        "researcher_visible_live": sum(1 for row in results if row.get("live_hit")),
        "agent_review_candidates": len(list(response.get("agent_review_candidates") or [])),
        "all_agent_review_rows_have_query_provenance": all(
            bool(row.get("adapter_query")) for row in (response.get("agent_review_candidates") or [])
        ),
        "all_visible_live_rows_have_query_provenance": all(
            not row.get("live_hit") or bool(row.get("adapter_query")) for row in results
        ),
        "adapters": [
            {
                "adapter": adapter.get("adapter"),
                "ok": bool(adapter.get("ok")),
                "returned": int(adapter.get("returned") or 0),
                "queries_with_results": list(adapter.get("queries_with_results") or []),
                "error": adapter.get("error"),
            }
            for adapter in adapters
        ],
    }


def evaluate_cases(
    cases: list[dict[str, Any]],
    search: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Run caller-provided plans and return counts whose meanings cannot blur."""
    measurements: list[dict[str, Any]] = []
    for case in cases:
        query = str(case.get("query") or "").strip()
        if not query:
            continue
        started = time.monotonic()
        response = search(query=query, query_plan=case.get("query_plan"))
        measurements.append(summarize_discover_response(case, response, time.monotonic() - started))
    return {
        "case_count": len(measurements),
        "raw_external_hits": sum(item["raw_external_hits"] for item in measurements),
        "researcher_visible_total": sum(item["researcher_visible_total"] for item in measurements),
        "researcher_visible_live": sum(item["researcher_visible_live"] for item in measurements),
        "agent_review_candidates": sum(item["agent_review_candidates"] for item in measurements),
        "all_agent_review_rows_have_query_provenance": all(
            item["all_agent_review_rows_have_query_provenance"] for item in measurements
        ),
        "all_visible_live_rows_have_query_provenance": all(
            item["all_visible_live_rows_have_query_provenance"] for item in measurements
        ),
        "cases": measurements,
    }


def _load_cases(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return [dict(case) for case in DEFAULT_CASES]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(case, dict) for case in payload):
        raise ValueError("plans file must be a JSON list of {id, query, query_plan} objects")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure model-directed public Discover plans")
    parser.add_argument("--plans", type=Path, help="JSON list of {id, query, query_plan}; defaults to the small fixture set")
    parser.add_argument("--live", action="store_true", help="Allow outbound public-catalogue requests")
    parser.add_argument("--out", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required; this evaluator never makes network requests implicitly")

    from scripts.research_data_mcp.discover_source_search import search_discover_sources

    root = Path.cwd()
    report = evaluate_cases(
        _load_cases(args.plans),
        lambda *, query, query_plan: search_discover_sources(
            root,
            query,
            live=True,
            semantic=True,
            query_plan=query_plan,
        ),
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
