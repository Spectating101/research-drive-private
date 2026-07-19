#!/usr/bin/env python3
"""Catalog-driven matching for procurement planning — no hardcoded task IDs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SHARD_RE = re.compile(r"\by20\d{2}_q[1-4]\b", re.I)
TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")


class ProcurementCatalogIndex:
  """Score message tokens against live queue, pipelines, shards, and spectator scripts."""

  def __init__(self, repo_root: Path, orchestrator: Any) -> None:
    self.repo_root = Path(repo_root).resolve()
    self.orchestrator = orchestrator
    self._cfg = json.loads((self.repo_root / "config/yzu_cluster.json").read_text(encoding="utf-8"))

  @classmethod
  def from_orchestrator(cls, orchestrator: Any) -> ProcurementCatalogIndex:
    return cls(orchestrator.repo_root, orchestrator)

  @staticmethod
  def tokens(message: str) -> set[str]:
    return set(TOKEN_RE.findall(message.lower()))

  @staticmethod
  def score_blob(message: str, *parts: str) -> float:
    tokens = ProcurementCatalogIndex.tokens(message)
    if not tokens:
      return 0.0
    blob = " ".join(str(part) for part in parts if part).lower()
    if not blob.strip():
      return 0.0
    score = sum(1.0 for token in tokens if token in blob)
    if any(token in blob for token in tokens if len(token) >= 5):
      score += 0.25
    return score

  def queue_tasks(self, *, runnable_only: bool = False) -> list[dict[str, Any]]:
    return self.orchestrator.queue_tasks(runnable_only=runnable_only)

  def pipelines(self) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pipeline_id, meta in self.orchestrator.executor.pipelines().items():
      if meta.get("enabled") is False:
        continue
      rows.append({"id": pipeline_id, "label": meta.get("label", pipeline_id), **meta})
    return rows

  def spectator_scripts(self) -> list[dict[str, Any]]:
    scripts = self._cfg.get("spectator_scripts") or {}
    return [{"id": key, **value} for key, value in scripts.items()]

  def datacite_shards(self) -> list[dict[str, str]]:
    path = self.repo_root / "scripts/data_catalog/datacite_y2025_parallel_shards.list"
    if not path.exists():
      return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
      line = line.strip()
      if not line or line.startswith("#"):
        continue
      parts = [part.strip() for part in line.split("|")]
      if len(parts) < 4:
        continue
      rows.append(
        {
          "shard": parts[0],
          "host": parts[1],
          "created_years": parts[2],
          "datacite_query": parts[3],
          "target_records": parts[4] if len(parts) > 4 else "",
        }
      )
    return rows

  def match_queue_tasks(self, message: str, *, runnable_only: bool = False, limit: int = 8) -> list[dict[str, Any]]:
    from scripts.yzu_cluster.cluster_ops import queue_tasks_enabled

    if not queue_tasks_enabled(self._cfg):
      return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for task in self.queue_tasks(runnable_only=runnable_only):
      score = self.score_blob(message, task.get("id", ""), task.get("title", ""), task.get("output_hint", ""))
      if score > 0:
        scored.append((score, task))
    scored.sort(key=lambda row: (-row[0], row[1].get("id", "")))
    return [task for _, task in scored[:limit]]

  def match_pipelines(self, message: str, limit: int = 3) -> list[dict[str, Any]]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for pipeline in self.pipelines():
      score = self.score_blob(message, pipeline.get("id", ""), pipeline.get("label", ""))
      if score > 0:
        scored.append((score, pipeline))
    scored.sort(key=lambda row: (-row[0], row[1].get("id", "")))
    return [pipeline for _, pipeline in scored[:limit]]

  def match_spectator_scripts(self, message: str) -> dict[str, Any] | None:
    scored: list[tuple[float, dict[str, Any]]] = []
    for script in self.spectator_scripts():
      score = self.score_blob(message, script.get("id", ""), script.get("script", ""), " ".join(script.get("args") or []))
      if score > 0:
        scored.append((score, script))
    if not scored:
      return None
    scored.sort(key=lambda row: (-row[0], row[1].get("id", "")))
    return scored[0][1]

  def resolve_shard(self, message: str) -> str | None:
    explicit = SHARD_RE.search(message)
    if explicit:
      return explicit.group(0).lower()
    scored: list[tuple[float, str]] = []
    for shard in self.datacite_shards():
      score = self.score_blob(message, shard.get("shard", ""), shard.get("created_years", ""), shard.get("datacite_query", ""))
      if score > 0:
        scored.append((score, shard["shard"]))
    if scored:
      scored.sort(key=lambda row: (-row[0], row[1]))
      return scored[0][1]
    datacite_score = self.score_blob(message, "datacite", "doi", "metadata", "shard", "harvest")
    if datacite_score <= 0:
      return None
    local = [shard["shard"] for shard in self.datacite_shards() if shard.get("host") == "local"]
    if local:
      return local[0]
    shards = self.datacite_shards()
    return shards[0]["shard"] if shards else None

  @staticmethod
  def task_family(task_id: str) -> str:
    return task_id.split("_", 1)[0] if "_" in task_id else task_id

  @staticmethod
  def infer_harvest_action(message: str) -> str | None:
    lowered = message.lower()
    if re.search(r"\b(status|monitor|check|progress)\b", lowered):
      return "status"
    if re.search(r"\b(pull|sync)\b", lowered):
      return "pull_meta"
    if re.search(r"\b(restart|resume|harvest|backfill|collect|download|run|start|procure)\b", lowered):
      return "restart"
    return None

  @staticmethod
  def wants_watchdog_pipeline(message: str) -> bool:
    return bool(re.search(r"\b(watchdog|rebalance|cluster ops)\b", message.lower()))

  @staticmethod
  def wants_fleet_pipeline(message: str) -> bool:
    return bool(re.search(r"\b(fleet|partition|workers?|supervisor)\b", message.lower()))
