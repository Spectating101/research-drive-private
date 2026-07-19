#!/usr/bin/env python3
"""Campaign delivery — tick workers, artifacts, registry promotion, dataset cards."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


from scripts.yzu_cluster.cluster_ops import cluster_only, format_cluster_summary


def advance_workers(gateway: Any, *, ticks: int = 2) -> None:
    """Run job worker + campaign runner so pending probes/collects move forward."""
    cfg = getattr(getattr(gateway, "orchestrator", None), "cfg", {}) or {}
    if cluster_only(cfg):
        ticks = max(ticks, 4)
    for _ in range(max(1, ticks)):
        try:
            gateway.jobs.tick()
        except Exception:
            break
    try:
        gateway.tick_campaigns(limit=3)
    except Exception:
        pass


def scrape_extract_path(gateway: Any, job_id: str) -> Path | None:
    rel = gateway.repo_root / "data_lake/spectator_engine/scrapes" / job_id / "extract.json"
    if rel.is_file():
        return rel
    return None


def build_scrape_card(gateway: Any, job_id: str) -> dict[str, Any] | None:
    path = scrape_extract_path(gateway, job_id)
    if not path:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return {
        "id": f"scrape:{job_id}",
        "handle": f"scrape:{job_id}",
        "title": payload.get("title") or f"Web scrape {payload.get('url', job_id)[:60]}",
        "url": payload.get("url"),
        "source": "web_scrape",
        "phase": "ready",
        "files": [{"name": "extract.json", "path": str(path.relative_to(gateway.repo_root)), "kind": "json"}],
        "schema_preview": {
            "kind": "json",
            "columns": ["url", "title", "links", "dataset_links"],
            "rows": [
                {
                    "url": payload.get("url"),
                    "title": (payload.get("title") or "")[:120],
                    "links": len(payload.get("links") or []),
                    "dataset_links": len(payload.get("dataset_links") or []),
                }
            ],
        },
        "load_hint": f"open_dataset('scrape:{job_id}')",
    }


def format_ready_delivery(gateway: Any, campaign_id: str) -> tuple[str, dict[str, Any]]:
    """Build reply + artifacts when a campaign is ready or has deliverables."""
    artifacts: dict[str, Any] = {}
    lines: list[str] = [f"**Campaign `{campaign_id}` is ready.**"]
    state_patch: dict[str, Any] = {"campaign_id": campaign_id, "last_handle": f"campaign:{campaign_id}"}

    try:
        arts = gateway.list_campaign_artifacts(campaign_id)
        artifacts["artifacts"] = arts
        files = arts.get("artifacts") or arts.get("files") or []
        if isinstance(files, list) and files:
            lines.append("\n**Files:**")
            for f in files[:8]:
                if not isinstance(f, dict):
                    continue
                name = f.get("name") or f.get("path") or "file"
                dl = f.get("download_path") or ""
                lines.append(f"- `{name}`" + (f" · [download]({dl})" if dl else ""))
    except Exception:
        pass

    try:
        card = gateway.get_dataset_card(f"campaign:{campaign_id}")
        artifacts["dataset_card"] = card
        state_patch["last_handle"] = card.get("handle") or state_patch["last_handle"]
        lines.append(f"\n**Dataset:** {card.get('title') or card.get('handle')}")
        if card.get("dataset_id"):
            lines.append(f"- Registry id: `{card['dataset_id']}` — say **query {card['dataset_id']}**")
        prev = card.get("schema_preview")
        if prev and prev.get("columns"):
            lines.append(f"- Columns: {', '.join(str(c) for c in prev['columns'][:10])}")
    except Exception:
        card = None

    campaign = gateway.get_campaign(campaign_id)
    payload = campaign.get("payload") or {}
    promoted = payload.get("promoted") or []
    if promoted:
        lines.append("\n**Promoted to registry:**")
        for row in promoted[:5]:
            if isinstance(row, dict):
                lines.append(f"- `{row.get('dataset_id') or row.get('id')}` — {row.get('title', '')[:80]}")

    recs = payload.get("recommendations") or []
    actionable = [r for r in recs if r.get("recommended_action") == "approve_collect"]
    if actionable:
        lines.append(f"\n**{len(actionable)} collect recommendation(s) pending** — say **approve recommendation 1**")

    for jid in (state_patch.get("job_ids") or payload.get("collect_job_ids") or [])[:3]:
        sc = build_scrape_card(gateway, str(jid))
        if sc:
            artifacts["dataset_card"] = sc
            state_patch["last_handle"] = sc["handle"]
            lines.append(f"\n**Scrape output** (`scrape:{jid}`) — {sc.get('url', '')[:70]}")
            break

    lines.append("\nSay **preview it**, **pin it**, **archive to drive**, or **query** the registry id.")
    archive_note = ""
    try:
        from scripts.research_data_mcp.procurement_archive import archive_from_card

        if card:
            archived = archive_from_card(gateway, card, campaign_id=campaign_id)
            if archived:
                jid = (archived.get("archive_job") or {}).get("job", {}).get("id", "")
                archive_note = f"\n\n**Auto-archive** queued for cold storage (job `{jid[:12]}`)." if jid else "\n\n**Auto-archive** queued for GDrive."
                artifacts["auto_archive"] = archived
    except Exception:
        pass
    return "\n".join(lines) + archive_note, {**artifacts, "state_patch": state_patch}


def format_campaign_status(gateway: Any, campaign_id: str, state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    advance_workers(gateway)
    cfg = getattr(getattr(gateway, "orchestrator", None), "cfg", {}) or {}
    campaign = gateway.get_campaign(campaign_id)
    phase = str(campaign.get("phase") or "")
    payload = campaign.get("payload") or {}

    if phase == "ready":
        return format_ready_delivery(gateway, campaign_id)

    lines = [
        f"**Campaign `{campaign_id}`**",
        f"- Phase: **{phase}** · status {campaign.get('status', '')}",
        f"- Goal: {(campaign.get('goal') or '')[:120]}",
    ]

    for key, label in (("probe_job_ids", "Probes"), ("collect_job_ids", "Collect jobs")):
        ids = payload.get(key) or []
        if ids:
            lines.append(f"- {label}: {', '.join(str(i)[:12] for i in ids[:5])}")

    recs = payload.get("recommendations") or []
    if recs:
        lines.append(f"- Recommendations: {len(recs)}")
        for i, rec in enumerate(recs[:4], 1):
            action = rec.get("recommended_action") or rec.get("feasibility") or "?"
            url = (rec.get("url") or "")[:60]
            lines.append(f"  {i}. {action} · {url}")

    job_ids = list(dict.fromkeys((state.get("job_ids") or []) + (payload.get("collect_job_ids") or [])))
    state_patch: dict[str, Any] = {"job_ids": job_ids}
    for jid in job_ids[:4]:
        try:
            job = gateway.get_yzu_job(str(jid))
            plan = job.get("plan") or {}
            lines.append(
                f"- Job `{str(jid)[:12]}` · **{job.get('status')}** · {plan.get('job_type')} · "
                f"{(plan.get('title') or '')[:50]}"
            )
            result = job.get("result") or {}
            if result.get("extract_path"):
                lines.append(f"  → scrape output: `{result['extract_path']}`")
            promo = result.get("registry_promotion") or []
            if promo:
                lines.append(f"  → promoted: {[p.get('dataset_id') for p in promo if isinstance(p, dict)]}")
        except Exception:
            pass

    if phase in {"awaiting_approval", "recommend"} and recs:
        lines.append("\nReply **approve recommendation N** to collect, or **resume** to continue probing.")

    try:
        status = gateway.cluster_status(live=False)
        status["cluster_only"] = cluster_only(cfg)
        lines.append("\n" + format_cluster_summary(status))
    except Exception:
        pass

    return "\n".join(lines), {"state_patch": state_patch, "campaign": campaign}


def _human_bytes(n: int | float | None) -> str:
    size = int(n or 0)
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.2f} GB"


def procured_files_from_job(gateway: Any, job: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract promoted file rows from a completed collect job."""
    repo = Path(gateway.repo_root).resolve()
    result = job.get("result") or {}
    plan = job.get("plan") or {}
    materialized = result.get("materialized") or {}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(name: str, rel: str, nbytes: int = 0) -> None:
        rel = rel.strip().lstrip("/")
        if not rel or rel in seen:
            return
        seen.add(rel)
        path = repo / rel
        if path.is_file() and not nbytes:
            nbytes = path.stat().st_size
        out.append({"name": name or Path(rel).name, "path": rel, "bytes": nbytes})

    for row in materialized.get("files") or []:
        rel = str(row.get("path") or "")
        if rel and not rel.startswith("data_lake"):
            try:
                rel = str(Path(rel).resolve().relative_to(repo))
            except ValueError:
                rel = str(row.get("name") or Path(rel).name)
        elif row.get("name"):
            base = materialized.get("canonical_dir") or plan.get("destination") or result.get("canonical_dir")
            if base:
                rel = f"{str(base).strip('/')}/{row['name']}"
        if rel:
            _add(str(row.get("name") or Path(rel).name), rel, int(row.get("bytes") or 0))

    dest = (
        materialized.get("canonical_dir")
        or result.get("canonical_dir")
        or plan.get("destination")
        or ""
    )
    if dest:
        dest_path = (repo / str(dest)).resolve()
        if dest_path.is_dir():
            for path in sorted(dest_path.iterdir()):
                if path.is_file():
                    _add(path.name, str(path.relative_to(repo)), path.stat().st_size)

    if not out and (
        str(plan.get("job_type") or "") == "collection_queue_task" or result.get("task_id")
    ):
        out_dir = str(result.get("out_dir") or "").strip().rstrip("/")
        if not out_dir:
            log_rel = str(result.get("log") or "")
            if log_rel:
                log_path = repo / log_rel
                if log_path.is_file():
                    text = log_path.read_text(encoding="utf-8", errors="ignore")
                    match = re.search(r'"out_dir"\s*:\s*"([^"]+)"', text)
                    if match:
                        out_dir = match.group(1)
        if out_dir:
            snap = (repo / out_dir).resolve()
            if snap.is_dir():
                _add(snap.name, str(snap.relative_to(repo)))
                for path in sorted(snap.rglob("*"))[:12]:
                    if path.is_file():
                        _add(path.name, str(path.relative_to(repo)), path.stat().st_size)
        else:
            hint = str(result.get("output_hint") or plan.get("output_hint") or "").strip().rstrip("/")
            if hint:
                base = (repo / hint).resolve()
                if base.is_dir():
                    children = sorted(
                        [p for p in base.iterdir() if p.is_dir()],
                        key=lambda p: p.name,
                        reverse=True,
                    )
                    if children:
                        latest = children[0]
                        _add(latest.name, str(latest.relative_to(repo)))
                        for path in sorted(latest.rglob("*"))[:12]:
                            if path.is_file():
                                _add(path.name, str(path.relative_to(repo)), path.stat().st_size)

    return out


