#!/usr/bin/env python3
"""Chat completion contract — block until jobs/campaigns finish and return paths."""

from __future__ import annotations

import time
from typing import Any

from scripts.research_data_mcp.procurement_delivery import (
    advance_workers,
    format_job_collect_outcome,
    format_ready_delivery,
    procured_files_from_job,
)

TERMINAL_JOB = frozenset({"completed", "failed", "cancelled"})
TERMINAL_CAMPAIGN = frozenset({"ready", "failed"})


def chat_completion_config(repo_root: Any) -> dict[str, Any]:
    from scripts.research_data_mcp.magic_config import load_magic_config

    return dict((load_magic_config(repo_root).get("chat") or {}))


def chat_wait_enabled(gateway: Any) -> bool:
    import os
    import sys

    if "pytest" in sys.modules:
        return False
    if os.environ.get("PROCUREMENT_CHAT_NO_WAIT") == "1":
        return False
    cfg = chat_completion_config(gateway.repo_root)
    return bool(cfg.get("wait_for_completion", True))


def chat_wait_seconds(gateway: Any) -> int:
    cfg = chat_completion_config(gateway.repo_root)
    return int(cfg.get("wait_seconds") or 600)


def apply_chat_local_collect(plan: dict[str, Any], *, url: str = "") -> dict[str, Any]:
    """Force controller-side HTTP collect for direct file URLs in chat."""
    plan = dict(plan)
    if str(plan.get("job_type") or "") != "http_manifest":
        return plan
    if plan.get("local_collect"):
        return plan
    if url:
        from scripts.research_data_mcp.scrape_plan import classify_url

        if classify_url(url) == "direct_http":
            plan["local_collect"] = True
            plan["public_direct_url"] = True
    elif plan.get("public_direct_url"):
        plan["local_collect"] = True
    return plan


def run_until_job_terminal(
    gateway: Any,
    job_id: str,
    *,
    timeout_s: int | None = None,
    poll_s: float = 2.0,
) -> dict[str, Any]:
    """Poll until a YZU job reaches a terminal state."""
    deadline = time.time() + (timeout_s if timeout_s is not None else chat_wait_seconds(gateway))
    job: dict[str, Any] = {}
    while time.time() < deadline:
        advance_workers(gateway, ticks=2)
        job = gateway.get_yzu_job(str(job_id))
        if str(job.get("status") or "") in TERMINAL_JOB:
            break
        time.sleep(poll_s)
    return job


def _campaign_job_ids(campaign: dict[str, Any]) -> list[str]:
    payload = campaign.get("payload") or {}
    ids: list[str] = []
    for key in ("collect_job_ids", "probe_job_ids"):
        ids.extend(str(x) for x in (payload.get(key) or []) if x)
    last = payload.get("last_collect_job")
    if isinstance(last, dict) and last.get("id"):
        ids.append(str(last["id"]))
    return list(dict.fromkeys(ids))


def _auto_approve_campaign_collect(gateway: Any, campaign_id: str) -> bool:
    try:
        gateway.approve_campaign_collect(campaign_id, 0)
        return True
    except (ValueError, IndexError, KeyError):
        return False
    except Exception:
        return False


def run_until_campaign_terminal(
    gateway: Any,
    campaign_id: str,
    *,
    timeout_s: int | None = None,
    poll_s: float = 2.0,
    auto_approve: bool = True,
) -> dict[str, Any]:
    """Block until campaign phase is ready or failed; tick workers throughout."""
    deadline = time.time() + (timeout_s if timeout_s is not None else chat_wait_seconds(gateway))
    campaign: dict[str, Any] = {}
    while time.time() < deadline:
        advance_workers(gateway, ticks=3)
        campaign = gateway.get_campaign(str(campaign_id))
        phase = str(campaign.get("phase") or "")
        payload = campaign.get("payload") or {}

        if phase in TERMINAL_CAMPAIGN:
            break

        recs = payload.get("recommendations") or []
        pending_collect = any(r.get("recommended_action") == "approve_collect" for r in recs)
        if auto_approve and pending_collect and phase in {"awaiting_approval", "recommend", "probe", "research"}:
            _auto_approve_campaign_collect(gateway, campaign_id)
            advance_workers(gateway, ticks=2)
            campaign = gateway.get_campaign(str(campaign_id))
            phase = str(campaign.get("phase") or "")
            if phase in TERMINAL_CAMPAIGN:
                break

        job_ids = _campaign_job_ids(campaign)
        if job_ids and all(
            str(gateway.get_yzu_job(jid).get("status") or "") in TERMINAL_JOB for jid in job_ids
        ):
            collect_ids = [str(x) for x in (payload.get("collect_job_ids") or [])]
            if collect_ids and all(
                str(gateway.get_yzu_job(jid).get("status") or "") == "completed" for jid in collect_ids
            ):
                break

        time.sleep(poll_s)

    return build_completion_outcome(gateway, campaign_id=str(campaign_id), campaign=campaign)


