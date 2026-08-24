#!/usr/bin/env python3
"""Live procurement ops smoke — run against :8765 when API + worker are up."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("PROCUREMENT_OPS_API", "http://127.0.0.1:8765")
EMAIL = os.environ.get("PROCUREMENT_OPS_EMAIL", "drkong@saturn.yzu.edu.tw")


def _post(path: str, body: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as r:
        return json.loads(r.read())


def main() -> int:
    report: dict = {"api": API, "steps": []}
    session_id = ""

    def step(name: str, ok: bool, detail: str = "") -> None:
        report["steps"].append({"name": name, "ok": ok, "detail": detail[:240]})
        mark = "OK" if ok else "FAIL"
        print(f"[{mark}] {name}" + (f" — {detail[:120]}" if detail else ""))

    try:
        st = _get("/yzu/status")
        step("cluster_status", True, f"disk={st.get('disk', {}).get('free_gb')}GB jobs={st.get('jobs')}")
    except Exception as exc:
        step("cluster_status", False, str(exc))
        _write(report)
        return 1

    try:
        prof = _get(f"/library/faculty/profile?email={EMAIL}")
        step("faculty_profile", prof.get("found") is True, prof.get("profile", {}).get("title", ""))
    except Exception as exc:
        step("faculty_profile", False, str(exc))

    # Composer search thread. Keep later Composer turns fresh so a bad/slow session
    # does not mask whether each capability is available.
    try:
        r = _post("/library/chat", {"message": "what taiwan equity panels do we have?", "user_email": EMAIL})
        session_id = r.get("session_id") or ""
        step(
            "chat_search",
            r.get("action") == "search" and bool(r.get("reply")),
            f"action={r.get('action')} words={len((r.get('reply') or '').split())}",
        )
    except Exception as exc:
        step("chat_search", False, str(exc))

    # Direct preview path used by Library/Discover detail surfaces.
    try:
        r = _get("/query/mops_governance_panel?limit=3")
        rows = len(r.get("rows") or [])
        matched = r.get("meta", {}).get("matched")
        step("query_preview", rows > 0, f"dataset=mops_governance_panel rows={rows} matched={matched}")
    except Exception as exc:
        step("query_preview", False, str(exc))

    # Composer DOI collect/in-lab path.
    try:
        r = _post(
            "/library/chat",
            {
                "message": "collect 10.5281/zenodo.7545157",
                "user_email": EMAIL,
            },
        )
        action = r.get("action")
        ok = action in {"collect_doi", "collect", "in_lab"} and bool(r.get("reply"))
        step("chat_collect_doi", ok, f"action={action} campaign={r.get('campaign_id')}")
    except Exception as exc:
        step("chat_collect_doi", False, str(exc))

    # probe URL
    try:
        r = _post(
            "/library/chat",
            {"message": "probe https://example.com", "user_email": EMAIL},
        )
        step("chat_probe_url", r.get("action") == "probe_url", (r.get("reply") or "")[:80])
    except Exception as exc:
        step("chat_probe_url", False, str(exc))

    # campaigns + datasets
    try:
        camps = _get("/library/campaigns?limit=5")
        ds = _get("/datasets")
        step("registry", True, f"campaigns={len(camps.get('campaigns') or [])} datasets={len(ds.get('datasets') or [])}")
    except Exception as exc:
        step("registry", False, str(exc))

    failed = [s for s in report["steps"] if not s["ok"]]
    report["passed"] = len(report["steps"]) - len(failed)
    report["failed"] = len(failed)
    _write(report)
    return 1 if failed else 0


def _write(report: dict) -> None:
    out = Path(__file__).resolve().parents[1] / "docs" / "status" / "generated"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "procurement_ops_smoke.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {path}")


if __name__ == "__main__":
    sys.exit(main())
