#!/usr/bin/env python3
"""License classes, budgets, and access policy for procurement."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

COMMERCIAL_HINTS = re.compile(
    r"\b(nielsen|kantar|iri|euromonitor|mintel|statista|bloomberg|refinitiv|wrds|paid|subscription|commercial)\b",
    re.I,
)
GOVERNMENT_HINTS = re.compile(r"\.gov|cdc\.gov|census\.gov|data\.gov|europa\.eu|dhsprogram", re.I)
ACADEMIC_HINTS = re.compile(r"icpsr|ukdataservice|zenodo|figshare|datacite|doi\.org|arxiv", re.I)


def load_governance(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "config/procurement_governance.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def classify_url(url: str, *, name: str = "") -> str:
    blob = f"{url} {name}".lower()
    if COMMERCIAL_HINTS.search(blob):
        return "commercial"
    if GOVERNMENT_HINTS.search(blob) or GOVERNMENT_HINTS.search(urlparse(url).netloc):
        return "public_government"
    if ACADEMIC_HINTS.search(blob):
        return "public_academic"
    return "public_unknown"


def allow_auto_probe(url: str, governance: dict[str, Any], *, name: str = "") -> bool:
    blocked = set(governance.get("blocked_probe_domains") or [])
    host = urlparse(url).netloc.lower()
    if host in blocked:
        return False
    access = classify_url(url, name=name)
    blocked_classes = set(governance.get("blocked_auto_probe_classes") or ["commercial"])
    return access not in blocked_classes


def allow_auto_collect(access_class: str, governance: dict[str, Any]) -> bool:
    allowed = set(governance.get("auto_collect_classes") or ["public_government", "public_academic", "public_unknown"])
    return access_class in allowed


class ProcurementBudget:
    def __init__(self, governance: dict[str, Any]) -> None:
        budgets = governance.get("budgets") or {}
        self.max_deepseek_calls = int(budgets.get("max_deepseek_calls_per_magic", 3))
        self.max_probes = int(budgets.get("max_probes_per_magic", 3))
        self.max_tavily = int(budgets.get("max_tavily_live_per_magic", 4))
        self._deepseek = 0
        self._probes = 0
        self._tavily = 0

    def use_deepseek(self) -> bool:
        if self._deepseek >= self.max_deepseek_calls:
            return False
        self._deepseek += 1
        return True

    def use_probe(self) -> bool:
        if self._probes >= self.max_probes:
            return False
        self._probes += 1
        return True

    def use_tavily(self) -> bool:
        if self._tavily >= self.max_tavily:
            return False
        self._tavily += 1
        return True

    def snapshot(self) -> dict[str, int]:
        return {
            "deepseek_calls": self._deepseek,
            "probes": self._probes,
            "tavily_live": self._tavily,
        }
