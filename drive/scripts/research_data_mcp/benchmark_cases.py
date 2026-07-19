#!/usr/bin/env python3
"""Benchmark case loaders — isolated from production runtime paths."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from sharpe_kernel.paths import repo_root_from_file


def _repo_root() -> Path:
    return repo_root_from_file(__file__)


@lru_cache(maxsize=1)
def load_benchmark_config() -> dict[str, Any]:
    path = _repo_root() / "config/procurement_benchmark_cases.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_email(row: dict[str, Any]) -> str:
    if row.get("email") is not None:
        return str(row.get("email") or "")
    env_key = str(row.get("email_env") or "").strip()
    if env_key:
        return os.getenv(env_key, str(row.get("email_default") or "")).strip()
    return str(row.get("email_default") or "")


def pipeline_tier_benchmark_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for row in load_benchmark_config().get("pipeline_tier_cases") or []:
        item = dict(row)
        item["email"] = _resolve_email(row)
        item.pop("email_env", None)
        item.pop("email_default", None)
        cases.append(item)
    return cases
