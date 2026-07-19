#!/usr/bin/env python3
"""Operate-the-platform battery — registration + Discover routing + approve lifecycle."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

API = os.environ.get("RESEARCH_DRIVE_API", "http://127.0.0.1:8765")
SID = f"battery-{int(time.time())}"


@dataclass
class Case:
    name: str
    kind: str
    ok: bool = False
    elapsed: float = 0.0
    detail: str = ""
    error: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


results: list[Case] = []
LAST_SUB: str | None = None
LAST_INTENT: str | None = None
LAST_JOB: str | None = None
LAST_SEC_JOB: str | None = None


def http_json(method: str, path: str, body: dict | None = None, timeout: float = 90) -> Any:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        API + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def chat(message: str, rail: dict | None = None, timeout: float = 180) -> dict[str, Any]:
    body = {"message": message, "session_id": SID, "rail_context": rail or {"tab": "browse", "mode": "ask"}}
    req = urllib.request.Request(
        API + "/library/chat/stream",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    complete = None
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("type") == "complete":
                complete = ev.get("result") or {}
            elif ev.get("type") == "error":
                raise RuntimeError(ev.get("message") or ev.get("error") or "err")
    if not complete:
        raise RuntimeError("no complete")
    complete["_elapsed"] = round(time.time() - t0, 2)
    return complete


def run(case: Case, fn) -> None:
    t0 = time.time()
    try:
        fn(case)
        case.elapsed = round(time.time() - t0, 2)
    except Exception as exc:  # noqa: BLE001
        case.ok = False
        case.elapsed = round(time.time() - t0, 2)
        case.error = str(exc)[:280]
    results.append(case)
    print(
        f"[{'PASS' if case.ok else 'FAIL'}] {case.kind:8} {case.name:46} {case.elapsed:6.1f}s  "
        f"{(case.detail or case.error)[:110]}"
    )


TWSE_RAIL = {
    "selected": {
        "title": "TWSE Open API",
        "source_id": "twse_official",
        "connector_id": "twse",
        "candidate_key": "source:twse_official",
        "endpoint": "openapi.twse.com.tw",
    },
    "actions": ["schedule_refresh", "ask_about"],
}


def c_tools(c: Case) -> None:
    d = http_json("GET", "/library/extensions/tools")
    need = [
        "research_discover_create_refresh_subscription",
        "research_discover_pause_refresh_subscription",
        "research_discover_stop_refresh_subscription",
        "research_discover_create_intent",
        "research_discover_source_search",
        "research_discover_tick_refresh_subscriptions",
        "procurement_probe_public_source",
    ]
    miss = [n for n in need if n not in (d.get("tools") or [])]
    c.ok = not miss and int(d.get("count") or 0) >= 79
    c.detail = f"count={d.get('count')} miss={miss or 'none'}"


def c_schedule_spec_api(c: Case) -> None:
    global LAST_SUB
    out = http_json(
        "POST",
        "/library/discover/subscriptions",
        {
            "cadence": "weekly",
            "source_id": "twse_official",
            "connector_id": "twse",
            "requested_schedule": "every Monday at 10:00",
            "timezone": "Asia/Taipei",
            "enabled": True,
        },
    )
    spec = out.get("schedule_spec") or {}
    c.ok = (
        out.get("execution_mode") == "scheduled"
        and bool(out.get("auto_refresh"))
        and spec.get("cron") == "0 10 * * 1"
        and bool(out.get("next_run_at"))
        and bool(spec.get("executable"))
    )
    c.detail = f"id={out.get('id')} cron={spec.get('cron')} next={out.get('next_run_at')}"
    LAST_SUB = out.get("id")


def c_probe(c: Case) -> None:
    out = chat("Probe https://openapi.twse.com.tw", {"actions": ["probe"]})
    c.ok = out.get("action") == "probe_url"
    c.detail = f"action={out.get('action')} {out.get('_elapsed')}s"


def c_search(c: Case) -> None:
    out = chat("search vault for TWSE")
    c.ok = out.get("action") == "search" and int((out.get("artifacts") or {}).get("total") or 0) > 0
    c.detail = f"action={out.get('action')} total={(out.get('artifacts') or {}).get('total')}"


def c_discover_search(c: Case) -> None:
    out = chat("Use research_discover_search for query TWSE. List source_id and access_mode.")
    arts = out.get("artifacts") or {}
    rows = arts.get("results") or (arts.get("discover") or {}).get("results") or []
    sids = [r.get("source_id") for r in rows if isinstance(r, dict)]
    c.ok = out.get("action") == "discover_search" and "twse_official" in sids
    c.detail = f"action={out.get('action')} sids={sids[:3]}"


def c_schedule(c: Case) -> None:
    global LAST_SUB
    n0 = http_json("GET", "/library/discover/subscriptions").get("total") or 0
    out = chat("Schedule refresh every Monday at 10:00 for this source.", TWSE_RAIL)
    arts = out.get("artifacts") or {}
    sub = arts.get("subscription") or {}
    spec = sub.get("schedule_spec") or {}
    n1 = http_json("GET", "/library/discover/subscriptions").get("total") or 0
    if not spec and arts.get("subscription_id"):
        one = http_json("GET", f"/library/discover/subscriptions/{arts.get('subscription_id')}")
        spec = one.get("schedule_spec") or {}
    c.ok = (
        out.get("action") == "schedule_refresh"
        and arts.get("platform_registered")
        and n1 > n0
        and spec.get("cron") == "0 10 * * 1"
    )
    c.detail = f"sub={arts.get('subscription_id')} cron={spec.get('cron')}"
    LAST_SUB = arts.get("subscription_id") or LAST_SUB


def c_intent(c: Case) -> None:
    global LAST_INTENT
    ids0 = {i.get("id") for i in http_json("GET", "/library/discover/history?kind=intent&limit=50").get("items") or []}
    out = chat(
        "Create a Discover research intent for: TWSE daily prices for board-election event studies. Do not collect.",
        TWSE_RAIL,
    )
    arts = out.get("artifacts") or {}
    ids1 = {i.get("id") for i in http_json("GET", "/library/discover/history?kind=intent&limit=50").get("items") or []}
    new = ids1 - ids0
    c.ok = out.get("action") == "create_intent" and bool(new or arts.get("intent_id"))
    c.detail = f"new={sorted(new)[:1]} id={arts.get('intent_id')}"
    LAST_INTENT = sorted(new)[0] if new else arts.get("intent_id")


def c_pause(c: Case) -> None:
    if not LAST_SUB:
        c.ok = False
        c.detail = "no subscription"
        return
    out = chat(f"Pause subscription {LAST_SUB}")
    sub = http_json("GET", f"/library/discover/subscriptions/{LAST_SUB}")
    c.ok = out.get("action") == "pause_subscription" and sub.get("status") == "paused"
    c.detail = f"status={sub.get('status')}"


def c_resume(c: Case) -> None:
    out = chat(f"Resume subscription {LAST_SUB}")
    sub = http_json("GET", f"/library/discover/subscriptions/{LAST_SUB}")
    c.ok = out.get("action") == "resume_subscription" and sub.get("status") == "active"
    c.detail = f"status={sub.get('status')}"


def c_stop(c: Case) -> None:
    # use a disposable sub so we don't kill the resume one mid-battery
    disposable = http_json(
        "POST",
        "/library/discover/subscriptions",
        {
            "cadence": "weekly",
            "source_id": "twse_official",
            "connector_id": "twse",
            "requested_schedule": "every Monday at 10:00 stop-test",
            "timezone": "Asia/Taipei",
            "enabled": True,
        },
    ).get("id")
    out = chat(f"Stop subscription {disposable}")
    sub = http_json("GET", f"/library/discover/subscriptions/{disposable}")
    c.ok = out.get("action") == "stop_subscription" and sub.get("status") in {"stopped", "cancelled", "inactive", "disabled"} or (
        out.get("action") == "stop_subscription" and sub.get("enabled") is False
    )
    # tolerate status naming
    if out.get("action") == "stop_subscription" and (sub.get("status") in {"stopped", "cancelled", "inactive", "disabled"} or sub.get("enabled") is False):
        c.ok = True
    c.detail = f"action={out.get('action')} status={sub.get('status')} enabled={sub.get('enabled')}"


def c_direct_collect(c: Case) -> None:
    global LAST_JOB
    before = {i.get("id") for i in http_json("GET", "/library/discover/history?kind=collection_run&limit=80").get("items") or []}
    out = chat("Collect this source.", TWSE_RAIL)
    arts = out.get("artifacts") or {}
    jid = arts.get("job_id") or (arts.get("job") or {}).get("id")
    time.sleep(0.3)
    after = http_json("GET", "/library/discover/history?kind=collection_run&limit=80")
    hit = [i for i in (after.get("items") or []) if i.get("id") == jid or i.get("job_id") == jid]
    c.ok = out.get("action") == "discover_collect" and bool(jid) and bool(hit)
    c.detail = f"action={out.get('action')} job={jid} in_history={bool(hit)}"
    LAST_JOB = jid


def c_approve_lifecycle(c: Case) -> None:
    global LAST_JOB
    if not LAST_JOB:
        c.ok = False
        c.detail = "no job"
        return
    out = chat(f"Approve job {LAST_JOB}")
    job = http_json("GET", f"/library/jobs/{LAST_JOB}")
    hist = http_json("GET", "/library/discover/history?kind=collection_run&limit=80")
    hit = next((i for i in (hist.get("items") or []) if i.get("id") == LAST_JOB or i.get("job_id") == LAST_JOB), None)
    status = job.get("status")
    c.ok = (
        out.get("action") == "approve_job"
        and status in {"queued", "running", "completed", "approved"}
        and bool(hit)
        and hit.get("status") == status
    )
    # if completed already, even better
    if status == "completed" and hit and hit.get("status") == "completed":
        c.ok = True
    c.detail = f"action={out.get('action')} job_status={status} hist_status={(hit or {}).get('status')}"
    c.evidence = {"job_id": LAST_JOB, "status": status}


def c_sec_manifest_collect(c: Case) -> None:
    global LAST_SEC_JOB
    out = http_json(
        "POST",
        "/library/discover/collect",
        {
            "connector_id": "src_ace4a0fb8e9e",
            "limit": 2,
            "auto_approve": False,
            "name": "SEC company tickers battery",
            "candidate_key": "connector:src_ace4a0fb8e9e",
        },
        timeout=90,
    )
    job = out.get("job") or {}
    jid = job.get("id")
    plan = job.get("plan") or {}
    # approve
    if jid:
        http_json("POST", f"/library/jobs/{jid}/approve")
        job = http_json("GET", f"/library/jobs/{jid}")
    hist = http_json("GET", "/library/discover/history?kind=collection_run&limit=80")
    hit = next((i for i in (hist.get("items") or []) if i.get("id") == jid or i.get("job_id") == jid), None)
    c.ok = (
        bool(jid)
        and plan.get("job_type") == "http_manifest"
        and plan.get("public_direct_url") is True
        and job.get("status") in {"queued", "running", "completed"}
        and bool(hit)
    )
    c.detail = (
        f"job={jid} type={plan.get('job_type')} public={plan.get('public_direct_url')} "
        f"status={job.get('status')} hist={bool(hit)}"
    )
    LAST_SEC_JOB = jid
    c.evidence = {"job_id": jid, "status": job.get("status")}


def c_collect_http(c: Case) -> None:
    # legacy HTTP collect path still works for TWSE catalog
    out = http_json(
        "POST",
        "/library/discover/collect",
        {
            "connector_id": "twse",
            "source_id": "twse_official",
            "limit": 5,
            "auto_approve": False,
            "candidate_key": "source:twse_official",
            "name": "TWSE catalog collect battery",
            "discover_intent_id": LAST_INTENT or "",
        },
        timeout=90,
    )
    job = out.get("job") or {}
    jid = job.get("id")
    time.sleep(0.3)
    hit = [
        i
        for i in http_json("GET", "/library/discover/history?kind=collection_run&limit=80").get("items") or []
        if i.get("id") == jid or i.get("job_id") == jid
    ]
    c.ok = bool(jid) and bool(hit)
    c.detail = f"job={jid} type={(job.get('plan') or {}).get('job_type')} status={job.get('status')}"



def c_spectator_scrape(c: Case) -> None:
    """Niche browser harvest via SpectatorEngine → windows_lab."""
    rail = {
        "selected": {
            "title": "TWSE Open API",
            "source_id": "twse_official",
            "connector_id": "twse",
            "candidate_key": "source:twse_official",
            "endpoint": "openapi.twse.com.tw",
        }
    }
    out = chat("Scrape this source with Spectator.", rail)
    arts = out.get("artifacts") or {}
    jid = arts.get("job_id") or (arts.get("job") or {}).get("id")
    if not jid:
        c.ok = False
        c.detail = f"action={out.get('action')} no job"
        return
    # approve + expect windows execution (may take >60s)
    chat(f"Approve job {jid}", timeout=300)
    job = http_json("GET", f"/library/jobs/{jid}")
    # poll up to ~2 min
    import time as _t
    for _ in range(24):
        job = http_json("GET", f"/library/jobs/{jid}")
        if job.get("status") in {"completed", "failed", "cancelled"}:
            break
        _t.sleep(5)
    res = job.get("result") if isinstance(job.get("result"), dict) else {}
    hist = http_json("GET", "/library/discover/history?kind=collection_run&limit=40")
    hit = next((i for i in (hist.get("items") or []) if i.get("id") == jid or i.get("job_id") == jid), None)
    c.ok = job.get("status") == "completed" and res.get("pool") == "windows_lab" and bool(hit)
    c.detail = f"job={jid} status={job.get('status')} pool={res.get('pool')} extract={res.get('extract_path')}"
    c.evidence = {"job_id": jid, "status": job.get("status"), "pool": res.get("pool")}




def c_cadence_twse_http_manifest(c: Case) -> None:
    """Schedule refresh must harvest TWSE OpenAPI JSON, not Swagger scrape."""
    sub = http_json(
        "POST",
        "/library/discover/subscriptions",
        {
            "cadence": "weekly",
            "source_id": "twse_official",
            "connector_id": "twse",
            "requested_schedule": "every Monday at 10:00",
            "timezone": "Asia/Taipei",
            "enabled": True,
        },
    )
    sid = sub.get("id")
    tick = http_json("POST", f"/library/discover/subscriptions/{sid}/run", {"auto_approve_safe": True}, timeout=180)
    fired = (tick.get("fired") or [None])[0] or {}
    jid = fired.get("job_id")
    if not jid:
        c.ok = False
        c.detail = f"no fire err={tick.get('errors')}"
        return
    job = {}
    for _ in range(45):
        job = http_json("GET", f"/library/jobs/{jid}")
        if job.get("status") in {"completed", "failed", "cancelled"}:
            break
        time.sleep(2)
    plan = job.get("plan") or {}
    res = job.get("result") if isinstance(job.get("result"), dict) else {}
    val = ((res.get("materialized") or {}).get("validation") or {})
    http_json("POST", "/library/discover/subscriptions/tick", {"limit": 1})
    upd = http_json("GET", f"/library/discover/subscriptions/{sid}")
    c.ok = (
        plan.get("job_type") == "http_manifest"
        and plan.get("collect_resolution") == "twse_openapi_known_manifest"
        and job.get("status") == "completed"
        and int(val.get("file_count") or 0) >= 4
        and int(val.get("total_bytes") or 0) > 100_000
        and upd.get("last_run_status") == "completed"
    )
    c.detail = (
        f"job={jid} status={job.get('status')} files={val.get('file_count')} "
        f"bytes={val.get('total_bytes')} resolution={plan.get('collect_resolution')} "
        f"sub_status={upd.get('last_run_status')}"
    )
    c.evidence = {"job_id": jid, "validation": val, "subscription_id": sid}


def c_cadence_force_tick(c: Case) -> None:
    """Register → next_run armed → force tick → History collection_run."""
    sub = http_json(
        "POST",
        "/library/discover/subscriptions",
        {
            "cadence": "weekly",
            "source_id": "twse_official",
            "connector_id": "twse",
            "requested_schedule": "every Monday at 10:00",
            "timezone": "Asia/Taipei",
            "enabled": True,
        },
    )
    sid = sub.get("id")
    if not (sid and sub.get("next_run_at") and sub.get("execution_mode") == "scheduled"):
        c.ok = False
        c.detail = f"not armed id={sid} mode={sub.get('execution_mode')} next={sub.get('next_run_at')}"
        return
    tick = http_json(
        "POST",
        f"/library/discover/subscriptions/{sid}/run",
        {"auto_approve_safe": True},
        timeout=120,
    )
    fired = (tick.get("fired") or [])
    jid = (fired[0].get("job_id") if fired else "") or ""
    updated = http_json("GET", f"/library/discover/subscriptions/{sid}")
    hist = http_json("GET", "/library/discover/history?kind=collection_run&limit=40")
    hit = next(
        (i for i in (hist.get("items") or []) if i.get("id") == jid or i.get("job_id") == jid),
        None,
    ) if jid else None
    c.ok = bool(fired) and bool(jid) and bool(updated.get("last_run_at")) and bool(updated.get("next_run_at")) and bool(hit)
    c.detail = (
        f"sub={sid} job={jid} last={updated.get('last_run_at')} "
        f"next={updated.get('next_run_at')} hist={bool(hit)} err={tick.get('errors')}"
    )
    c.evidence = {"subscription_id": sid, "job_id": jid, "tick": tick}


def c_honesty(c: Case) -> None:
    subs = http_json("GET", "/library/discover/subscriptions").get("subscriptions") or []
    lying = []
    for s in subs:
        mode = s.get("execution_mode")
        auto = bool(s.get("auto_refresh"))
        nxt = s.get("next_run_at")
        if mode == "scheduled":
            if not auto or not nxt:
                lying.append(s.get("id"))
        elif mode in (None, "non_executing"):
            if auto or nxt:
                lying.append(s.get("id"))
        else:
            lying.append(s.get("id"))
    c.ok = bool(subs) and not lying
    c.detail = f"n={len(subs)} lying={lying[:3]}"


def c_composer_schedule(c: Case) -> None:
    ids0 = {i.get("id") for i in http_json("GET", "/library/discover/history?kind=subscription&limit=50").get("items") or []}
    out = chat(
        "Use research_discover_create_refresh_subscription for source_id twse_official connector_id twse "
        "cadence weekly requested_schedule 'every Monday 10:00'. Confirm in history with next_run_at.",
        {"tab": "browse"},
        timeout=180,
    )
    ids1 = {i.get("id") for i in http_json("GET", "/library/discover/history?kind=subscription&limit=50").get("items") or []}
    new = ids1 - ids0
    c.ok = out.get("action") in {"composer", "schedule_refresh"} and bool(new)
    c.detail = f"action={out.get('action')} new={sorted(new)[:1]} brain={(out.get('artifacts') or {}).get('brain')}"


def main() -> int:
    print("SESSION", SID, "API", API)
    run(Case("mcp tools 78+", "http"), c_tools)
    run(Case("API schedule_spec cron", "http"), c_schedule_spec_api)
    run(Case("direct probe", "direct"), c_probe)
    run(Case("direct vault search", "direct"), c_search)
    run(Case("direct Discover catalog search", "direct"), c_discover_search)
    run(Case("direct schedule+spec", "direct"), c_schedule)
    run(Case("direct create intent", "direct"), c_intent)
    run(Case("direct pause sub", "direct"), c_pause)
    run(Case("direct resume sub", "direct"), c_resume)
    run(Case("direct stop sub", "direct"), c_stop)
    run(Case("direct collect selected → History", "direct"), c_direct_collect)
    run(Case("approve job → History lifecycle", "direct"), c_approve_lifecycle)
    run(Case("HTTP catalog collect → History", "http"), c_collect_http)
    run(Case("SEC http_manifest collect+approve", "http"), c_sec_manifest_collect)
    run(Case("spectator scrape TWSE→windows_lab", "spectator"), c_spectator_scrape)
    run(Case("cadence force tick → History", "http"), c_cadence_force_tick)
    run(Case("cadence TWSE OpenAPI harvest", "http"), c_cadence_twse_http_manifest)
    run(Case("honesty schedule consistency", "http"), c_honesty)
    run(Case("composer schedule register", "composer"), c_composer_schedule)

    passed = sum(1 for r in results if r.ok)
    print("=" * 80)
    print(f"SCORE {passed}/{len(results)} ({100 * passed / len(results):.0f}%)")
    for r in results:
        if not r.ok:
            print("FAIL", r.name, r.detail or r.error)

    out = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "docs", "status", "generated", "composer_platform_battery.json")
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(
        {
            "session_id": SID,
            "score": f"{passed}/{len(results)}",
            "passed": passed,
            "total": len(results),
            "ladder": [
                "tools",
                "schedule_spec",
                "probe",
                "vault_search",
                "discover_search",
                "schedule",
                "intent",
                "pause",
                "resume",
                "stop",
                "collect",
                "approve_lifecycle",
                "http_collect",
                "sec_manifest",
                "spectator_scrape",
                "honesty",
                "composer_schedule",
            ],
            "cases": [
                {
                    "name": r.name,
                    "kind": r.kind,
                    "ok": r.ok,
                    "elapsed": r.elapsed,
                    "detail": r.detail,
                    "error": r.error,
                    "evidence": r.evidence,
                }
                for r in results
            ],
        },
        open(out, "w"),
        indent=2,
    )
    print("wrote", out)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