def format_job_collect_outcome(
    gateway: Any,
    job_id: str,
    *,
    job: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build chat note + artifacts when a collect job finished successfully."""
    if job is None:
        job = gateway.get_yzu_job(job_id)
    if str(job.get("status") or "") != "completed":
        return "", {}

    files = procured_files_from_job(gateway, job)
    plan = job.get("plan") or {}
    lines = ["**Collection complete.**"]
    if files:
        for row in files[:6]:
            lines.append(f"- `{row['path']}` ({_human_bytes(row.get('bytes'))})")
        if len(files) > 6:
            lines.append(f"- …and {len(files) - 6} more file(s)")
        dest = plan.get("destination") or (job.get("result") or {}).get("canonical_dir")
        if dest:
            lines.append(f"\nStored under **`{dest}`** in Lab Drive → Procured.")
    else:
        lines.append("- Job finished but no local files were indexed yet — say **status** to refresh.")

    lines.append("\nSay **preview it** or open the path in **Lab Drive → Procured**.")
    extra: dict[str, Any] = {
        "procured_files": files,
        "job": job,
    }
    if files:
        extra["dataset_card"] = {
            "handle": f"job:{job_id}",
            "title": plan.get("title") or files[0]["name"],
            "source": plan.get("job_type") or "collect",
            "files": files,
            "primary_file": files[0],
        }
    promo = (job.get("result") or {}).get("registry_promotion") or []
    if promo:
        extra["registry_promotion"] = promo
        ids = [p.get("dataset_id") for p in promo if isinstance(p, dict) and p.get("dataset_id")]
        if ids:
            lines.append(f"\nPromoted to registry: `{', '.join(ids[:3])}`")
    return "\n".join(lines), extra
