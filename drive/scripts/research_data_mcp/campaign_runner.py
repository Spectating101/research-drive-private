#!/usr/bin/env python3
"""Background campaign advancement — resume probes/collects on worker tick."""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.magic_config import load_magic_config

TERMINAL_JOB = frozenset({"completed", "failed", "cancelled"})


class CampaignRunner:
    def __init__(
        self,
        gateway: Any,
        campaigns: Any,
        *,
        memory: Any = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.gateway = gateway
        self.campaigns = campaigns
        self.memory = memory
        self.config = config or load_magic_config(gateway.repo_root)
        campaign_cfg = self.config.get("campaign") or {}
        self._tick_limit = int(campaign_cfg.get("tick_limit", 3))
        self._auto_tick = bool(campaign_cfg.get("auto_tick", True))

    def on_job_completed(self, job: dict[str, Any], *, promoted: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
        cid = str((job.get("request") or {}).get("campaign_id") or "")
        if not cid or not self.campaigns:
            return None
        try:
            campaign = self.campaigns.get(cid)
        except KeyError:
            return None

        payload = campaign.get("payload") or {}
        jid = str(job.get("id") or "")
        status = str(job.get("status") or "")

        collect_ids = {str(x) for x in (payload.get("collect_job_ids") or [])}
        last_collect = (payload.get("last_collect_job") or {}).get("id")
        if last_collect:
            collect_ids.add(str(last_collect))

        if jid in collect_ids:
            if status == "completed":
                return self.campaigns.update(
                    cid,
                    phase="ready",
                    status="ready",
                    payload={"promoted": promoted or [], "last_collect_job": job},
                )
            if status in TERMINAL_JOB - {"completed"}:
                return self.campaigns.update(
                    cid,
                    phase="failed",
                    status="failed",
                    error=str(job.get("error") or status)[:500],
                    payload={"last_collect_job": job},
                )

        probe_ids = [str(x) for x in (payload.get("probe_job_ids") or [])]
        if jid in probe_ids and probe_ids and self._all_terminal(probe_ids):
            return self._advance_after_probes(cid, payload)

        return None

    def tick(self, limit: int | None = None) -> list[dict[str, Any]]:
        if not self._auto_tick or not self.campaigns:
            return []
        advances: list[dict[str, Any]] = []
        cap = limit if limit is not None else self._tick_limit
        for campaign in self.campaigns.active()[:cap]:
            updated = self._tick_one(campaign)
            if updated:
                advances.append(updated)
        return advances

    def resume(self, campaign_id: str, *, force_execute: bool = False) -> dict[str, Any]:
        from scripts.research_data_mcp.magic_procure import MagicProcurement

        mp = MagicProcurement(self.gateway, memory=self.memory, campaigns=self.campaigns)
        return mp.resume(campaign_id, force_execute=force_execute)

    def _tick_one(self, campaign: dict[str, Any]) -> dict[str, Any] | None:
        phase = str(campaign.get("phase") or "")
        cid = str(campaign["id"])
        payload = campaign.get("payload") or {}

        if phase == "collecting":
            job_ids: list[str] = [str(x) for x in (payload.get("collect_job_ids") or [])]
            last = payload.get("last_collect_job")
            if isinstance(last, dict) and last.get("id"):
                if str(last.get("status") or "") == "completed":
                    return self.campaigns.update(
                        cid,
                        phase="ready",
                        status="ready",
                        payload={"last_collect_job": last},
                    )
                job_ids.append(str(last["id"]))
            for jid in dict.fromkeys(job_ids):
                job = self.gateway.get_yzu_job(jid)
                status = str(job.get("status") or "")
                if status == "pending_approval":
                    self.gateway.jobs.approve(jid)
                    self.gateway.jobs.tick()
                    continue
                if status == "queued":
                    self.gateway.jobs.tick()
                    continue
                if status == "completed":
                    return self.campaigns.update(cid, phase="ready", status="ready", payload={"last_collect_job": job})
                if status in TERMINAL_JOB - {"completed"}:
                    return self.campaigns.update(
                        cid,
                        phase="failed",
                        status="failed",
                        error=str(job.get("error") or status)[:500],
                        payload={"last_collect_job": job},
                    )

        if phase in {"probe", "research"}:
            probe_ids = [str(x) for x in (payload.get("probe_job_ids") or [])]
            if probe_ids:
                progressed = False
                for jid in probe_ids:
                    job = self.gateway.get_yzu_job(jid)
                    status = str(job.get("status") or "")
                    if status == "pending_approval":
                        self.gateway.jobs.approve(jid)
                        progressed = True
                    elif status in {"queued", "running"}:
                        progressed = True
                if progressed:
                    self.gateway.jobs.tick()
                if self._all_terminal(probe_ids):
                    return self._advance_after_probes(cid, payload)

        return None

    def _advance_after_probes(self, campaign_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        recs = payload.get("recommendations") or []
        if any(r.get("recommended_action") == "approve_collect" for r in recs):
            phase = "awaiting_approval"
        elif recs:
            phase = "recommend"
        else:
            phase = "probe"
        research_cfg = self.config.get("research") or {}
        if phase == "awaiting_approval" and research_cfg.get("auto_collect"):
            from scripts.research_data_mcp.magic_procure import MagicProcurement

            mp = MagicProcurement(self.gateway, memory=self.memory, campaigns=self.campaigns)
            for index, rec in enumerate(recs):
                if rec.get("recommended_action") == "approve_collect":
                    mp.approve_collect(campaign_id, index)
                    break
            return self.campaigns.get(campaign_id)
        return self.campaigns.update(campaign_id, phase=phase)

    def _all_terminal(self, job_ids: list[str]) -> bool:
        if not job_ids:
            return False
        for jid in job_ids:
            job = self.gateway.get_yzu_job(jid)
            if str(job.get("status") or "") not in TERMINAL_JOB:
                return False
        return True
