#!/usr/bin/env python3
"""What the desk can obtain, by capability, checked against what it can reach.

``databank_source_map.json`` is the procurement catalog: 25 sources, each
declaring capabilities, geographies, licence and known gaps. Until now it was
served only as raw JSON at ``/library/source-map``, so the question a researcher
actually asks -- "can this desk get me point-in-time index membership for
Taiwan?" -- had no surface that answered it.

That question is the competitive one. HuggingFace, Kaggle, Google Dataset Search
and WRDS can each tell you whether a dataset exists in their index. None can
tell you whether *your* institution can obtain it, under which licence, and what
is already sitting on the shelf.

The declaration alone is not trustworthy, though. ``bigquery_public`` is
declared ``live_connector`` with ``status: active``, and on this host the
connector cannot authenticate at all -- ``google.auth`` is not importable, so
every BigQuery capability the map advertises is currently unreachable. A
capability matrix that repeated the declaration would have quietly promised
patent data the desk cannot fetch.

So every source is graded against evidence:

* ``held`` -- registry datasets naming this source that a probe proved queryable
  (``materialization.query_ready``). The strongest signal, and the only one that
  cannot be satisfied by an assertion in a config file.
* ``declared_only`` -- datasets exist in the registry for this source but none
  are query-ready. A route, not a holding.
* ``connector_unavailable`` -- a live connector whose dependency or credential
  is missing. Declared active, cannot be reached.
* ``not_on_desk`` -- honestly out of reach (``planned``, WRDS).

The probes are deliberately offline: they check dependencies, credentials and
local roots, never the network. A matrix that took thirty seconds and a working
uplink to render would not be used, and a network timeout must not be able to
downgrade a licensed seat to "unreachable".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SOURCE_MAP_REL = "config/databank_source_map.json"
REGISTRY_REL = "config/research_query_registry.json"

# Access modes whose holdings live on disk rather than behind a live call.
_MATERIALISED = frozenset({
    "materialized_instant", "materialized_bulk", "derived_internal",
    "procurement_catalog", "catalog_reference",
})


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _connector_probe(source_id: str) -> tuple[bool, str]:
    """Whether a live connector could be used right now, and why not.

    Offline by design -- import and credential resolution only. ``status()``
    for BigQuery reports a missing dependency or absent ADC without a round
    trip, which is exactly the failure that matters here.
    """
    if source_id in {"bigquery_public", "ethereum_onchain"}:
        try:
            from scripts.research_data_mcp import bigquery_client

            state = bigquery_client.status()
        except Exception as exc:  # pragma: no cover - import guard
            return False, f"connector import failed: {exc}"
        if str(state.get("credentials")) != "available":
            return False, str(state.get("detail") or state.get("fix") or "credentials unavailable")
        return True, f"project {state.get('project')}"
    if source_id == "huggingface":
        try:
            from scripts.research_data_mcp import extension_clients  # noqa: F401
        except Exception:
            return True, "public HTTP API, no credential required"
        return True, "public HTTP API, no credential required"
    if source_id == "open_research_catalogs":
        return True, "public HTTP APIs (Zenodo, OpenAlex)"
    return True, "no credential requirement declared"


def source_evidence(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Grade each declared source against what the desk can actually reach."""
    root = Path(repo_root)
    sources = _load(root / SOURCE_MAP_REL).get("sources") or []
    rows = _load(root / REGISTRY_REL).get("datasets") or []

    held: dict[str, dict[str, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("source_id") or "")
        if not sid:
            continue
        mat = row.get("materialization") or {}
        bucket = held.setdefault(sid, {"datasets": 0, "query_ready": 0, "visible": 0})
        bucket["datasets"] += 1
        bucket["visible"] += 1 if row.get("professor_visible") else 0
        bucket["query_ready"] += 1 if mat.get("query_ready") else 0

    out: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        sid = str(source.get("id") or "")
        if not sid:
            continue
        mode = str(source.get("access_mode") or "")
        counts = held.get(sid) or {"datasets": 0, "query_ready": 0, "visible": 0}
        ready = int(counts["query_ready"])

        if mode == "planned":
            reach, detail = "not_on_desk", "declared unavailable on this desk"
        elif ready:
            reach, detail = "held", f"{ready} query-ready dataset(s)"
        elif mode == "live_connector":
            ok, why = _connector_probe(sid)
            reach = "connector_ready" if ok else "connector_unavailable"
            detail = why
        elif counts["datasets"]:
            reach, detail = "declared_only", f"{counts['datasets']} dataset(s) declared, none query-ready"
        elif mode in _MATERIALISED:
            reach, detail = "declared_only", "no registry dataset yet"
        else:
            reach, detail = "declared_only", "no evidence recorded"

        out[sid] = {
            "source_id": sid,
            "label": source.get("label"),
            "provider": source.get("provider"),
            "access_mode": mode,
            "license": source.get("license"),
            "status": source.get("status"),
            "capabilities": list(source.get("capabilities") or []),
            "geographies": list(source.get("geographies") or []),
            "known_gaps": list(source.get("known_gaps") or []),
            "partition_ids": list(source.get("partition_ids") or []),
            "datasets": int(counts["datasets"]),
            "query_ready_datasets": ready,
            "reachability": reach,
            "reachability_detail": detail,
            # Only a held or connector-ready source can be acted on now. The
            # rest are requests, and the button must say so.
            "actionable": reach in {"held", "connector_ready"},
        }
    return out


# Reachability grades ordered best-first, so a capability is represented by its
# strongest supplier rather than whichever source happened to be listed first.
_REACH_RANK = {
    "held": 0, "connector_ready": 1, "declared_only": 2,
    "connector_unavailable": 3, "not_on_desk": 4,
}


def capability_matrix(repo_root: Path) -> dict[str, Any]:
    """Capabilities the desk declares, each with its graded suppliers."""
    root = Path(repo_root)
    doc = _load(root / SOURCE_MAP_REL)
    glossary = doc.get("capabilities_glossary") or {}
    evidence = source_evidence(root)

    by_capability: dict[str, list[dict[str, Any]]] = {}
    for row in evidence.values():
        for cap in row["capabilities"]:
            by_capability.setdefault(str(cap), []).append(row)

    capabilities = []
    for cap, suppliers in by_capability.items():
        suppliers = sorted(
            suppliers,
            key=lambda r: (_REACH_RANK.get(r["reachability"], 9), -r["query_ready_datasets"]),
        )
        geographies = sorted({g for s in suppliers for g in s["geographies"]})
        obtainable = [s for s in suppliers if s["actionable"]]
        capabilities.append(
            {
                "capability": cap,
                "description": glossary.get(cap) or "",
                "geographies": geographies,
                "supplier_count": len(suppliers),
                "obtainable_now": bool(obtainable),
                # Datasets held by the sources that supply this capability --
                # NOT a count of datasets providing it. A source declaring five
                # capabilities contributes its whole holding to each, so this
                # measures supplier depth and must never be presented as "50
                # daily-price datasets". The name says which.
                "supplier_datasets_query_ready": sum(s["query_ready_datasets"] for s in suppliers),
                "suppliers": [
                    {
                        k: s[k]
                        for k in (
                            "source_id", "label", "provider", "access_mode", "license",
                            "reachability", "reachability_detail", "query_ready_datasets",
                            "geographies", "known_gaps", "actionable",
                        )
                    }
                    for s in suppliers
                ],
            }
        )
    capabilities.sort(key=lambda c: (not c["obtainable_now"], -c["supplier_datasets_query_ready"], c["capability"]))

    grades: dict[str, int] = {}
    for row in evidence.values():
        grades[row["reachability"]] = grades.get(row["reachability"], 0) + 1

    return {
        "capabilities": capabilities,
        "sources": sorted(
            evidence.values(),
            key=lambda r: (_REACH_RANK.get(r["reachability"], 9), str(r["source_id"])),
        ),
        "totals": {
            "capabilities": len(capabilities),
            "sources": len(evidence),
            "obtainable_capabilities": sum(1 for c in capabilities if c["obtainable_now"]),
            "reachability": grades,
        },
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = capability_matrix(args.repo_root)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    t = result["totals"]
    print(f"{t['obtainable_capabilities']}/{t['capabilities']} capabilities obtainable now "
          f"· {t['sources']} sources · {t['reachability']}")
    for cap in result["capabilities"]:
        mark = "●" if cap["obtainable_now"] else "○"
        print(f"\n{mark} {cap['capability']}  ({cap['supplier_count']} supplier(s), "
              f"{cap['supplier_datasets_query_ready']} datasets across them)")
        print(f"  {cap['description'][:100]}")
        for s in cap["suppliers"]:
            print(f"    {s['reachability']:22} {str(s['label'])[:44]:46} {s['reachability_detail'][:44]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
