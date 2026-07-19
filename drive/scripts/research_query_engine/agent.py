from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

from scripts.yzu_cluster.orchestrator import YzuOrchestrator
from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)


class AgentOrchestrator:
    def __init__(self, engine, config_path: str = "config/research_agent.json", orchestrator: YzuOrchestrator | None = None):
        self.engine = engine
        self.orchestrator = orchestrator or YzuOrchestrator(ROOT, engine=engine)
        self.repo_root = self.orchestrator.repo_root
        config_file = self.repo_root / config_path
        # This is a deprecated compatibility shell.  Its optional host inventory
        # must not make the primary Research Drive runtime unbootable.
        self.config = json.loads(config_file.read_text(encoding="utf-8")) if config_file.is_file() else {}
        self.jobs_root = self.orchestrator.jobs_root
        self.store = self.orchestrator.store
        self.procurement = self.orchestrator.executor.procurement
        self.remote_worker = self.repo_root / "scripts/cluster_agent/remote_collect.py"
        self._planner = None

    def set_planner(self, planner) -> None:
        self._planner = planner

    def status(self) -> dict:
        workers = self._workers()
        return {
            "brain": "legacy_agent_shell",
            "canonical_brain": "cursor_composer",
            "legacy_llm_configured": bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_BASE_URL")),
            "legacy_model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "workers": [{k: row[k] for k in ("hostname", "tailscale_ip", "status")} for row in workers],
            "allowed_job_types": self.orchestrator.allowed_job_types(),
            "pipelines": self.orchestrator.executor.pipelines(),
            "connector_count": len(self.procurement.store.list()),
            "yzu": self.orchestrator.components(),
        }

    def chat(self, message: str, context: dict | None = None) -> dict:
        """Catalog planning only — does not submit jobs. Use POST /library/chat for Composer."""
        if self._planner:
            out = self._planner.assist(message, context or {})
            return {
                "message": out["message"],
                "plan": out.get("plan"),
                "job": out.get("job"),
                "advice": out.get("advice"),
                "timing_ms": out.get("timing_ms"),
                "cluster": self.status(),
                "note": out.get("redirect"),
            }
        return {
            "message": (
                "Use POST /library/chat (Cursor Composer + MCP) for procurement. "
                "/agent/chat is a deprecated compatibility shell and does not own orchestration."
            ),
            "plan": None,
            "job": None,
            "cluster": self.status(),
        }

    def approve(self, job_id: str) -> dict:
        return self.orchestrator.approve(job_id)

    def cancel(self, job_id: str) -> dict:
        return self.orchestrator.cancel(job_id)

    def approve_connector(self, connector_id: str) -> dict:
        return self.procurement.store.approve(connector_id)

    def collect_connector(self, connector_id: str, limit: int = 200) -> dict:
        plan = self.procurement.collection_plan(connector_id, limit=limit)
        return self.orchestrator.submit(plan["title"], plan, {"connector_id": connector_id, "limit": limit})

    def _workers(self) -> list[dict]:
        inventory = self.config.get("inventory")
        if not inventory:
            return []
        path = Path(inventory)
        if not path.exists():
            return []
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return [row for row in csv.DictReader(handle) if row.get("status") == "joined"]