def build_completion_outcome(
    gateway: Any,
    *,
    campaign_id: str | None = None,
    job_id: str | None = None,
    campaign: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured terminal state: phase, paths, delivery note."""
    out: dict[str, Any] = {"paths": [], "files": [], "delivery_note": "", "phase": ""}

    if job_id and job is None:
        job = gateway.get_yzu_job(str(job_id))
    if job and str(job.get("status") or "") == "completed":
        note, extra = format_job_collect_outcome(gateway, str(job.get("id") or job_id or ""), job=job)
        out["delivery_note"] = note
        out["files"] = extra.get("procured_files") or procured_files_from_job(gateway, job)
        out["paths"] = [f.get("path") for f in out["files"] if f.get("path")]
        out["phase"] = "ready"
        out["job"] = job
        out.update({k: v for k, v in extra.items() if k not in out})
        return out

    if campaign_id:
        if campaign is None:
            campaign = gateway.get_campaign(str(campaign_id))
        phase = str(campaign.get("phase") or "")
        out["phase"] = phase
        out["campaign"] = campaign

        if phase == "ready":
            note, extra = format_ready_delivery(gateway, str(campaign_id))
            out["delivery_note"] = note
            out.update(extra)
            arts = extra.get("artifacts") or {}
            files = arts.get("artifacts") or arts.get("files") or []
            if isinstance(files, list):
                out["paths"] = [
                    str(f.get("path") or f.get("name") or "")
                    for f in files
                    if isinstance(f, dict) and (f.get("path") or f.get("name"))
                ]
            return out

        payload = campaign.get("payload") or {}
        for jid in _campaign_job_ids(campaign):
            j = gateway.get_yzu_job(jid)
            if str(j.get("status") or "") != "completed":
                continue
            files = procured_files_from_job(gateway, j)
            if files:
                out["files"].extend(files)
        out["paths"] = list(dict.fromkeys(f.get("path") for f in out["files"] if f.get("path")))
        if out["paths"]:
            lines = ["**Collection complete.**"]
            for row in out["files"][:8]:
                lines.append(f"- `{row['path']}`")
            out["delivery_note"] = "\n".join(lines)
        return out

    return out


def wait_for_chat_job(gateway: Any, job_id: str) -> tuple[str, dict[str, Any]]:
    """Wait for a collect job and return delivery note + extras for action_result."""
    if not chat_wait_enabled(gateway):
        return "", {}
    job = run_until_job_terminal(gateway, job_id)
    outcome = build_completion_outcome(gateway, job_id=job_id, job=job)
    return str(outcome.get("delivery_note") or ""), {
        k: v
        for k, v in outcome.items()
        if k in {"procured_files", "files", "paths", "job", "dataset_card", "registry_promotion"}
    }


def wait_for_chat_campaign(gateway: Any, campaign_id: str) -> tuple[str, dict[str, Any]]:
    """Wait for magic-procure campaign and return delivery note + extras."""
    if not chat_wait_enabled(gateway):
        return "", {}
    outcome = run_until_campaign_terminal(gateway, campaign_id)
    note = str(outcome.get("delivery_note") or "")
    if not note and outcome.get("phase") == "failed":
        camp = outcome.get("campaign") or {}
        note = f"Campaign failed: {str(camp.get('error') or 'unknown')[:200]}"
    return note, {
        k: v
        for k, v in outcome.items()
        if k
        not in {
            "delivery_note",
        }
    }
