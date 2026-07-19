#!/usr/bin/env python3
"""Spectator scrape capabilities — allowlisted Playwright scripts for the desk agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def list_spectator_scripts(repo_root: Path) -> list[dict[str, Any]]:
    path = Path(repo_root).resolve() / "config/yzu_cluster.json"
    if not path.is_file():
        return []
    cfg = json.loads(path.read_text(encoding="utf-8"))
    scripts = cfg.get("spectator_scripts") or {}
    engine = cfg.get("spectator_engine") or {}
    pools = list(engine.get("pool_order") or ["optiplex", "windows_lab"])
    out: list[dict[str, Any]] = []
    for key, meta in scripts.items():
        out.append(
            {
                "script_key": key,
                "title": meta.get("label") or key,
                "description": meta.get("description") or "",
                "when_to_use": meta.get("when_to_use")
                or (
                    "Generic Playwright page/links scrape (any public URL)"
                    if key == "generic_url_scrape"
                    else f"Named board scraper: {key}"
                ),
                "workdir": meta.get("workdir"),
                "pools": pools,
            }
        )
    return out


def build_spectator_plan(
    *,
    url: str = "",
    script_key: str = "generic_url_scrape",
    mode: str = "",
    title: str = "",
    agent_initiated: bool = True,
) -> dict[str, Any]:
    from scripts.research_data_mcp.scrape_plan import build_generic_scrape_plan, infer_scrape_mode, plan_for_url

    script_key = (script_key or "generic_url_scrape").strip()
    url = (url or "").strip()
    if script_key == "generic_url_scrape":
        if not url.startswith("http"):
            raise ValueError("url is required for generic_url_scrape")
        scrape_mode = mode or infer_scrape_mode(url)
        plan = plan_for_url(url, mode=scrape_mode, title=title)
        if plan.get("job_type") == "scraper_run":
            plan["scrape_mode"] = scrape_mode
        plan["agent_initiated"] = agent_initiated
        return plan
    plan = {
        "title": title or f"Spectator {script_key}",
        "job_type": "scraper_run",
        "script_key": script_key,
        "launchable": True,
        "timeout_seconds": 3600,
        "agent_initiated": agent_initiated,
    }
    if url.startswith("http"):
        plan["url"] = url
    return plan
