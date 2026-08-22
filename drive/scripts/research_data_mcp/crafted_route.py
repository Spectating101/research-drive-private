#!/usr/bin/env python3
"""Keep the method that got the data, not just the data.

craft_collect_plan() returns {plan, rationale, doctrine} and stores none of it.
The flywheel then promotes curated and locator rows — the output. Across 168
registry rows there is no field naming how anything was obtained: no plan, no
rationale, no recipe. So 47 Etherscan datasets exist while the reasoning that
produced them is gone, and the next OpenSea-shaped need starts from nothing.

That also makes the desk understate itself. Resources lists a fixed set of
vendors because a crafted route has nowhere to be recorded, so work that took
real reasoning — paging an undocumented API, finding the field that carries the
identifier, learning the rate limit the hard way — reads as no capability at all.

A record here is a claim about what worked, so it carries its evidence: what ran,
what came back, and when it last succeeded. A method that has never completed is
kept as `drafted`, never as a capability — an untested recipe presented as a
route is how a researcher plans around something that does not work.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

SCHEMA = 1
# A route is only a capability once it has produced something. Anything else is
# a draft, however good the reasoning behind it looked.
DRAFTED = "drafted"
PROVEN = "proven"
FAILING = "failing"


def store_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / "data_lake" / "procurement_memory" / "crafted_routes.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema": SCHEMA, "routes": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # A corrupt store must not erase the record; the caller decides.
        return {"schema": SCHEMA, "routes": {}, "unreadable": True}
    if not isinstance(doc, dict):
        return {"schema": SCHEMA, "routes": {}, "unreadable": True}
    doc.setdefault("schema", SCHEMA)
    doc.setdefault("routes", {})
    return doc


def _text(value: Any) -> str:
    return str(value or "").strip()


def record_attempt(
    repo_root: Path | str,
    *,
    source_id: str,
    plan: dict[str, Any],
    rationale: str = "",
    succeeded: bool,
    produced: list[str] | None = None,
    note: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    """Record that a crafted plan ran, and what it did.

    Success is not assumed from a plan existing. `succeeded` is the caller's
    observation of the run, and a route that has never succeeded stays drafted.
    """
    source_id = _text(source_id)
    if not source_id:
        return {"ok": False, "error": "source_id is required"}
    if not isinstance(plan, dict) or not plan:
        return {"ok": False, "error": "a plan is required to record a route"}

    path = store_path(repo_root)
    doc = _load(path)
    if doc.get("unreadable"):
        return {"ok": False, "error": "crafted route store is unreadable; not overwriting it"}

    stamp = time.time() if now is None else float(now)
    route = doc["routes"].get(source_id) or {
        "source_id": source_id,
        "state": DRAFTED,
        "attempts": 0,
        "successes": 0,
        "first_seen": stamp,
        "produced": [],
    }
    route["plan"] = plan
    if rationale:
        route["rationale"] = rationale
    if note:
        route["note"] = note
    route["attempts"] = int(route.get("attempts", 0)) + 1
    route["last_attempt_at"] = stamp
    if succeeded:
        route["successes"] = int(route.get("successes", 0)) + 1
        route["last_success_at"] = stamp
        route["state"] = PROVEN
        for dataset_id in produced or []:
            d = _text(dataset_id)
            if d and d not in route["produced"]:
                route["produced"].append(d)
    elif route.get("successes", 0):
        # It worked before and did not this time. That is worth saying plainly
        # rather than silently keeping the old green state.
        route["state"] = FAILING
    else:
        route["state"] = DRAFTED

    doc["routes"][source_id] = route
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return {"ok": True, "source_id": source_id, "state": route["state"], "attempts": route["attempts"]}


def get_route(repo_root: Path | str, source_id: str) -> dict[str, Any] | None:
    return _load(store_path(repo_root))["routes"].get(_text(source_id))


def crafted_capabilities(repo_root: Path | str, *, proven_only: bool = True) -> list[dict[str, Any]]:
    """Crafted routes as capabilities the desk can honestly claim.

    Proven first and by default: Resources should be able to show what the desk
    can actually do, without a drafted recipe reading as a working route.
    """
    routes = list(_load(store_path(repo_root))["routes"].values())
    if proven_only:
        routes = [r for r in routes if r.get("state") == PROVEN]
    routes.sort(key=lambda r: (-int(r.get("successes", 0)), r.get("source_id", "")))
    return [
        {
            "source_id": r.get("source_id"),
            "state": r.get("state"),
            "successes": int(r.get("successes", 0)),
            "attempts": int(r.get("attempts", 0)),
            "produced": list(r.get("produced") or []),
            "last_success_at": r.get("last_success_at"),
            "rationale": r.get("rationale", ""),
        }
        for r in routes
    ]
